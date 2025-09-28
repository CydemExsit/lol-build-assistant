from __future__ import annotations
import argparse, json
from pathlib import Path
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE = "https://lolalytics.com"
LANG = "zh_tw"
DEF_MODE = "aram"
DEF_TIER = "d2_plus"
DEF_PATCH = "7"

BOOT_HINTS = [
    "靴","鞋","Boots","Greaves","Treads","Tabi",
    "明朗之靴","狂戰士護脛","水星之靴","鋼鐵護脛","法師之靴","機動靴","離群之靴",
    "艾歐尼亞之靴","輕靈之靴"
]

def _url(hero: str, mode: str, tier: str, patch: str, lang: str = LANG) -> str:
    return f"{BASE}/{lang}/lol/{hero.lower()}/{mode}/build/?tier={tier}&patch={patch}"

def _mkdir_for(p: str): Path(p).parent.mkdir(parents=True, exist_ok=True)

def _is_boot(name: str) -> bool:
    if not isinstance(name, str): return False
    n = name.strip().lower()
    if not n: return False
    # 「鞋子 / Boots / Boots of Speed」也算靴
    if n in {"鞋子","boots","boots of speed"}:
        return True
    return any(k.lower() in n for k in BOOT_HINTS)

# === 主要的抽取腳本（在頁面端執行） ============================================
EXTRACT_JS = r"""
(() => {
  // 解析 URL（解開 Next.js 的 /_next/image?url=...）
  const decodeItemUrl = (u) => {
    if (!u) return "";
    try {
      const abs = new URL(u, location.origin);
      const inner = abs.searchParams.get("url");
      if (inner) u = inner;
    } catch(e){}
    try { u = decodeURIComponent(u); } catch(e){}
    return u;
  };

  // 從節點抓出道具名稱/檔名（只專注 item，避免去碰符文/召喚師/技能）
  const getItemNamesFromNode = (el) => {
    const out = new Set();

    // 1) alt / aria-label / title（排除明顯不是道具的字）
    const BAD = /(Runes?|符文|技能|Summoner|召喚師|statmod|advertisement|電刑|黑暗收割|先攻|相位衝擊|迅捷步伐|征服者|強攻|致命節奏|不滅之握|召喚艾莉|背水一戰|傳奇：血脈|Flash|Cleanse|Heal|Ghost|Ignite|Exhaust|Teleport)/i;
    el.querySelectorAll('img[alt], [aria-label], [title]').forEach(n => {
      const s = (n.getAttribute('alt') || n.getAttribute('aria-label') || n.getAttribute('title') || '').trim();
      if (!s || s.length > 60 || BAD.test(s)) return;
      out.add(s);
    });

    // 2) 背景圖（已由 Python 端打上 data-bgurl，這裡直接取檔名）
    el.querySelectorAll('[data-bgurl]').forEach(n => {
      let u = decodeItemUrl(n.getAttribute('data-bgurl') || '');
      if (!/\/items\//i.test(u)) return;
      const file = (u.split('?')[0].split('/').pop() || '').toLowerCase();
      const base = file.replace(/\.(png|jpg|jpeg|webp|gif)$/i,'');
      if (base) out.add(base);
    });

    // 3) <img> src/srcset
    el.querySelectorAll('img[src], img[data-src], img[srcset], img[data-srcset]').forEach(n=>{
      let u = n.getAttribute('src') || n.getAttribute('data-src') || n.getAttribute('srcset') || n.getAttribute('data-srcset') || '';
      u = (u.split(' ')[0] || '');
      u = decodeItemUrl(u);
      if (!/\/items\//i.test(u)) return;
      const file = (u.split('?')[0].split('/').pop() || '').toLowerCase();
      const base = file.replace(/\.(png|jpg|jpeg|webp|gif)$/i,'');
      if (base) out.add(base);
    });

    return Array.from(out);
  };

  const numberPairs = (el) => {
    const t = (el.textContent || "").replace(/,/g,"");
    const nums = t.match(/\d+\.\d+|\d+/g) || [];
    // 頁面多半不附 %，直接取 0..100 的前兩個值 /100
    const vals = nums.map(Number).filter(n => isFinite(n) && n <= 100);
    if (vals.length >= 2) return [vals[0]/100, vals[1]/100];
    return [NaN, NaN];
  };

  const RE_WIN = /(Winning Items|勝率最高|單件勝率)/i;
  const RE_SET = /(Actually\s*Built\s*Sets|實際出裝|出裝組合|裝備搭配|套裝)/i;

  const wins = [], sets = [];
  const seenI = new Set(), seenS = new Set();

  const byTitle = (re) => {
    const all = Array.from(document.querySelectorAll('section,div,article,h2,h3'));
    const lab = all.find(n => re.test((n.textContent || '').trim()));
    return lab ? (lab.closest('section,div,article') || lab.parentElement || null) : null;
  };

  const harvest = (root, kind) => {
    if (!root) return;
    root.querySelectorAll('div,li,section,article').forEach(el => {
      const names = getItemNamesFromNode(el);

      if (kind === 'win') {
        if (names.length < 1 || names.length > 2) return;     // 1~2 張圖
      } else {
        if (names.length < 5) return;                          // 套裝需 ≥5（Python 端再剔靴）
      }

      const [w, p] = numberPairs(el);
      if (!isFinite(w) || !isFinite(p)) return;

      if (kind === 'win') {
        const name = names[0];
        if (seenI.has(name)) return;
        seenI.add(name);
        wins.push({ name, win: w, pick: p });
      } else {
        const top5 = names.slice(0, 5);
        const key = top5.join('|');
        if (seenS.has(key)) return;
        seenS.add(key);
        sets.push({ items: top5, win: w, pick: p });
      }
    });
  };

  // 先定位標題區塊抽，抓不到再全頁 fallback
  harvest(byTitle(RE_WIN), 'win');
  harvest(byTitle(RE_SET), 'set');
  if (wins.length < 5) harvest(document.body, 'win');
  if (sets.length < 5) harvest(document.body, 'set');

  return { wins, sets };
})();
"""

# === Playwright 爬取 ==========================================================
def _goto_and_extract(url: str, headless: bool = True):
  with sync_playwright() as p:
    b = p.chromium.launch(headless=headless)
    ctx = b.new_context(
        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
        locale="zh-TW",
        viewport={"width":1440,"height":900},
        extra_http_headers={"Referer":"https://lolalytics.com/"},
    )
    # 反自動化繞過
    ctx.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        window.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'languages', {get: () => ['zh-TW','zh','en-US','en']});
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
    """)
    page = ctx.new_page()

    # 首頁預熱
    page.goto(f"{BASE}/{LANG}/", wait_until="domcontentloaded", timeout=45000)
    try: page.wait_for_load_state("networkidle", timeout=12000)
    except PWTimeout: pass

    # 目標頁
    page.goto(url, wait_until="domcontentloaded", timeout=45000)

    # cookie
    for label in ["同意","接受","I agree","Accept","Got it"]:
      try:
        page.get_by_role("button", name=label).click(timeout=800)
        break
      except Exception:
        pass

    # 任一 item 圖元件出現（亦可能走 background-image）
    try:
        page.wait_for_selector(
            'img[src*="/items/"], img[data-src*="/items/"], img[srcset*="/items/"], img[data-srcset*="/items/"], [style*="background-image"]',
            timeout=20000
        )
    except PWTimeout:
        pass

    # 整頁滾動觸發 lazy
    for _ in range(30):
        page.mouse.wheel(0, 1800)
        page.wait_for_timeout(220)
    page.wait_for_timeout(1000)

    # 把「Actually Built Sets」區塊滾到中間
    page.evaluate(r"""
    (() => {
      const nodes = Array.from(document.querySelectorAll('*'));
      const re = /(Actually\s*Built\s*Sets|實際出裝|出裝組合|裝備搭配|套裝|Build Sets)/i;
      const hit = nodes.find(n => re.test((n.textContent||'').trim()));
      if (!hit) return false;
      (hit.closest('section,div,article')||hit).scrollIntoView({behavior:'instant', block:'center'});
      return true;
    })()
    """)
    page.wait_for_timeout(800)

    # 點「5」
    page.evaluate(r"""
    (() => {
      const center = document.elementFromPoint(innerWidth/2, innerHeight/2);
      const root = (center && center.closest('section,div,article')) || document.body;
      const btns = Array.from(root.querySelectorAll('button, a, span, div'))
        .filter(el => /^\s*[2-6]\+?\s*$/.test((el.textContent||'').trim()));
      const b5 = btns.find(el => (el.textContent||'').trim().startsWith('5'));
      if (b5) { b5.dispatchEvent(new MouseEvent('click', {bubbles:true})); return true; }
      return false;
    })()
    """)
    page.wait_for_timeout(1500)

    # 區塊內連續滾底，觸發 lazy render
    page.evaluate(r"""
    (() => {
      const re = /(Actually\s*Built\s*Sets|實際出裝|出裝組合|裝備搭配|套裝|Build Sets)/i;
      const hit = Array.from(document.querySelectorAll('*')).find(n => re.test((n.textContent||'').trim()));
      if (!hit) return false;
      const root = hit.closest('section,div,article') || hit;
      const sc = root.querySelector('[style*="overflow"], [class*="scroll"], [class*="list"]') || root;
      let tries = 0, lastH = -1, stable = 0;
      const tick = () => {
        sc.scrollTop = sc.scrollHeight + 4000;
        const h = sc.scrollHeight;
        stable = (h === lastH) ? (stable + 1) : 0;
        lastH = h;
        tries++;
        if (tries < 60 && stable < 6) setTimeout(tick, 140);
      };
      tick();
      return true;
    })()
    """)
    page.wait_for_timeout(3500)

    # 將含 /items/ 的背景圖打標為 data-bgurl（解碼 _next/image）
    page.evaluate(r"""
    (() => {
      const all = Array.from(document.querySelectorAll('*'));
      let n = 0;
      const extractUrl = (bg) => {
        const m = (bg || "").match(/url\((["']?)(.*?)\1\)/i);
        if (!m) return "";
        let u = m[2] || "";
        try {
          const abs = new URL(u, location.origin);
          const inner = abs.searchParams.get('url');
          if (inner) u = inner;
        } catch (e) {}
        try { u = decodeURIComponent(u); } catch (e) {}
        return u;
      };
      all.forEach(el => {
        const u = extractUrl(getComputedStyle(el).backgroundImage);
        if (!u) return;
        if (!/\/items\//i.test(u)) return;
        el.setAttribute('data-bgurl', u);
        n++;
      });
      return n;
    })()
    """)
    for _ in range(10):
        page.mouse.wheel(0, 1600)
        page.wait_for_timeout(180)
    page.wait_for_timeout(800)

    # 偵錯輸出
    body_text = page.evaluate("document.body.innerText")
    _mkdir_for("data/raw/body_len.txt")
    Path("data/raw/body_len.txt").write_text(str(len(body_text)), encoding="utf-8")
    Path("data/raw/body_sample.txt").write_text(body_text[:5000], encoding="utf-8")
    pct_count = page.evaluate("(document.body.innerText.match(/%/g)||[]).length")
    Path("data/raw/pct_count.txt").write_text(str(pct_count), encoding="utf-8")

    item_counts = page.evaluate(r"""
    (() => {
      const q = sel => document.querySelectorAll(sel).length;
      return {
        img_src:       q('img[src*="/items/"]'),
        img_datasrc:   q('img[data-src*="/items/"]'),
        img_srcset:    q('img[srcset*="/items/"]'),
        img_datasrcset:q('img[data-srcset*="/items/"]'),
        bg_inline:     q('[style*="background-image"]'),
        bg_tagged:     q('[data-bgurl]')
      };
    })()
    """)
    Path("data/raw/item_counts.json").write_text(json.dumps(item_counts, ensure_ascii=False, indent=2), encoding="utf-8")

    sample = page.evaluate(r"""
    (() => {
      const pick = [];
      const q = (sel) => Array.from(document.querySelectorAll(sel));
      const nodes = new Set([
        ...q('img[alt], img[data-src], img[srcset], img[data-srcset]'),
        ...q('[style*="background-image"]'),
        ...q('[data-bgurl]'),
        ...q('picture source[srcset], source[srcset]')
      ]);
      const low = s => (s||"").toLowerCase();
      const get = (n,k)=> (n.getAttribute(k)||"");
      const fromInlineBG = n => {
        const bg = (n.style && n.style.backgroundImage) || "";
        const m = bg.match(/url\((["']?)(.*?)\1\)/i);
        return m ? m[2] : "";
      };
      const url = n => {
        const cands = [
          get(n,'src'),
          get(n,'data-src'),
          (get(n,'srcset')||'').split(' ')[0],
          (get(n,'data-srcset')||'').split(' ')[0],
          get(n,'data-bgurl'),
          fromInlineBG(n)
        ];
        return cands.find(u => low(u).includes('/items/')) || "";
      };
      const name = n => (n.getAttribute('alt')||n.getAttribute('title')||n.getAttribute('aria-label')||"");
      nodes.forEach(n => { const u = url(n); if(u) pick.push({name:name(n), url:u}); });
      return pick.slice(0,80);
    })()
    """)
    Path("data/raw/item_sample.json").write_text(json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8")

    # 真正抽取
    data = page.evaluate(EXTRACT_JS)
    Path("data/raw/raw_extract.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    html = page.content()
    _mkdir_for("data/raw/snap_last.png")
    page.screenshot(path="data/raw/snap_last.png", full_page=True)
    b.close()
  return html, data

# === 後處理 & 匯出 ============================================================
def scrape(hero: str, mode: str, tier: str, patch: str, lang: str, headless: bool = True):
  url = _url(hero, mode, tier, patch, lang)
  html, data = _goto_and_extract(url, headless=headless)

  _mkdir_for("data/raw/page_try.html")
  Path("data/raw/page_try.html").write_text(html, encoding="utf-8")

  wins = data.get("wins") or []
  sets = data.get("sets") or []

  # sets：剔除靴，確保恰 5 件
  clean_sets = []
  for s in sets:
      items = [x for x in s["items"] if not _is_boot(x)]
      if len(items) == 5:
          clean_sets.append({"items": items, "win": s["win"], "pick": s["pick"]})

  # sets 去重
  uniq, seen = [], set()
  for s in clean_sets:
    k="|".join(s["items"])
    if k in seen: continue
    seen.add(k); uniq.append(s)

  # wins 單件去重
  wmap={}
  for w in wins:
    n = w.get("name")
    if n and n not in wmap:
      wmap[n] = w
  wins = list(wmap.values())

  win_df = pd.DataFrame(wins, columns=["name","win","pick"]).rename(columns={"win":"win_rate","pick":"pick_rate"})
  if not win_df.empty:
    # 若抓到 30~60 這種，當百分比轉 0~1
    for col in ("win_rate","pick_rate"):
      win_df[col] = pd.to_numeric(win_df[col], errors="coerce")
      win_df[col] = win_df[col].where(win_df[col] <= 1, win_df[col] / 100.0)
  win_df["sample_size"]=0

  set_df = pd.DataFrame(uniq, columns=["items","win","pick"]).rename(columns={"win":"set_win_rate","pick":"set_pick_rate"})
  if not set_df.empty:
    set_df["items"]=set_df["items"].apply(lambda xs:"|".join(xs))
    set_df["set_sample_size"]=0

  return win_df, set_df, url

def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--hero", required=True)
  ap.add_argument("--mode", default=DEF_MODE)
  ap.add_argument("--tier", default=DEF_TIER)
  ap.add_argument("--patch", default=DEF_PATCH)
  ap.add_argument("--lang", default=LANG)
  ap.add_argument("--winning_out", required=True)
  ap.add_argument("--sets_out", required=True)

  # ✅ 只留這一行，整數 1/0 控制是否 headless（預設 1 = 關視窗）
  ap.add_argument("--headless", type=int, default=1, help="1=headless, 0=show browser")

  args = ap.parse_args()

  win_df, set_df, url = scrape(
      args.hero, args.mode, args.tier, args.patch, args.lang,
      headless=bool(args.headless)
  )
  if win_df.empty and set_df.empty:
    raise SystemExit("[error] 抓不到列（wins/sets 皆空）。請把 data/raw/page_try.html 與 data/raw/raw_extract.json 給我。")

  _mkdir_for(args.winning_out); _mkdir_for(args.sets_out)
  win_df.to_csv(args.winning_out, index=False, encoding="utf-8")
  set_df.to_csv(args.sets_out, index=False, encoding="utf-8")
  print(f"[ok] scraped: {url}")
  if not win_df.empty:
    print(f"[ok] winning -> {args.winning_out}  rows={len(win_df)}")
  if not set_df.empty:
    print(f"[ok] sets    -> {args.sets_out}     rows={len(set_df)}")

if __name__ == "__main__":
  main()

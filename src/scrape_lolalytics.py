# -*- coding: utf-8 -*-
import argparse, os, time
from typing import Tuple
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout, Page

LANG = "zh_tw"
DEF_MODE = "aram"
DEF_TIER = "d2_plus"
DEF_PATCH = "7"

# ---------- utils ----------

def _mkdir_for(path: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def _to_pct(s: str) -> float:
    """'67.03' or '67.03%' -> 0.6703（僅 Winning Items 需要正規化成 0~1）。"""
    try:
        v = float(str(s).strip().replace("%","").replace(",",""))
        if v < 0: v = 0.0
        if v > 100: v = 100.0
        return round(v / 100.0, 6)
    except:
        return 0.0

def _text_of(el) -> str:
    try:
        return el.inner_text().strip()
    except:
        return ""

def _attr(el, name: str) -> str:
    try:
        v = el.get_attribute(name)
        return v or ""
    except:
        return ""

def _name_from_img(img) -> Tuple[str, str]:
    src = _attr(img, "src")
    alt = _attr(img, "alt")
    if alt:
        return alt, src
    base = os.path.basename(src).split(".")[0]
    return base, src

# ---------- navigation / page-ready ----------

def _goto_build_page(page: Page, hero: str, mode: str, tier: str, patch: str, lang: str) -> str:
    url = f"https://lolalytics.com/{lang}/lol/{hero}/{mode}/build/?tier={tier}&patch={patch}"
    page.goto(url, wait_until="domcontentloaded")

    # 儘量等到網路靜止（Qwik/lolx 有時仍會延遲載入）
    try:
        page.wait_for_load_state("networkidle", timeout=45000)
    except Exception:
        pass

    # 觸發 lazy render（拉到底再回頂）
    try:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(600)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(200)
    except Exception:
        pass

    # 永遠輸出除錯快照
    try:
        os.makedirs("data/raw", exist_ok=True)
        page.screenshot(path="data/raw/snap_last.png", full_page=True)
        with open("data/raw/page_last.html", "w", encoding="utf-8") as f:
            f.write(page.content())
    except Exception:
        pass

    return url

# ---------- parsers ----------

def _parse_winning_items(page: Page) -> pd.DataFrame:
    """
    解析「Winning Items」：
      1) 鎖定整個區塊（左側 'Winning' / 'Items' 標籤）
      2) 在右側橫向容器「分段橫向捲動」，每段都收集一次，直到沒有新行
      3) evaluate 把每列的 img / win / pick 拉回來
      4) 輸出欄：img, name, win_rate(0~1), pick_rate(0~1), sample_size=0
    """
    block = page.locator(
        "xpath=//div[contains(@class,'flex') and contains(@class,'h-[128px]') and contains(@class,'mb-2') and contains(@class,'border')"
        " and .//div[@class='my-1' and normalize-space()='Winning']"
        " and .//div[@class='my-1' and normalize-space()='Items']]"
    ).first

    try:
        block.wait_for(state="visible", timeout=10000)
    except Exception:
        try:
            with open("data/raw/winning_block_dump.pre.html","w",encoding="utf-8") as f:
                f.write(page.content())
        except Exception:
            pass
        return pd.DataFrame(columns=["img","name","win_rate","pick_rate","sample_size"])

    block.scroll_into_view_if_needed()

    scroller = block.locator("xpath=.//div[contains(@class,'overflow-x-scroll')]").first
    try:
        scroller.wait_for(state="visible", timeout=10000)
    except Exception:
        try:
            with open("data/raw/winning_block_dump.norows.html","w",encoding="utf-8") as f:
                f.write(block.inner_html())
        except Exception:
            pass
        return pd.DataFrame(columns=["img","name","win_rate","pick_rate","sample_size"])

    # 抽取目前畫面上的 rows
    def _extract_rows():
        return scroller.evaluate(
            """
            (el) => {
              const out = [];
              const candidates = Array.from(el.querySelectorAll('div'));
              let container = null;
              for (const c of candidates) {
                const kids = Array.from(c.children || []);
                const hasMany = kids.filter(r => r.querySelector("img[src*='/item64/']")).length;
                if (hasMany >= 5) { container = c; break; }
              }
              if (!container) return out;
              for (const row of Array.from(container.children)) {
                const img = row.querySelector("img[src*='/item64/']");
                if (!img) continue;
                const nums = Array.from(row.querySelectorAll("div.my-1"))
                  .map(e => (e.textContent || "").trim())
                  .filter(Boolean);
                const win  = nums[0] || "";
                const pick = nums[1] || "";
                out.push({ src: img.src || "", alt: img.alt || "", win, pick });
              }
              return out;
            }
            """
        )

    seen_src = set()
    data = []

    # 先觸發一次 scroll
    try:
        scroller.evaluate("(el) => { el.scrollLeft = 1; el.dispatchEvent(new Event('scroll', {bubbles:true})); }")
    except Exception:
        pass
    page.wait_for_timeout(200)

    # 逐步往右捲動，直到不能再捲或沒有新資料
    for _ in range(60):  # 最多 60 段
        rows = _extract_rows()
        new_added = 0
        for r in rows:
            key = r.get("src","")
            if not key or key in seen_src:
                continue
            seen_src.add(key)
            win_rate  = _to_pct(r.get("win",""))
            pick_rate = _to_pct(r.get("pick",""))
            if win_rate == 0.0 and pick_rate == 0.0:
                continue
            data.append({
                "img": key,
                "name": r.get("alt",""),
                "win_rate": win_rate,
                "pick_rate": pick_rate,
                "sample_size": 0,
            })
            new_added += 1

        # 嘗試再往右捲一屏
        moved = scroller.evaluate(
            """
            (el) => {
              const before = el.scrollLeft;
              const next = Math.min(el.scrollLeft + el.clientWidth, el.scrollWidth);
              el.scrollLeft = next;
              el.dispatchEvent(new Event('scroll', {bubbles:true}));
              return [before, el.scrollLeft, el.scrollWidth];
            }
            """
        )
        page.wait_for_timeout(160)

        before, after, _total = moved
        if after == before and new_added == 0:
            break  # 捲不動且沒有新資料，停止

    if not data:
        try:
            with open("data/raw/winning_block_dump.fail.html","w",encoding="utf-8") as f:
                f.write(block.inner_html())
        except Exception:
            pass

    return pd.DataFrame(data, columns=["img","name","win_rate","pick_rate","sample_size"])

def _click_sets_five(page: Page) -> None:
    """在『Actually Built Sets』區塊內把 Exact Item Count 切到 5。"""
    try:
        page.evaluate(r"""
        (() => {
          const find = (re) => Array.from(document.querySelectorAll('*'))
            .find(n => re.test((n.textContent||'').trim()));
          const blk = find(/(Actually\s*Built\s*Sets|實際出裝|出裝組合|裝備搭配|套裝)/i);
          if (!blk) return false;
          const root = blk.closest('section,div,article') || blk;
          (root).scrollIntoView({behavior:'instant', block:'center'});
          const btns = Array.from(root.querySelectorAll('button, a, span, div'));
          const b5 = btns.find(el => (el.textContent||'').trim() === '5');
          if (b5) { b5.dispatchEvent(new MouseEvent('click', {bubbles:true})); return true; }
          return false;
        })()
        """)
        page.wait_for_timeout(1200)  # 等重繪
    except Exception:
        pass


def _parse_sets_5(page: Page) -> pd.DataFrame:
    """
    Actually Built Sets（只取恰好 5 件、排除鞋、Games>1；不做橫向滑動）
    """
    _click_sets_five(page)

    js = r"""
    (() => {
      const RE_SET = /(Actually\s*Built\s*Sets|實際出裝|出裝組合|裝備搭配|套裝)/i;
      const PCT = /(\d+(?:\.\d+)?)\s*%/g;
      const NUM = /\d[\d,\.]*/g;
      const BOOT = /(靴|鞋|Boots|Greaves|Treads|Tabi|Berserker|Mercury|Plated|Sorcerer|Mobility|Ionia|Lucidity|Steelcaps|Tabi)/i;

      const byText = (re) => {
        const lab = Array.from(document.querySelectorAll('*'))
          .find(n => re.test((n.textContent||'').trim()));
        if (!lab) return null;
        return lab.closest('section,div,article') || lab;
      };

      const getItems = (el) => {
        // 蒐集可見的 item 名稱（alt / aria-label / title）
        const names = [];
        el.querySelectorAll('img[alt], [aria-label], [title]').forEach(n => {
          const v = n.getAttribute('alt') || n.getAttribute('aria-label') || n.getAttribute('title') || '';
          const s = (v||'').trim();
          if (!s || s.length > 40) return;
          names.push(s);
        });
        return names;
      };

      const twoPercents = (el) => {
        const txt = (el.textContent||'').replace(/\s+/g,' ');
        const m = [...txt.matchAll(PCT)].map(x => parseFloat(x[1]));
        if (m.length >= 2) return [m[0], m[1]];
        return [NaN, NaN];
      };

      const gamesOf = (el) => {
        // 取同列最像「場數」的數字（含千分位）
        const txt = (el.textContent||'');
        const nums = [...txt.matchAll(NUM)].map(x => x[0].replace(/,/g,''));
        // 偏向較大的整數
        const ints = nums.map(x => parseInt(x, 10)).filter(x => Number.isFinite(x));
        if (!ints.length) return 0;
        return Math.max(...ints);
      };

      const root = byText(RE_SET);
      if (!root) return [];

      const rows = Array.from(root.querySelectorAll('div,li,section,article'));
      const out = [];
      const seen = new Set();

      for (const r of rows) {
        const itemsAll = getItems(r);
        if (itemsAll.length < 5) continue;

        // 排除鞋，取前五個非鞋道具
        const items = itemsAll.filter(x => !BOOT.test(x)).slice(0, 5);
        if (items.length !== 5) continue;

        // 防誤抓：這一列的 5 個 item 要彼此不同
        if (new Set(items).size !== 5) continue;

        const [win, pick] = twoPercents(r);
        if (!Number.isFinite(win) || !Number.isFinite(pick)) continue;

        const games = gamesOf(r);
        if (!(games > 1)) continue; // 只要 sample_size > 1

        const key = items.join('|');
        if (seen.has(key)) continue;
        seen.add(key);

        out.push({ items, win, pick, games });
      }

      // 依場數降序，讓高樣本在前
      out.sort((a,b) => b.games - a.games);
      return out;
    })()
    """

    try:
        rows = page.evaluate(js) or []
    except Exception:
        rows = []

    data = []
    for r in rows:
        data.append({
            "items": "|".join(r.get("items", [])),
            "items_img": "",  # 若要圖再補；目前只要名稱即可
            "set_win_rate": float(r.get("win", 0)),
            "set_pick_rate": float(r.get("pick", 0)),
            "set_sample_size": int(r.get("games", 0)),
        })

    cols = ["items","items_img","set_win_rate","set_pick_rate","set_sample_size"]
    df = pd.DataFrame(data, columns=cols)

    if df.empty:
        # 方便你抓錯誤：dump 該區塊 HTML
        try:
            blk_html = page.evaluate(r"""
            (() => {
              const find = (re) => Array.from(document.querySelectorAll('*'))
                .find(n => re.test((n.textContent||'').trim()));
              const blk = find(/(Actually\s*Built\s*Sets|實際出裝|出裝組合|裝備搭配|套裝)/i);
              const root = blk && (blk.closest('section,div,article') || blk);
              return root ? root.innerHTML : '';
            })()
            """)
            _mkdir_for("data/raw/sets_block_dump.fail.html")
            with open("data/raw/sets_block_dump.fail.html","w",encoding="utf-8") as f:
                f.write(blk_html or "")
        except Exception:
            pass

    return df


# ---------- runner ----------

def scrape(hero: str, mode: str, tier: str, patch: str, lang: str, no_headless: bool=False):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not no_headless)
        ctx = browser.new_context(
            locale=lang.replace("_","-"),
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/121.0.0.0 Safari/537.36"),
            viewport={"width": 1440, "height": 2200}
        )
        page = ctx.new_page()
        url = _goto_build_page(page, hero, mode, tier, patch, lang)

        win_df = _parse_winning_items(page)
        sets_df = _parse_sets_5(page)

        ctx.close()
        browser.close()
        return win_df, sets_df, url

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hero", required=True)
    ap.add_argument("--mode", default=DEF_MODE)
    ap.add_argument("--tier", default=DEF_TIER)
    ap.add_argument("--patch", default=DEF_PATCH)
    ap.add_argument("--lang", default=LANG)
    ap.add_argument("--winning_out", required=True)
    ap.add_argument("--sets_out", required=True)
    ap.add_argument("--no-headless", action="store_true", help="run with browser window")
    args = ap.parse_args()

    win_df, set_df, url = scrape(args.hero, args.mode, args.tier, args.patch, args.lang, no_headless=args.no_headless)

    if win_df.empty:
        print("[warn] winning items empty")
    if set_df.empty:
        print("[warn] actually-built sets(5) empty")

    _mkdir_for(args.winning_out); _mkdir_for(args.sets_out)
    win_df.to_csv(args.winning_out, index=False, encoding="utf-8")
    set_df.to_csv(args.sets_out, index=False, encoding="utf-8")
    print(f"[ok] scraped: {url}")

    if win_df.empty:
        print("[error] winning items empty"); import sys; sys.exit(2)
    if set_df.empty:
        print("[error] actually built sets empty"); import sys; sys.exit(3)

if __name__ == "__main__":
    main()

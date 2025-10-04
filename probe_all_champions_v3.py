# -*- coding: utf-8 -*-
"""
全英雄快速探測：
- 不寫檔。逐一造訪 /{lang}/lol/{hero}/{mode}/build/?tier=...&patch=...
- 兩段驗證：Winning Items 非空 + a_5 五件 Actually Built Sets 非空。
- 任何一段失敗或丟例外，記入失敗名單。
- 以 tierlist 與多個候補頁面蒐集 hero slugs；若頁面未帶語系或 URL 變形也能匹配。

用法：
  python probe_all_champions_v3.py --lang zh_tw --mode aram --tier d2_plus --patch 7
  python probe_all_champions_v3.py --limit 20
"""
import argparse, re, time
from typing import List, Dict, Any, Tuple, Set
import pandas as pd
from playwright.sync_api import sync_playwright, Page

LANG = "zh_tw"
DEF_MODE = "aram"
DEF_TIER = "d2_plus"
DEF_PATCH = "7"

SCROLL_STEP = 378
SCROLL_PAUSE_MS = 160
MAX_SCROLL_STEPS = 800
MAX_STALL = 6

# ----------------- core utils -----------------

def _goto(page: Page, url: str):
    page.goto(url, wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=45000)
    except Exception:
        pass
    # 嘗試觸發 lazy render
    try:
        for _ in range(2):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(350)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(150)
    except Exception:
        pass


def _to_pct(s: str) -> float:
    try:
        v = float(str(s).strip().replace("%", "").replace(",", ""))
        if v < 0: v = 0.0
        if v > 100: v = 100.0
        return round(v / 100.0, 6)
    except Exception:
        return 0.0

# ----------------- Winning Items -----------------

def parse_winning_items(page: Page) -> pd.DataFrame:
    block = page.locator(
        "xpath=//div[contains(@class,'flex') and contains(@class,'h-[128px]') and contains(@class,'mb-2') and contains(@class,'border')"
        " and .//div[@class='my-1' and normalize-space()='Winning']"
        " and .//div[@class='my-1' and normalize-space()='Items']]"
    ).first
    try:
        block.wait_for(state="visible", timeout=8000)
    except Exception:
        return pd.DataFrame(columns=["img","name","win_rate","pick_rate","sample_size"])

    scroller = block.locator("xpath=.//div[contains(@class,'overflow-x-scroll')]").first
    try:
        scroller.wait_for(state="visible", timeout=6000)
    except Exception:
        return pd.DataFrame(columns=["img","name","win_rate","pick_rate","sample_size"])

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
    try:
        scroller.evaluate("(el)=>{ el.scrollLeft = 1; el.dispatchEvent(new Event('scroll',{bubbles:true})); }")
    except Exception:
        pass
    page.wait_for_timeout(150)

    for _ in range(60):
        rows = _extract_rows()
        new_added = 0
        for r in rows:
            key = r.get("src", "")
            if not key or key in seen_src:
                continue
            seen_src.add(key)
            win_rate = _to_pct(r.get("win", ""))
            pick_rate = _to_pct(r.get("pick", ""))
            if win_rate == 0.0 and pick_rate == 0.0:
                continue
            data.append({
                "img": key,
                "name": r.get("alt", ""),
                "win_rate": win_rate,
                "pick_rate": pick_rate,
                "sample_size": 0,
            })
            new_added += 1
        moved = scroller.evaluate(
            """
            (el)=>{ const b=el.scrollLeft; const n=Math.min(b+el.clientWidth, el.scrollWidth); el.scrollLeft=n; el.dispatchEvent(new Event('scroll',{bubbles:true})); return [b, el.scrollLeft, el.scrollWidth]; }
            """
        )
        page.wait_for_timeout(140)
        if moved[1] == moved[0] and new_added == 0:
            break
    return pd.DataFrame(data, columns=["img","name","win_rate","pick_rate","sample_size"])

# ----------------- Actually Built Sets (5 items) -----------------

def click_sets_5(page: Page):
    try:
        a5 = page.locator("[data-type='a_5']").first
        if a5 and a5.count() > 0:
            a5.click()
            page.wait_for_selector("img[data-id^='4_']", timeout=5000)
            time.sleep(0.12)
    except Exception:
        pass


def find_sets_scroller(page: Page):
    scrollers = page.locator(
        "xpath=//div[contains(@class,'overflow-x-scroll') and .//div[contains(@class,'gap-[6px]') and contains(@class,'text-center') and contains(@style,'padding-left')]]"
    )
    count = scrollers.count() if scrollers else 0
    for i in range(count):
        sc = scrollers.nth(i)
        try:
            ok = sc.evaluate(
                """
                (el)=> Array.from(el.querySelectorAll('div')).some(row => [0,1,2,3,4].every(k => row.querySelector(`img[data-id^="${k}_"]`)))
                """
            )
        except Exception:
            ok = False
        if ok:
            return sc
    return None


def extract_visible_sets(scroller) -> List[Dict[str, Any]]:
    rows = scroller.evaluate(
        """
        (el)=>{
          const out=[]; let container=null;
          for(const c of Array.from(el.querySelectorAll('div'))){
            const kids=Array.from(c.children||[]); const cnt=kids.filter(r=>r.querySelector("img[data-id^='0_']")).length; if(cnt>=3){container=c; break;}
          }
          if(!container) return out;
          for(const row of Array.from(container.children)){
            const imgs=[]; for(let k=0;k<5;k++){ const im=row.querySelector(`img[data-id^='${k}_']`); if(!im){imgs.length=0; break;} imgs.push(im); }
            if(!imgs.length) continue;
            const names=imgs.map(i=>i.alt||""); const images=imgs.map(i=>i.src||"");
            const nums=Array.from(row.querySelectorAll('div.my-1')).map(e=>(e.textContent||'').trim()).filter(Boolean).map(t=>parseFloat(t.replace('%','').replace(',',''))).filter(v=>Number.isFinite(v));
            const win=nums[0]||0, pick=nums[1]||0, games=Math.round(nums[2]||0);
            out.push({names, images, win, pick, games});
          }
          return out;
        }
        """
    )
    return rows or []


def parse_sets_5(page: Page) -> pd.DataFrame:
    click_sets_5(page)
    scroller = find_sets_scroller(page)
    if not scroller:
        return pd.DataFrame(columns=["items","items_img","set_win_rate","set_pick_rate","set_sample_size"])

    seen: Set[str] = set()
    out: List[Dict[str, Any]] = []
    stall=0

    try:
        scroller.evaluate("(el)=>{ el.scrollLeft = Math.max(el.scrollLeft, 1); el.dispatchEvent(new Event('scroll',{bubbles:true})); }")
        page.wait_for_timeout(100)
    except Exception:
        pass

    for step in range(MAX_SCROLL_STEPS):
        rows = extract_visible_sets(scroller)
        new_added=0
        stop=False
        for r in rows:
            names=r.get("names",[]); images=r.get("images",[])
            if len(names)!=5 or len(images)!=5: continue
            if any(src.endswith("/2003.webp") or src.endswith("/2031.webp") for src in images):
                continue
            key="|".join(names)
            if key in seen: continue
            seen.add(key)
            games=int(r.get("games",0))
            out.append({
                "items": key,
                "items_img": "|".join(images),
                "set_win_rate": float(r.get("win",0)),
                "set_pick_rate": float(r.get("pick",0)),
                "set_sample_size": games,
            })
            new_added+=1
            if games<2:
                stop=True
        if stop:
            break
        before, after, sw = scroller.evaluate(
            f"""
            (el)=>{{ const b=el.scrollLeft; const n=Math.min(b+{SCROLL_STEP}, el.scrollWidth-el.clientWidth); el.scrollLeft=n; el.dispatchEvent(new Event('scroll',{{bubbles:true}})); return [b, el.scrollLeft, el.scrollWidth]; }}
            """
        )
        page.wait_for_timeout(SCROLL_PAUSE_MS)
        stall = stall+1 if after==before else 0
        if stall>=MAX_STALL: break
        if new_added==0 and after==before: break

    cols=["items","items_img","set_win_rate","set_pick_rate","set_sample_size"]
    return pd.DataFrame(out, columns=cols) if out else pd.DataFrame(columns=cols)

# ----------------- gather hero slugs -----------------

def collect_aram_slugs(page: Page, lang: str, tier: str, patch: str) -> List[str]:
    # 多組候選 URL，含/不含語系，大小寫 queue 參數
    urls = [
        f"https://lolalytics.com/{lang}/lol/tierlist/?tier={tier}&patch={patch}&queue=aram",
        f"https://lolalytics.com/{lang}/lol/tierlist/?queue=aram",
        f"https://lolalytics.com/lol/tierlist/?queue=aram",
        f"https://lolalytics.com/lol/tierlist/aram/",
        f"https://lolalytics.com/{lang}/lol/",
        "https://lolalytics.com/lol/",
    ]
    slugs: Set[str] = set()
    pat_strict = re.compile(r"/lol/([^/]+)/aram/build/")
    pat_loose  = re.compile(r"/lol/([^/]+)/(?:aram|sr)/build/")
    pat_any    = re.compile(r"/lol/([^/]+)/")

    for u in urls:
        try:
            _goto(page, u)
            # 收集所有 href
            anchors = page.evaluate("() => Array.from(document.querySelectorAll('a[href]')).map(a=>a.getAttribute('href'))") or []
            hrefs = [h for h in anchors if isinstance(h, str)]
        except Exception:
            continue
        for h in hrefs:
            m = pat_strict.search(h) or pat_loose.search(h) or pat_any.search(h)
            if m:
                slug = m.group(1)
                # 過濾非英雄路徑，例如 tierlist、items 等
                if slug in {"tierlist","items","duos","aram","sr","ban","top","jungle","mid","adc","support"}:
                    continue
                if re.fullmatch(r"[a-z0-9\-']+", slug):
                    slugs.add(slug)
        if len(slugs) >= 150:
            break

    if len(slugs) < 50:
        # 後備：給一組常見英雄，避免 0 筆
        fallback = [
            'ahri','akali','alistar','amumu','anivia','annie','aphelios','ashe','aurelionsol','azir','bard','belveth',
            'blitzcrank','brand','braum','briar','caitlyn','camille','cassiopeia','chogath','corki','darius','diana',
            'draven','ekko','elise','evelynn','ezreal','fiddlesticks','fiora','fizz','galio','gangplank','garen',
            'gnar','gragas','graves','gwen','hecarim','heimerdinger','hwei','illaoi','irelia','ivern','janna','jarvaniv',
            'jax','jayce','jhin','jinx','kaisa','kalista','karma','karthus','kassadin','katarina','kayle','kayn','kennen',
            'khazix','kindred','kled','kogmaw','leblanc','leesin','leona','lillia','lissandra','lucian','lulu','lux',
            'malphite','malzahar','maokai','masteryi','milio','missfortune','mordekaiser','morgana','naafiri','nami',
            'nasus','nautilus','neeko','nidalee','nilah','nocturne','nunu','olaf','orianna','ornn','pantheon','poppy',
            'pyke','qiyana','quinn','rakan','rammus','reksai','rell','renata','renekton','rengar','riven','rumble',
            'ryze','samira','sejuani','senna','seraphine','sett','shaco','shen','shyvana','singed','sion','sivir',
            'skarner','smolder','sona','soraka','swain','sylas','syndra','tahmkench','taliyah','talon','taric','teemo',
            'thresh','tristana','trundle','tryndamere','twistedfate','twitch','udyr','urgot','varus','vayne','veigar',
            'velkoz','vex','vi','viego','viktor','vladimir','volibear','warwick','wukong','xayah','xerath','xinzhao',
            'yasuo','yone','yorick','yuumi','zac','zed','zeri','ziggs','zilean','zoe','zyra'
        ]
        for s in fallback:
            slugs.add(s)
    return sorted(slugs)

# ----------------- main probe -----------------

def probe_all(lang: str, mode: str, tier: str, patch: str, limit: int = 0):
    failures: List[Tuple[str, str]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            locale=lang.replace("_","-"),
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/121.0.0.0 Safari/537.36"),
            viewport={"width":1440, "height":2200}
        )
        page = ctx.new_page()

        slugs = collect_aram_slugs(page, lang, tier, patch)
        total = len(slugs)
        test_list = slugs[:limit] if limit>0 else slugs
        print(f"[info] heroes detected: {total}, testing: {len(test_list)}")

        tested = 0
        for slug in test_list:
            url = f"https://lolalytics.com/{lang}/lol/{slug}/{mode}/build/?tier={tier}&patch={patch}"
            try:
                _goto(page, url)
                win_df = parse_winning_items(page)
                sets_df = parse_sets_5(page)
                ok_win  = not win_df.empty
                ok_sets = not sets_df.empty
                if ok_win and ok_sets:
                    pass
                else:
                    reason = ("win_empty" if not ok_win else "") + ("|sets_empty" if not ok_sets else "")
                    failures.append((slug, reason.strip('|') or 'empty'))
            except Exception as e:
                failures.append((slug, f"exception:{type(e).__name__}"))
            tested += 1
            if tested % 10 == 0:
                print(f"[progress] {tested}/{len(test_list)} tested; failures so far: {len(failures)}")
            page.wait_for_timeout(60)

        ctx.close(); browser.close()

    if not failures:
        print("[result] all tested heroes passed")
        return
    print("[result] failures =", len(failures))
    by_reason: Dict[str, List[str]] = {}
    for slug, reason in failures:
        by_reason.setdefault(reason, []).append(slug)
    for reason, names in sorted(by_reason.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        print(f"  - {reason}: {len(names)}")
    print("[list] failed heroes:")
    print(", ".join(slug for slug, _ in failures))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default=LANG)
    ap.add_argument("--mode", default=DEF_MODE)
    ap.add_argument("--tier", default=DEF_TIER)
    ap.add_argument("--patch", default=DEF_PATCH)
    ap.add_argument("--limit", type=int, default=0, help="limit number of heroes for quick test")
    args = ap.parse_args()
    probe_all(args.lang, args.mode, args.tier, args.patch, args.limit)

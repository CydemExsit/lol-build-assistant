# -*- coding: utf-8 -*-
"""
擴充 _parse_sets_5：
- 在 a_5（Actually Built 5 件、不含靴）區塊中，找到橫向卷軸容器與其內部 list（style 會有 padding-left）。
- 以固定步長 378px 右移（等同使用者拖動），每步抽取可見列，直到：
  1) 無法再右移，或
  2) 沒有新資料連續數次，或
  3) 新抓到的 set_sample_size < 2。

說明：Lolalytics 的 Qwik 前端會在 scroller 的 on:scroll 事件裡改 inner list 的 padding-left，
這裡採用修改 scroller.scrollLeft 來觸發重繪，比直接改 padding-left 更穩定。
"""

import argparse, os, time
from typing import Tuple, List, Dict, Any
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout, Page

LANG = "zh_tw"
DEF_MODE = "aram"
DEF_TIER = "d2_plus"
DEF_PATCH = "7"

SCROLL_STEP = 378  # 使用者觀察到的固定步距
SCROLL_PAUSE_MS = 160
MAX_SCROLL_STEPS = 800
MAX_STALL = 6

# ---------- utils ----------

def _mkdir_for(path: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def _to_pct(s: str) -> float:
    """'67.03' or '67.03%' -> 0.6703（僅 Winning Items 需要正規化成 0~1）。"""
    try:
        v = float(str(s).strip().replace("%","" ).replace(",",""))
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
    try:
        page.wait_for_load_state("networkidle", timeout=45000)
    except Exception:
        pass
    try:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(600)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(200)
    except Exception:
        pass
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
        scroller.evaluate("(el) => { el.scrollLeft = 1; el.dispatchEvent(new Event('scroll', {bubbles:true})); }")
    except Exception:
        pass
    page.wait_for_timeout(200)

    for _ in range(60):
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
            break

    if not data:
        try:
            with open("data/raw/winning_block_dump.fail.html","w",encoding="utf-8") as f:
                f.write(block.inner_html())
        except Exception:
            pass

    return pd.DataFrame(data, columns=["img","name","win_rate","pick_rate","sample_size"])

# ---------- Actually Built Sets: scrolling 5-piece rows ----------

def _click_sets_five(page: Page) -> None:
    """Actually Built Sets：只切到 a_5（不含靴的 5 件）。"""
    try:
        a5 = page.locator("[data-type='a_5']").first
        if a5 and a5.count() > 0:
            a5.click()
            page.wait_for_selector("img[data-id^='4_']", timeout=5000)
            time.sleep(0.15)
    except Exception:
        pass

def _find_sets_scroller(page: Page):
    """返回 (scroller, inner_list)；皆為 Locator。找不到則 (None, None)。"""
    # 候選：具有 overflow-x-scroll，且其下存在一個有 padding-left 風格的 list 容器
    scrollers = page.locator(
        "xpath=//div[contains(@class,'overflow-x-scroll') and .//div[contains(@class,'gap-[6px]') and contains(@class,'text-center') and contains(@style,'padding-left')]]"
    )
    count = scrollers.count() if scrollers else 0
    for i in range(count):
        sc = scrollers.nth(i)
        try:
            # 確認此 scroller 裡可見 5 件列（各有 data-id^='0_'..'4_'）
            ok = sc.evaluate(
                """
                (el) => {
                  const hasRow = Array.from(el.querySelectorAll('div')).some(row =>
                    [0,1,2,3,4].every(k => row.querySelector(`img[data-id^="${k}_"]`))
                  );
                  return !!hasRow;
                }
                """
            )
        except Exception:
            ok = False
        if ok:
            inner = sc.locator("xpath=.//div[contains(@class,'gap-[6px]') and contains(@style,'padding-left')]").first
            return sc, inner
    return None, None


def _extract_visible_sets(scroller) -> List[Dict[str, Any]]:
    """在給定 scroller 目前畫面中抽取 5 件列。回傳 list(dict)。"""
    rows = scroller.evaluate(
        """
        (el) => {
          const out = [];
          // 尋找子容器，其中每個 child 代表一列
          let container = null;
          for (const c of Array.from(el.querySelectorAll('div'))) {
            const kids = Array.from(c.children || []);
            const cnt = kids.filter(r => r.querySelector("img[data-id^='0_']")).length;
            if (cnt >= 3) { container = c; break; }
          }
          if (!container) return out;
          for (const row of Array.from(container.children)) {
            const imgs = [];
            for (let k=0; k<5; k++) {
              const img = row.querySelector(`img[data-id^='${k}_']`);
              if (!img) { imgs.length = 0; break; }
              imgs.push(img);
            }
            if (!imgs.length) continue;
            const names  = imgs.map(i => i.alt || "");
            const images = imgs.map(i => i.src || "");
            const nums = Array.from(row.querySelectorAll("div.my-1"))
              .map(e => (e.textContent || "").trim())
              .filter(Boolean)
              .map(t => parseFloat(t.replace('%','').replace(',','')))
              .filter(v => Number.isFinite(v));
            const win = nums[0] || 0;
            const pick = nums[1] || 0;
            const games = Math.round(nums[2] || 0);
            out.push({ names, images, win, pick, sample: games });
          }
          return out;
        }
        """
    )
    return rows or []


def _parse_sets_5(page: Page) -> pd.DataFrame:
    _click_sets_five(page)

    # 永遠保留一份完整 DOM 方便除錯
    try:
        _mkdir_for("data/raw/page_last.html")
        with open("data/raw/page_last.html","w",encoding="utf-8") as f:
            f.write(page.content())
    except Exception:
        pass

    scroller, inner = _find_sets_scroller(page)
    if not scroller:
        # 退而求其次，沿用舊法從全頁抓可見列
        imgs0 = page.locator("css=img[data-id^='0_']")
        try:
            total = imgs0.count()
        except Exception:
            total = 0
        if total == 0:
            return pd.DataFrame(columns=["items","items_img","set_win_rate","set_pick_rate","set_sample_size"])
        # 沒有捲動器就只收一次可見區
        return _collect_sets_from_scoped(imgs0)

    seen_key = set()
    out: List[Dict[str, Any]] = []
    stall = 0
    last_left = -1

    # 先觸發一次 scroll 以保險
    try:
        scroller.evaluate("(el)=>{ el.scrollLeft = Math.max(el.scrollLeft, 1); el.dispatchEvent(new Event('scroll', {bubbles:true})); }")
        page.wait_for_timeout(120)
    except Exception:
        pass

    for step in range(MAX_SCROLL_STEPS):
        rows = _extract_visible_sets(scroller)
        new_added = 0
        stop_due_to_small_sample = False
        for r in rows:
            names = r.get("names", [])
            images = r.get("images", [])
            if len(names) != 5 or len(images) != 5:
                continue
            # 排除起手裝的假陽性（藥水）
            if any(src.endswith("/2003.webp") or src.endswith("/2031.webp") for src in images):
                continue
            key = "|".join(names)
            if key in seen_key:
                continue
            seen_key.add(key)
            win, pick, games = float(r.get("win",0)), float(r.get("pick",0)), int(r.get("sample",0))
            out.append({
                "items": key,
                "items_img": "|".join(images),
                "set_win_rate": win,
                "set_pick_rate": pick,
                "set_sample_size": games,
            })
            new_added += 1
            if games < 2:
                stop_due_to_small_sample = True
        if stop_due_to_small_sample:
            break

        # 嘗試右移一個固定步距
        before, after, sw = scroller.evaluate(
            f"""
            (el) => {{
              const before = el.scrollLeft;
              const next = Math.min(before + {SCROLL_STEP}, el.scrollWidth - el.clientWidth);
              el.scrollLeft = next;
              el.dispatchEvent(new Event('scroll', {{bubbles:true}}));
              return [before, el.scrollLeft, el.scrollWidth];
            }}
            """
        )
        page.wait_for_timeout(SCROLL_PAUSE_MS)

        if after == before:
            stall += 1
        else:
            stall = 0
        if stall >= MAX_STALL:
            break
        if new_added == 0 and after == last_left:
            # 沒新資料而且位置未變
            break
        last_left = after

    cols = ["items","items_img","set_win_rate","set_pick_rate","set_sample_size"]
    df = pd.DataFrame(out, columns=cols) if out else pd.DataFrame(columns=cols)

    if df.empty:
        try:
            block = page.locator("xpath=//div[.//div[@data-type='a_5']]").first
            _mkdir_for("data/raw/sets_block_dump.fail.html")
            with open("data/raw/sets_block_dump.fail.html","w",encoding="utf-8") as f:
                f.write(block.inner_html())
        except Exception:
            pass

    return df


def _collect_sets_from_scoped(imgs0_locator) -> pd.DataFrame:
    out, seen = [], set()
    try:
        total = imgs0_locator.count()
    except Exception:
        total = 0
    for i in range(total):
        img0 = imgs0_locator.nth(i)
        row = img0.locator("xpath=ancestor::div[1]")
        for _ in range(6):
            if all(row.locator(f"css=img[data-id^='{k}_']").count() > 0 for k in range(5)):
                break
            row = row.locator("xpath=ancestor::div[1]")
        if any(row.locator(f"css=img[data-id^='{k}_']").count() == 0 for k in range(5)):
            continue
        names, imgs, skip = [], [], False
        for k in range(5):
            q = row.locator(f"css=img[data-id^='{k}_']").first
            n, src = _name_from_img(q)
            names.append(n)
            imgs.append(src)
            if src.endswith("/2003.webp") or src.endswith("/2031.webp"):
                skip = True
        if skip:
            continue
        key = "|".join(names)
        if key in seen:
            continue
        seen.add(key)
        texts = [t.strip() for t in row.locator("xpath=.//div[contains(@class,'my-1')]").all_inner_texts() if t.strip()]
        nums = []
        for t in texts:
            try:
                nums.append(float(t.replace("%","" ).replace(",","")))
            except:
                pass
        if len(nums) < 3:
            continue
        win, pick, sample = nums[0], nums[1], int(nums[2])
        out.append({
            "items": key,
            "items_img": "|".join(imgs),
            "set_win_rate": win,
            "set_pick_rate": pick,
            "set_sample_size": sample,
        })
    cols = ["items","items_img","set_win_rate","set_pick_rate","set_sample_size"]
    return pd.DataFrame(out, columns=cols) if out else pd.DataFrame(columns=cols)

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

        ctx.close(); browser.close()
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

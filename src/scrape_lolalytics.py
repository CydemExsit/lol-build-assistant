# -*- coding: utf-8 -*-
import argparse, os, time
from typing import Tuple
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout, Page

LANG = "zh_tw"
DEF_MODE = "aram"
DEF_TIER = "d2_plus"
DEF_PATCH = "7"

def _mkdir_for(path: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def _to_pct(s: str) -> float:
    """'67.03' or '67.03%' -> 0.6703；容錯處理（只給 Winning Items 用）"""
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

def _goto_build_page(page, hero: str, mode: str, tier: str, patch: str, lang: str) -> str:
    url = f"https://lolalytics.com/{lang}/lol/{hero}/{mode}/build/?tier={tier}&patch={patch}"
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_selector("div.my-1", timeout=30000)
    return url

def _parse_winning_items(page: Page) -> pd.DataFrame:
    """
    只解析「Winning Items」：
      1) 鎖定整個區塊（含左側 'Winning' / 'Items' 標籤）
      2) 右側橫向容器做一次 scroll 觸發
      3) 直接 evaluate 把每列的 img / win / pick 拉回來
    """
    block = page.locator(
        "xpath=//div[contains(@class,'flex') and contains(@class,'h-[128px]') and contains(@class,'mb-2') and contains(@class,'border')"
        " and .//div[@class='my-1' and normalize-space()='Winning']"
        " and .//div[@class='my-1' and normalize-space()='Items']]"
    ).first
    block.wait_for(state="visible", timeout=10000)
    block.scroll_into_view_if_needed()

    scroller = block.locator("xpath=.//div[contains(@class,'overflow-x-scroll')]").first
    scroller.wait_for(state="visible", timeout=10000)
    try:
        scroller.evaluate("(el) => { el.scrollLeft = 1; el.dispatchEvent(new Event('scroll', {bubbles:true})); }")
    except Exception:
        pass
    page.wait_for_timeout(200)

    rows = scroller.evaluate(
        """
        (el) => {
          const candidates = Array.from(el.querySelectorAll('div'));
          let container = null;
          for (const c of candidates) {
            const kids = Array.from(c.children || []);
            const hasMany = kids.filter(r => r.querySelector("img[src*='/item64/']")).length;
            if (hasMany >= 5) { container = c; break; }
          }
          if (!container) return [];
          return Array.from(container.children).map(row => {
            const img = row.querySelector("img[src*='/item64/']");
            if (!img) return null;
            const nums = Array.from(row.querySelectorAll("div.my-1"))
              .map(e => (e.textContent || "").trim())
              .filter(Boolean);
            const win  = nums[0] || "";
            const pick = nums[1] || "";
            return { src: img.src || "", alt: img.alt || "", win, pick };
          }).filter(Boolean);
        }
        """
    )

    data = []
    for r in rows:
        win_rate  = _to_pct(r.get("win",""))
        pick_rate = _to_pct(r.get("pick",""))
        if win_rate == 0.0 and pick_rate == 0.0:
            continue
        data.append({
            "img": r.get("src",""),
            "name": r.get("alt",""),
            "win_rate": win_rate,
            "pick_rate": pick_rate,
        })

    if not data:
        try:
            html_dump = block.inner_html()
            _mkdir_for("data/raw/winning_block_dump.fail.html")
            with open("data/raw/winning_block_dump.fail.html","w",encoding="utf-8") as f:
                f.write(html_dump)
        except Exception:
            pass

    # algo.load_winning_items 需要 sample_size 欄；這裡固定補 0
    return pd.DataFrame(data, columns=["img","name","win_rate","pick_rate"]).assign(sample_size=0)

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

def _parse_sets_5(page: Page) -> pd.DataFrame:
    """
    抓 Actually Built Sets（a_5，不含靴）。
    全頁尋找 data-id 前綴 0..4 的五件列，再過濾掉含藥水(2003/2031)的起手裝列。
    直接使用頁面上的數值（Win / Pick / Games）。
    另外固定輸出 items_img 供 MD 顯示圖片。
    """
    _click_sets_five(page)

    # 永遠保留一份完整 DOM 方便除錯
    try:
        _mkdir_for("data/raw/page_last.html")
        with open("data/raw/page_last.html","w",encoding="utf-8") as f:
            f.write(page.content())
    except Exception:
        pass

    imgs0 = page.locator("css=img[data-id^='0_']")
    try:
        total = imgs0.count()
    except Exception:
        total = 0

    out, seen = [], set()
    for i in range(total):
        img0 = imgs0.nth(i)
        # 往上找到同一列且同時含有 0..4 五張圖的容器
        row = img0.locator("xpath=ancestor::div[1]")
        for _ in range(6):
            if all(row.locator(f"css=img[data-id^='{k}_']").count() > 0 for k in range(5)):
                break
            row = row.locator("xpath=ancestor::div[1]")

        if any(row.locator(f"css=img[data-id^='{k}_']").count() == 0 for k in range(5)):
            continue

        # 5 件（名稱與圖片）
        names, imgs, skip = [], [], False
        for k in range(5):
            q = row.locator(f"css=img[data-id^='{k}_']").first
            n, src = _name_from_img(q)
            names.append(n)
            imgs.append(src)
            # 排除 Starting Items 假陽性
            if src.endswith("/2003.webp") or src.endswith("/2031.webp"):
                skip = True
        if skip:
            continue

        key = "|".join(names)
        if key in seen:
            continue
        seen.add(key)

        # 這一列的數字（直接沿用網站顯示，不做百分比縮放）
        texts = [t.strip() for t in row.locator("xpath=.//div[contains(@class,'my-1')]").all_inner_texts() if t.strip()]
        nums = []
        for t in texts:
            try:
                nums.append(float(t.replace("%","").replace(",","")))
            except:
                pass
        if len(nums) < 3:
            continue

        win, pick, sample = nums[0], nums[1], int(nums[2])

        out.append({
            "items": "|".join(names),
            "items_img": "|".join(imgs),
            "set_win_rate": win,
            "set_pick_rate": pick,
            "set_sample_size": sample,
        })

    cols = ["items","items_img","set_win_rate","set_pick_rate","set_sample_size"]
    df = pd.DataFrame(out, columns=cols) if out else pd.DataFrame(columns=cols)

    # 若仍抓不到，dump a_5 區塊的 HTML 以便判斷
    if df.empty:
        try:
            block = page.locator("xpath=//div[.//div[@data-type='a_5']]").first
            _mkdir_for("data/raw/sets_block_dump.fail.html")
            with open("data/raw/sets_block_dump.fail.html","w",encoding="utf-8") as f:
                f.write(block.inner_html())
        except Exception:
            pass

    return df

def scrape(hero: str, mode: str, tier: str, patch: str, lang: str, no_headless: bool=False):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not no_headless)
        ctx = browser.new_context()
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

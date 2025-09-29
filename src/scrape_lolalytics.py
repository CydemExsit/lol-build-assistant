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

def _click_sets_five(page: Page):
    """Actually Built Sets：點 a_5（不含靴）；回傳按鈕 locator 供後續 scroll。"""
    a5 = None
    try:
        a5 = page.locator("[data-type='a_5']").first
        if a5 and a5.count() > 0:
            a5.click()
            # 等到第 5 件（data-id^='4_'）渲染出來（任何地方的可見 4_）
            page.wait_for_selector("css=img[data-id^='4_']:visible", timeout=8000)
            time.sleep(0.2)
    except Exception:
        pass
    return a5


def _parse_sets_5(page: Page) -> pd.DataFrame:
    """
    Actually Built Sets（a_5）：
    - 點 a_5 並把它捲進視口，觸發懶載入
    - 全頁只取「可見」的 data-id=0_ 圖片，往上找含 0..4_ 五張「可見」圖片的那層當一列
    - 排除含藥水(2003/2031)的起手列
    - 輸出 items 與 items_img 兩欄，數值不做百分比換算
    """
    a5 = _click_sets_five(page)
    try:
        if a5:
            a5.scroll_into_view_if_needed()
            page.wait_for_timeout(200)
    except Exception:
        pass

    # 若還沒渲染，嘗試把頁面往下捲一段（Lux 常需要）
    try:
        if page.locator("css=img[data-id^='0_']:visible").count() == 0:
            page.evaluate("() => window.scrollBy(0, window.innerHeight * 0.8)")
            page.wait_for_timeout(250)
    except Exception:
        pass

    imgs0 = page.locator("css=img[data-id^='0_']:visible")
    try:
        n0 = imgs0.count()
    except Exception:
        n0 = 0

    out, seen = [], set()
    for i in range(n0):
        img0 = imgs0.nth(i)
        row = img0.locator("xpath=ancestor::div[1]")

        # 往上爬到同時含有 0..4_ 五張「可見」圖片的容器
        for _ in range(6):
            ok_row = True
            for k in range(5):
                if row.locator(f"css=img[data-id^='{k}_']:visible").count() == 0:
                    ok_row = False
                    break
            if ok_row:
                break
            row = row.locator("xpath=ancestor::div[1]")

        if any(row.locator(f"css=img[data-id^='{k}_']:visible").count() == 0 for k in range(5)):
            continue

        # 5 件道具（依 0..4 序），同時蒐集圖片 URL；排除含藥水
        names, imgs, skip = [], [], False
        for k in range(5):
            q = row.locator(f"css=img[data-id^='{k}_']:visible").first
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

        # 抓該列數字（Win / Pick / Games），用網站原值
        texts = [t.strip() for t in row.locator("xpath=.//div[contains(@class,'my-1')]").all_inner_texts() if t.strip()]
        nums = []
        for t in texts:
            try:
                nums.append(float(t.replace("%", "").replace(",", "")))
            except:
                pass
        if len(nums) < 3:
            continue

        out.append({
            "items": key,
            "items_img": "|".join(imgs),
            "set_win_rate": nums[0],
            "set_pick_rate": nums[1],
            "set_sample_size": int(nums[2]),
        })

    cols = ["items", "items_img", "set_win_rate", "set_pick_rate", "set_sample_size"]
    return pd.DataFrame(out, columns=cols) if out else pd.DataFrame(columns=cols)

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

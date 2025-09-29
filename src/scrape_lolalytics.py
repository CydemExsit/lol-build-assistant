# -*- coding: utf-8 -*-
import argparse, csv, os, sys, time, math
from dataclasses import dataclass
from typing import List, Tuple
import pandas as pd

# Playwright
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

LANG = "zh_tw"
DEF_MODE = "aram"
DEF_TIER = "d2_plus"
DEF_PATCH = "7"

def _mkdir_for(path: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def _to_pct(s: str) -> float:
    """'67.03' -> 0.6703；容錯處理"""
    try:
        v = float(str(s).strip().replace("%",""))
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
    # 從檔名推（item64/3031.webp -> 3031）
    base = os.path.basename(src).split(".")[0]
    return base, src

def _goto_build_page(page, hero: str, mode: str, tier: str, patch: str, lang: str) -> str:
    url = f"https://lolalytics.com/{lang}/lol/{hero}/{mode}/build/?tier={tier}&patch={patch}"
    page.goto(url, wait_until="domcontentloaded")
    # 等待頁面主體出現
    page.wait_for_selector("div.my-1", timeout=30000)
    return url

def _parse_winning_items(page):
    import pandas as pd
    page.wait_for_selector("img[src*='/item64/']", timeout=30000)

    def _looks_like_items_container(candidate) -> bool:
        """檢查容器是否包含多列道具圖示與百分比"""
        try:
            return candidate.evaluate(
                """
                (root) => {
                    const rows = Array.from(root.querySelectorAll(':scope > *')).length
                        ? Array.from(root.querySelectorAll(':scope > *'))
                        : Array.from(root.children);
                    if (!rows.length) return false;

                    let ok = 0;
                    for (const row of rows) {
                        const imgs = row.querySelectorAll("img[src*='/item64/']");
                        if (!imgs.length) continue;

                        const texts = Array.from(row.querySelectorAll('*'))
                          .map(el => (el.textContent || '').trim())
                          .filter(Boolean);
                        const percents = texts.filter(t => t.includes('%'));
                        if (percents.length >= 2) {
                            ok += 1;
                            if (ok >= 2) return true;
                        }
                    }
                    return false;
                }
                """
            )
        except Exception:
            return False

    def _find_items_block(scope):
        # 嘗試在指定區塊內找到符合結構的容器
        for selector in [
            "css=:scope div.flex:has(img[src*='/item64/'])",
            "css=:scope div.grid:has(img[src*='/item64/'])",
            "css=:scope div:has(> div:has(img[src*='/item64/']))",
        ]:
            try:
                loc = scope.locator(selector)
            except Exception:
                continue
            try:
                count = loc.count()
            except Exception:
                count = 0
            for idx in range(count):
                cand = loc.nth(idx)
                if _looks_like_items_container(cand):
                    return cand
        if _looks_like_items_container(scope):
            return scope
        return None

    def _locate_from_section(section_selector: str):
        try:
            handle = page.wait_for_selector(section_selector, timeout=3000)
        except PWTimeout:
            return None
        except Exception:
            return None
        if not handle:
            return None
        section = page.locator(section_selector).first
        try:
            section.wait_for(state="visible", timeout=3000)
        except Exception:
            pass
        return _find_items_block(section)

    container = None
    # 先用較穩定的 data-* 區段鎖定
    for selector in [
        "[data-lolalytics-e2e='winning-items']",
        "[data-e2e='winning-items']",
        "[data-section='winning-items']",
        "[data-testid='winning-items']",
        "section[data-lolalytics-e2e-section='winning-items']",
    ]:
        container = _locate_from_section(selector)
        if container:
            break

    # 找不到就全頁掃描符合視覺結構的容器
    if container is None:
        candidates = page.locator("css=div:has(img[src*='/item64/'])")
        try:
            total = candidates.count()
        except Exception:
            total = 0
        for idx in range(total):
            cand = candidates.nth(idx)
            if _looks_like_items_container(cand):
                container = cand
                break

    if container is None:
        raise RuntimeError("winning items container not found")

    # 逐列解析
    rows = container.locator("css=:scope > *:has(img[src*='/item64/'])")
    if rows.count() == 0:
        rows = container.locator("css=:scope *:has(> img[src*='/item64/'])")

    data = []
    for i in range(rows.count()):
        row = rows.nth(i)
        img = row.locator("img[src*='/item64/']").first
        if img.count() == 0:
            continue
        name, src = _name_from_img(img)

        texts = [t.strip() for t in row.locator("xpath=.//*[contains(text(), '%')]").all_inner_texts() if t.strip()]
        rates = []
        for t in texts:
            v = _to_pct(t)
            if v > 0:
                rates.append(v)
        if len(rates) < 2:
            continue
        win_rate, pick_rate = rates[:2]
        data.append({"img": src, "name": name, "win_rate": win_rate, "pick_rate": pick_rate})

    return pd.DataFrame(data, columns=["img", "name", "win_rate", "pick_rate"])

def _click_sets_five(page) -> None:
    """
    在 Actually Built Sets 區塊點選「5」。
    有些情況 SSR 只渲染 3，需要點一下才會更新到 5。
    """
    try:
        # 直接找 data-type="a_5" 的按鈕
        btn = page.locator('[data-type="a_5"]').first
        if btn and btn.count() > 0:
            btn.click()
            # 等待內容刷新（等到一列裡至少出現 data-id="4_*" 的圖示）
            page.wait_for_selector("img[data-id^='4_']", timeout=5000)
            time.sleep(0.15)
    except PWTimeout:
        pass
    except Exception:
        pass

def _parse_sets_5(page) -> pd.DataFrame:
    """
    抓 Actually Built Sets（5件）。
    依據 data-id="0_* ... 4_*" 來識別每一列的五件物品。
    """
    # 先嘗試點到 5
    _click_sets_five(page)

    # 以「每列的第一張 data-id^=0_ 的圖」來鎖定一列
    # 並確保該列同時含有 1_~4_ 的圖片
    candidates = page.locator("img[data-id^='0_']").all()
    out = []
    for img0 in candidates:
        # 找到包含這張圖的最接近父層 div（列容器）
        row = img0.locator("xpath=ancestor::div[1]")
        # 放大到含有五張 data-id 的那層
        for _ in range(4):
            ok_row = all(row.locator(f"img[data-id^='{k}_']").count() > 0 for k in range(5))
            if ok_row:
                break
            row = row.locator("xpath=ancestor::div[1]")

        # 最後確認一次
        ok = all(row.locator(f"img[data-id^='{k}_']").count() > 0 for k in range(5))
        if not ok:
            continue

        imgs = [row.locator(f"img[data-id^='{k}_']").first for k in range(5)]
        names = []
        for q in imgs:
            n, _ = _name_from_img(q)
            names.append(n)

        win_el  = row.locator(".//div[contains(@class,'my-1')][not(contains(@class,'text-[#939bf6]'))]").first
        pick_el = row.locator(".//div[contains(@class,'my-1') and contains(@class,'text-[#939bf6]')]").first
        n_el    = row.locator(".//div[contains(@class,'my-1') and contains(@class,'text-[9px]') and contains(@class,'text-[#bbb]')]").first

        win = _to_pct(_text_of(win_el))
        pick = _to_pct(_text_of(pick_el))
        sample = _text_of(n_el).replace(",","")
        try:
            sample = int(sample) if sample else 0
        except:
            sample = 0

        out.append({
            "items": "|".join(names),
            "set_win_rate": win,
            "set_pick_rate": pick,
            "set_sample_size": sample,
        })

    # 去重（有時候不同容器層抓到同一列）
    if out:
        df = pd.DataFrame(out).drop_duplicates(subset=["items"], keep="first").reset_index(drop=True)
    else:
        df = pd.DataFrame(columns=["items","set_win_rate","set_pick_rate","set_sample_size"])
    return df

def scrape(hero: str, mode: str, tier: str, patch: str, lang: str, no_headless: bool=False):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not no_headless)
        ctx = browser.new_context()
        page = ctx.new_page()
        url = _goto_build_page(page, hero, mode, tier, patch, lang)

        # 解析 Winning Items
        win_df = _parse_winning_items(page)

        # 解析 Actually Built Sets（5）
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
    # main() 寫完 CSV 前/後做檢查（兩者都要有資料才算成功）
    if win_df.empty:
        print("[error] winning items empty"); import sys; sys.exit(2)
    if set_df.empty:
        print("[error] actually built sets empty"); import sys; sys.exit(3)

if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
Lolalytics 抓取器：Winning Items 與 Actually Built Sets（a_5）。
重點修正：
1) 針對少數英雄（如 Lux）a_5 區塊不回應 scrollLeft 的情況，新增第二種翻頁機制：
   直接調整內層 list 的 style.paddingLeft，每次 +378px，並觸發 scroll/resize 事件。
2) 兩種機制並用：先嘗試 scroller.scrollLeft，失敗再改 padding-left；都失敗連續多次則停止。
3) 避免使用無效 CSS 選擇器（如 .gap-[6px]），改以 XPath/通用 traversing 尋找容器。
4) 若 <img> 無 alt，回退以 /item64/{id}.webp 中的 {id} 當名稱，避免 sets 第一欄空白。
5) 比例欄位只去掉 % 與逗號，不做 0~1 縮放（保持原頁面數值，例如 0.81 而非 0.0081）。

執行示例：
  powershell -File .\scripts\build_batch.ps1 -Heroes lux
  powershell -File .\scripts\build_batch.ps1 -Heroes ezreal
  # 除錯觀察：
  python src/scrape_lolalytics.py --hero lux --winning_out data/raw/lux_aram_d2_plus_7d_winning.csv \
      --sets_out data/raw/lux_aram_d2_plus_7d_sets.csv --no-headless
"""

from __future__ import annotations
import argparse, os, time, re
from typing import List, Dict, Any, Tuple
import pandas as pd
from playwright.sync_api import sync_playwright, Page, Locator

LANG = "zh_tw"
DEF_MODE = "aram"
DEF_TIER = "d2_plus"
DEF_PATCH = "7"

SCROLL_STEP = 378
SCROLL_PAUSE_MS = 160
MAX_SCROLL_STEPS = 800
MAX_STALL = 6

ID_RE = re.compile(r"/item64/(\d+)\.webp$", re.IGNORECASE)

# ---------- utils ----------

def _mkdir_for(path: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def _to_num(s: str):
    try:
        t = str(s).strip().replace('%','').replace(',','')
        return float(t) if t else None
    except Exception:
        return None


def _attr(el, name: str) -> str:
    try:
        v = el.get_attribute(name)
        return v or ""
    except Exception:
        return ""


def _id_from_src(src: str) -> str:
    m = ID_RE.search(src or "")
    return m.group(1) if m else ""

# ---------- navigation ----------

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

# ---------- winning items ----------

def _parse_winning_items(page: Page) -> pd.DataFrame:
    block = page.locator(
        "xpath=//div[contains(@class,'flex') and contains(@class,'h-[128px]') and contains(@class,'mb-2') and contains(@class,'border')"
        " and .//div[@class='my-1' and normalize-space()='Winning']"
        " and .//div[@class='my-1' and normalize-space()='Items']]"
    ).first

    try:
        block.wait_for(state="visible", timeout=10000)
    except Exception:
        return pd.DataFrame(columns=["img","name","win_rate","pick_rate","sample_size"])

    block.scroll_into_view_if_needed()
    scroller = block.locator("xpath=.//div[contains(@class,'overflow-x-scroll')]").first
    try:
        scroller.wait_for(state="visible", timeout=10000)
    except Exception:
        return pd.DataFrame(columns=["img","name","win_rate","pick_rate","sample_size"])

    def _extract_rows():
        return scroller.evaluate(
            r"""
            (el) => {
              const out = [];
              const idFromSrc = (s) => { const m = /\/item64\/(\d+)\.webp$/i.exec(s||""); return m? m[1] : "" };
              let container = null;
              for (const c of Array.from(el.querySelectorAll('div'))) {
                const kids = Array.from(c.children || []);
                const hasMany = kids.filter(r => r.querySelector("img[src*='/item64/']")).length;
                if (hasMany >= 5) { container = c; break; }
              }
              if (!container) return out;
              for (const row of Array.from(container.children)) {
                const img = row.querySelector("img[src*='/item64/']");
                if (!img) continue;
                const alt = (img.getAttribute('alt')||'').trim();
                const name = alt ? alt : idFromSrc(img.getAttribute('src')||'');
                const nums = Array.from(row.querySelectorAll("div.my-1"))
                  .map(e => (e.textContent || "").trim())
                  .filter(Boolean);
                const win  = nums[0] || "";
                const pick = nums[1] || "";
                out.push({ src: img.getAttribute('src') || "", name, win, pick });
              }
              return out;
            }
            """
        )

    seen_src = set(); data = []
    try:
        scroller.evaluate("(el) => { el.scrollLeft = 1; el.dispatchEvent(new Event('scroll', {bubbles:true})); }")
    except Exception:
        pass
    page.wait_for_timeout(200)

    for _ in range(60):
        rows = _extract_rows(); new_added = 0
        for r in rows:
            key = r.get("src","")
            if not key or key in seen_src:
                continue
            seen_src.add(key)
            win_rate  = _to_num(r.get("win",""))
            pick_rate = _to_num(r.get("pick",""))
            name = (r.get("name") or "").strip() or _id_from_src(key)
            data.append({"img": key, "name": name, "win_rate": win_rate, "pick_rate": pick_rate, "sample_size": 0})
            new_added += 1
        consts = scroller.evaluate(
            r"""
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
        before, after, _total = consts
        if after == before and new_added == 0:
            break

    cols = ["img","name","win_rate","pick_rate","sample_size"]
    return pd.DataFrame(data, columns=cols) if data else pd.DataFrame(columns=cols)

# ---------- sets (a_5) ----------

def _click_sets_five(page: Page) -> None:
    try:
        a5 = page.locator("[data-type='a_5']").first
        if a5 and a5.count() > 0:
            a5.click()
            page.wait_for_selector("img[data-id^='4_']", timeout=5000)
            time.sleep(0.15)
    except Exception:
        pass


def _find_sets_scroller(page: Page) -> Tuple[Locator|None, Locator|None]:
    # 用 XPath 避免 .gap-[6px] 的 CSS 解析問題
    scrollers = page.locator(
        "xpath=//div[contains(@class,'overflow-x-scroll') and .//div[contains(@class,'gap-[6px]') and contains(@class,'text-center') and contains(@style,'padding-left')]]"
    )
    cnt = scrollers.count() if scrollers else 0
    for i in range(cnt):
        sc = scrollers.nth(i)
        try:
            ok = sc.evaluate(
                r"""
                (el) => {
                  return Array.from(el.querySelectorAll('div')).some(row =>
                    [0,1,2,3,4].every(k => row.querySelector(`img[data-id^='${k}_']`))
                  );
                }
                """
            )
        except Exception:
            ok = False
        if ok:
            inner = sc.locator("xpath=.//div[contains(@class,'gap-[6px]') and contains(@class,'text-center') and contains(@style,'padding-left')]").first
            return sc, inner
    return None, None


def _extract_visible_sets(scroller: Locator) -> List[Dict[str, Any]]:
    rows = scroller.evaluate(
        r"""
        (el) => {
          const out = [];
          const idFromSrc = (s) => { const m = /\/item64\/(\d+)\.webp$/i.exec(s||""); return m? m[1] : "" };
          let container = null;
          for (const c of Array.from(el.querySelectorAll('div'))) {
            const kids = Array.from(c.children || []);
            const cnt = kids.filter(r => r.querySelector("img[data-id^='0_']")).length;
            if (cnt >= 1) { container = c; break; }
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
            const names  = imgs.map(i => {
              const alt = (i.getAttribute('alt')||'').trim();
              return alt ? alt : idFromSrc(i.getAttribute('src')||'');
            });
            const images = imgs.map(i => i.getAttribute('src') || '');
            if (names.some(n => !n)) continue;
            const nums = Array.from(row.querySelectorAll("div.my-1"))
              .map(e => (e.textContent || "").trim())
              .filter(Boolean)
              .map(t => parseFloat(t.replace('%','').replace(',','')))
              .filter(v => Number.isFinite(v));
            const win   = (nums.length>0 ? nums[0] : 0);
            const pick  = (nums.length>1 ? nums[1] : 0);
            const games = (nums.length>2 ? Math.round(nums[2]) : 0);
            out.push({ names, images, win, pick, sample: games });
          }
          return out;
        }
        """
    )
    return rows or []


def _advance_sets_page(page: Page, scroller: Locator, inner: Locator|None) -> bool:
    # 先嘗試 scrollLeft
    try:
        before, after, maxw = scroller.evaluate(
            r"""
            (el, step) => {
              const before = el.scrollLeft;
              const max = Math.max(0, el.scrollWidth - el.clientWidth);
              const next = Math.min(before + step, max);
              el.scrollLeft = next;
              el.dispatchEvent(new Event('scroll', {bubbles:true}));
              return [before, el.scrollLeft, max];
            }
            """,
            SCROLL_STEP,
        )
        if after != before:
            return True
    except Exception:
        pass

    # 再嘗試 padding-left（Lux 等個案）
    if inner is not None:
        try:
            moved = scroller.evaluate(
                r"""
                (el, step) => {
                  let list = null;
                  for (const d of Array.from(el.querySelectorAll('div'))) {
                    const st = d.getAttribute('style') || '';
                    if (st.includes('padding-left')) { list = d; break; }
                  }
                  if (!list) return false;
                  const curStr = list.style.paddingLeft || (list.getAttribute('style')||'');
                  const m = /padding-left:\s*([\-\d\.]+)px/i.exec(curStr);
                  const cur = m ? parseFloat(m[1]) : 0;
                  const next = cur + step;
                  list.style.paddingLeft = `${next}px`;
                  el.dispatchEvent(new Event('scroll', {bubbles:true}));
                  window.dispatchEvent(new Event('resize'));
                  return next !== cur;
                }
                """,
                SCROLL_STEP,
            )
            return bool(moved)
        except Exception:
            return False
    return False


def _collect_sets_from_scoped(imgs0_locator: Locator) -> pd.DataFrame:
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
            src = _attr(q, "src"); alt = (_attr(q, "alt") or "").strip()
            name = alt or _id_from_src(src)
            names.append(name); imgs.append(src)
            if src.endswith("/2003.webp") or src.endswith("/2031.webp"):
                skip = True
        if skip or any(n == "" for n in names):
            continue
        key = "|".join(names)
        if key in seen:
            continue
        seen.add(key)
        texts = [t.strip() for t in row.locator("xpath=.//div[contains(@class,'my-1')]").all_inner_texts() if t.strip()]
        nums = []
        for t in texts:
            try:
                nums.append(float(t.replace('%','').replace(',','')))
            except Exception:
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


def _parse_sets_5(page: Page) -> pd.DataFrame:
    _click_sets_five(page)
    try:
        _mkdir_for("data/raw/page_last.html")
        with open("data/raw/page_last.html","w",encoding="utf-8") as f:
            f.write(page.content())
    except Exception:
        pass

    scroller, inner = _find_sets_scroller(page)
    if not scroller:
        # 無水平 scroller，退而求其次：抓可視區域
        imgs0 = page.locator("css=img[data-id^='0_']")
        try:
            total = imgs0.count()
        except Exception:
            total = 0
        if total == 0:
            return pd.DataFrame(columns=["items","items_img","set_win_rate","set_pick_rate","set_sample_size"])
        return _collect_sets_from_scoped(imgs0)

    seen_key = set(); out: List[Dict[str, Any]] = []
    stall = 0; last_seen_count = 0

    # 先觸發一次 scroll 以讓 Qwik 佈局（某些英雄需要）
    try:
        scroller.evaluate("(el)=>{ el.scrollLeft = Math.max(el.scrollLeft, 1); el.dispatchEvent(new Event('scroll', {bubbles:true})); }")
        page.wait_for_timeout(120)
    except Exception:
        pass

    for _ in range(MAX_SCROLL_STEPS):
        rows = _extract_visible_sets(scroller)
        new_added = 0
        for r in rows:
            names = r.get("names", []); images = r.get("images", [])
            if len(names) != 5 or len(images) != 5:
                continue
            if any((src or '').endswith("/2003.webp") or (src or '').endswith("/2031.webp") for src in images):
                continue
            key = "|".join(names)
            if key in seen_key:
                continue
            seen_key.add(key)
            win = float(r.get("win",0) or 0); pick = float(r.get("pick",0) or 0); games = int(r.get("sample",0) or 0)
            out.append({
                "items": key,
                "items_img": "|".join(images),
                "set_win_rate": win,
                "set_pick_rate": pick,
                "set_sample_size": games,
            })
            new_added += 1
        moved = _advance_sets_page(page, scroller, inner)
        page.wait_for_timeout(SCROLL_PAUSE_MS)

        if new_added == 0 and not moved:
            stall += 1
        else:
            stall = 0
        if stall >= MAX_STALL:
            break
        # 若長時間沒有增加，提前結束
        if len(seen_key) == last_seen_count and not moved:
            break
        last_seen_count = len(seen_key)

    cols = ["items","items_img","set_win_rate","set_pick_rate","set_sample_size"]
    if not out:
        # 保底：再嘗試一次可視區域採集
        imgs0 = page.locator("css=img[data-id^='0_']")
        try:
            total = imgs0.count()
        except Exception:
            total = 0
        if total > 0:
            return _collect_sets_from_scoped(imgs0)
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
    ap.add_argument("--no-headless", action="store_true")
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

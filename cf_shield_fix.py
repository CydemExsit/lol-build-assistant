# -*- coding: utf-8 -*-
"""
cf_shield_fix.py

診斷：你的請求被 Cloudflare 擋下，頁面回傳的是「Sorry, you have been blocked」。
這支工具做兩件事：
1) bootstrap：用可視瀏覽器人工通過 Cloudflare，將 cookie 存成 storage state。
2) test：帶著 storage state 開啟指定英雄頁，檢測是否仍被擋。

整合方式：拿到可用的 storage state 後，把你的主程式的 new_context 改成使用 storage_state 路徑即可。

用法：
  # 第一步：人工通過（會開視窗）
  python cf_shield_fix.py bootstrap --hero lux --lang zh_tw --mode aram --tier d2_plus --patch 7 --state data/cf_state.json

  # 第二步：驗證 cookie 是否生效（無頭）
  python cf_shield_fix.py test --hero lux --lang zh_tw --mode aram --tier d2_plus --patch 7 --state data/cf_state.json

  # 你的程式中引用（示意）：
  ctx = browser.new_context(locale=lang.replace('_','-'), viewport={"width":1440,"height":2200}, storage_state="data/cf_state.json")

注意：若 IP / 指紋被封，需更換出口 IP（住宅代理），或降低併發與頻率。
"""
import argparse, json, os, sys, time
from typing import Optional
from playwright.sync_api import sync_playwright, Page

# ---------------- util ----------------

def _url(lang: str, hero: str, mode: str, tier: str, patch: str) -> str:
    return f"https://lolalytics.com/{lang}/lol/{hero}/{mode}/build/?tier={tier}&patch={patch}"

CF_MARKERS = (
    "Attention Required! | Cloudflare",
    "cf-error-details",
    "Sorry, you have been blocked",
)


def _is_cf_block(page: Page) -> bool:
    try:
        if any(k in (page.title() or "") for k in CF_MARKERS):
            return True
    except Exception:
        pass
    try:
        if page.locator('#cf-error-details').count() > 0:
            return True
    except Exception:
        pass
    try:
        html = page.content()
        if any(k in html for k in CF_MARKERS):
            return True
    except Exception:
        pass
    return False


def _visit(page: Page, url: str) -> bool:
    page.goto(url, wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=45000)
    except Exception:
        pass
    return not _is_cf_block(page)

# ---------------- cmds ----------------

def cmd_bootstrap(args):
    """開啟可視視窗，讓你人工通過 Cloudflare，存下 cookie。"""
    state_path = args.state
    os.makedirs(os.path.dirname(state_path) or ".", exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])  # 可視
        ctx = browser.new_context(
            locale=args.lang.replace('_','-'),
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Upgrade-Insecure-Requests": "1",
            },
        )
        page = ctx.new_page()
        ok = _visit(page, _url(args.lang, args.hero, args.mode, args.tier, args.patch))
        print("[info] initial ok=", ok, "title=", page.title())
        print("[info] 若畫面顯示 Cloudflare 阻擋，請在此視窗內完成驗證或等候自動放行。")
        input("[info] 驗證完成後按 Enter 以保存 cookie → ")
        ctx.storage_state(path=state_path)
        print("[ok] storage saved:", state_path)
        ctx.close(); browser.close()


def cmd_test(args):
    state_path = args.state
    if not os.path.exists(state_path):
        print("[error] storage not found:", state_path)
        sys.exit(2)
    with sync_playwright() as p:
        # 優先用 chromium；失敗再試 webkit 作對照
        engines = [(p.chromium, "chromium"), (p.webkit, "webkit")]
        success = False
        for engine, name in engines:
            browser = engine.launch(headless=True)
            ctx = browser.new_context(
                locale=args.lang.replace('_','-'),
                viewport={"width":1440,"height":2200},
                storage_state=state_path,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                extra_http_headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Upgrade-Insecure-Requests": "1",
                },
            )
            page = ctx.new_page()
            ok = _visit(page, _url(args.lang, args.hero, args.mode, args.tier, args.patch))
            print(f"[test] engine={name} ok={ok} title={page.title()!r}")
            if ok:
                success = True
            ctx.close(); browser.close()
        if not success:
            print("[hint] 仍被擋：")
            print(" - 換一個來源 IP（住宅代理/不同網路）")
            print(" - 減少併發與頻率，加入隨機等待")
            print(" - 重新執行 bootstrap 取得新 storage state")

# ---------------- main ----------------
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    s1 = sub.add_parser("bootstrap", help="可視化通過 Cloudflare 並保存 cookie")
    s1.add_argument("--hero", required=True)
    s1.add_argument("--lang", default="zh_tw")
    s1.add_argument("--mode", default="aram")
    s1.add_argument("--tier", default="d2_plus")
    s1.add_argument("--patch", default="7")
    s1.add_argument("--state", default="data/cf_state.json")
    s1.set_defaults(func=cmd_bootstrap)

    s2 = sub.add_parser("test", help="帶 storage state 測試是否仍被 Cloudflare 擋")
    s2.add_argument("--hero", required=True)
    s2.add_argument("--lang", default="zh_tw")
    s2.add_argument("--mode", default="aram")
    s2.add_argument("--tier", default="d2_plus")
    s2.add_argument("--patch", default="7")
    s2.add_argument("--state", default="data/cf_state.json")
    s2.set_defaults(func=cmd_test)

    args = ap.parse_args(); args.func(args)

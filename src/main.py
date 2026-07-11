import argparse
import json
import sys
from pathlib import Path
from .pipeline import run
from .live_client import build_match_context, capture_snapshot, load_snapshot
from .recommend import recommend_from_snapshot
from .lolalytics import DEFAULT_TIER


def _configure_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _write_recommendation_markdown(result: dict, out_md: str | Path) -> None:
    active = result.get("active_player") or {}
    source = result.get("build", {}).get("source", {})
    boot_options = result.get("build", {}).get("boot_options", [])
    routes = result.get("build", {}).get("routes", [])
    lines = [
        "# LoL Build Assistant 推薦",
        "",
        f"- 英雄：{active.get('champion_id') or active.get('champion_name')} ({active.get('position')})",
        f"- 模式：{(source.get('lolalytics_params') or {}).get('mode', 'aram')}",
        f"- LoLalytics：{source.get('lolalytics_url')}",
        f"- Champions Analysed：{source.get('champions_analysed'):,}" if source.get("champions_analysed") else "- Champions Analysed：未知",
        f"- 成套限制：{source.get('built_sets_tab', 'Actually Built Sets: 5')}，五件非鞋成裝必須同時出現在該表",
        "",
        "## 敵方陣容",
        "",
    ]
    for enemy in result.get("enemy_team", []):
        lines.append(f"- {enemy.get('champion')} ({enemy.get('position')})")
    lines.extend(["", "## 鞋子選擇", ""])
    for boot_index, boot in enumerate(boot_options, start=1):
        boot_display = boot.get("display_name") or boot.get("zh_tw_name") or boot.get("name")
        win_rate = f"{boot.get('win_rate') * 100:.2f}%" if isinstance(boot.get("win_rate"), (int, float)) else "-"
        pick_rate = f"{boot.get('pick_rate') * 100:.2f}%" if isinstance(boot.get("pick_rate"), (int, float)) else "-"
        games = f"{int(boot.get('games')):,}" if isinstance(boot.get("games"), int) else "-"
        lines.append(
            f"{boot_index}. {boot_display} / {boot.get('name')} (`{boot.get('item_id')}`) "
            f"- 勝率 {win_rate} / 選取率 {pick_rate} / 場次 {games}"
        )
    lines.extend(["", "## 推薦五件套路線", ""])
    for route_index, route in enumerate(routes, start=1):
        stats = route.get("set_stats") or {}
        params = (route.get("source") or {}).get("lolalytics_params") or {}
        lines.append(f"### 路線 {route_index}：{route.get('label')}")
        lines.append("")
        item_names = [
            f"{item.get('display_name') or item.get('zh_tw_name') or item.get('name')} (`{item.get('item_id')}`)"
            for item in route.get("items", [])
        ]
        lines.append(f"- 五件成裝：{' > '.join(item_names)}")
        for reminder in route.get("starting_reminders", []):
            lines.append(f"- 開場提醒：{reminder}")
        if stats:
            lines.append(
                "- LoLalytics set："
                f"勝率 {(stats.get('win_rate') or 0) * 100:.2f}% / "
                f"選取率 {(stats.get('pick_rate') or 0) * 100:.2f}% / "
                f"{int(stats.get('games') or 0):,} 場 / "
                f"window={params.get('patch', '7')}"
            )
        for reason in route.get("reasons", []):
            lines.append(f"- {reason}")
        lines.append("")
    lines.extend(
        [
            "## 合規邊界",
            "",
            "- 只使用 Riot 本機 Live Client Data API 的遊戲內可見資料。",
            "- 不分析敵方玩家個人帳號、牌位、勝率或歷史戰績。",
            "- 不自動操作遊戲、不讀記憶體、不繞過 Riot / Vanguard。",
        ]
    )
    out_path = Path(out_md)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_legacy_args(argv: list[str] | None = None):
    p = argparse.ArgumentParser()
    p.add_argument("--winning", required=True)
    p.add_argument("--sets", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--explain", action="store_true")
    p.add_argument("--topk", type=int, default=50)
    p.add_argument("--cover", type=float, default=0.80)
    return p.parse_args(argv)


def parse_args(argv: list[str] | None = None):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)

    snap = sub.add_parser("snapshot-live", help="capture Riot Live Client Data API JSON")
    snap.add_argument("--out-dir", default=None)
    snap.add_argument("--timeout", type=float, default=5.0)

    ctx = sub.add_parser("context", help="build match context JSON from a live snapshot")
    ctx.add_argument("--snapshot", required=True)
    ctx.add_argument("--out", required=True)

    rec = sub.add_parser("recommend-live", help="recommend a build from a live snapshot")
    rec.add_argument("--snapshot", default=None, help="snapshot directory; captures live data when omitted")
    rec.add_argument("--out", default="data/processed/live_recommendation.json")
    rec.add_argument("--out-md", default="data/processed/live_recommendation.md")
    rec.add_argument("--refresh-lolalytics", action="store_true")
    rec.add_argument("--mode", default="aram", help="LoLalytics mode; default is aram")
    rec.add_argument("--tier", default=DEFAULT_TIER, help=f"LoLalytics tier; default is {DEFAULT_TIER}")
    rec.add_argument("--min-champions-analysed", type=int, default=1_000_000)

    serve = sub.add_parser("serve", help="start local web UI")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--out", default="data/processed/live_recommendation.json")
    serve.add_argument("--mode", default="aram")
    serve.add_argument("--tier", default=DEFAULT_TIER)
    serve.add_argument("--min-champions-analysed", type=int, default=1_000_000)
    serve.add_argument("--refresh-lolalytics", action="store_true")

    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    _configure_stdout()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0].startswith("--"):
        args = parse_legacy_args(argv)
        run(args.winning, args.sets, args.out, explain=args.explain, topk=args.topk, cover=args.cover)
        return

    args = parse_args(argv)
    if args.command == "snapshot-live":
        path = capture_snapshot(out_dir=args.out_dir, timeout=args.timeout)
        print(f"[ok] snapshot -> {path}")
        return

    if args.command == "context":
        context = build_match_context(load_snapshot(args.snapshot), source_path=args.snapshot)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(context, f, ensure_ascii=False, indent=2)
        active = context.get("active_player") or {}
        print(f"[ok] context -> {args.out}")
        print(f"[ok] active champion -> {active.get('champion_id') or active.get('champion_name')}")
        return

    if args.command == "recommend-live":
        snapshot = args.snapshot
        if snapshot is None:
            try:
                snapshot = str(capture_snapshot())
            except Exception as exc:
                raise SystemExit(
                    "[error] Riot Live Client Data API is not available at https://127.0.0.1:2999.\n"
                    "        請確認你已經進入 loading 畫面或遊戲內；只在 client/lobby/選角時通常抓不到。\n"
                    f"        detail: {exc}"
                )
            print(f"[ok] snapshot -> {snapshot}")
        result = recommend_from_snapshot(
            snapshot,
            out_path=args.out,
            refresh_lolalytics=args.refresh_lolalytics,
            mode=args.mode,
            tier=args.tier,
            min_champions_analysed=args.min_champions_analysed,
        )
        _write_recommendation_markdown(result, args.out_md)
        print(f"[ok] recommendation -> {args.out}")
        print(f"[ok] readable report -> {args.out_md}")
        primary = (result.get("build", {}).get("routes") or [{}])[0]
        boot_options = result.get("build", {}).get("boot_options") or []
        if boot_options:
            print("[ok] boot options -> " + " | ".join(boot.get("display_name") or boot.get("name") for boot in boot_options))
        print("[ok] 5-item set -> " + " > ".join(item.get("display_name") or item["name"] for item in primary.get("items", [])))
        if len(result.get("build", {}).get("routes", [])) > 1:
            labels = " | ".join(route.get("label", "route") for route in result["build"]["routes"])
            print(f"[ok] routes -> {labels}")
        return

    if args.command == "serve":
        from .server import serve

        serve(
            host=args.host,
            port=args.port,
            out_path=args.out,
            mode=args.mode,
            tier=args.tier,
            min_champions_analysed=args.min_champions_analysed,
            refresh_lolalytics=args.refresh_lolalytics,
        )
        return

if __name__ == "__main__":
    main()

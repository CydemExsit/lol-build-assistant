from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .autostart import autostart_status, install_autostart, remove_autostart
from .data_dragon import update_static_data
from .evaluation import audit_file
from .live_client import build_match_context, capture_snapshot, load_snapshot
from .lolalytics import DEFAULT_TIER
from .maintenance import apply_cleanup_plan, build_cleanup_plan, format_bytes
from .service import RecommendationService


def _configure_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _add_recommendation_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out", default="data/processed/live_recommendation.json")
    parser.add_argument("--out-md", default="data/processed/live_recommendation.md")
    parser.add_argument("--mode", default="aram")
    parser.add_argument("--tier", default=DEFAULT_TIER)
    parser.add_argument("--min-champions-analysed", type=int, default=1_000_000)
    parser.add_argument("--refresh-lolalytics", action="store_true")
    parser.add_argument("--cache-max-age-hours", type=int, default=168)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Static pre-game ARAM build assistant")
    commands = parser.add_subparsers(dest="command", required=True)

    snapshot = commands.add_parser("snapshot-live", help="capture a sanitized static snapshot")
    snapshot.add_argument("--out-dir", default=None)
    snapshot.add_argument("--timeout", type=float, default=5.0)

    context = commands.add_parser("context", help="build match context JSON from a snapshot")
    context.add_argument("--snapshot", required=True)
    context.add_argument("--out", required=True)

    recommend = commands.add_parser("recommend-live", help="generate one frozen recommendation")
    recommend.add_argument("--snapshot", default=None)
    _add_recommendation_options(recommend)

    serve = commands.add_parser("serve", help="start the browser UI without match detection")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    _add_recommendation_options(serve)

    watch = commands.add_parser("watch", help="start UI and detect new matches automatically")
    watch.add_argument("--host", default="127.0.0.1")
    watch.add_argument("--port", type=int, default=8765)
    watch.add_argument("--poll-interval", type=float, default=3.0)
    watch.add_argument(
        "--auto-open",
        action="store_true",
        help="open the UI once for a detected match (disabled by default)",
    )
    _add_recommendation_options(watch)

    sync = commands.add_parser("sync-data", help="refresh Riot Data Dragon static metadata")
    sync.add_argument("--force", action="store_true")

    startup = commands.add_parser("autostart", help="manage Windows sign-in startup")
    startup.add_argument("action", choices=("install", "remove", "status"))

    audit = commands.add_parser("audit", help="audit a frozen recommendation")
    audit.add_argument(
        "--recommendation",
        default="data/processed/live_recommendation.json",
    )

    cleanup = commands.add_parser("cleanup", help="preview or apply the storage policy")
    cleanup.add_argument("--keep-snapshots", type=int, default=5)
    cleanup.add_argument("--apply", action="store_true")

    return parser.parse_args(argv)


def _service_from_args(args: argparse.Namespace) -> RecommendationService:
    return RecommendationService(
        out_path=args.out,
        out_markdown_path=args.out_md,
        mode=args.mode,
        tier=args.tier,
        min_champions_analysed=args.min_champions_analysed,
        refresh_lolalytics=args.refresh_lolalytics,
        cache_max_age_hours=args.cache_max_age_hours,
    )


def _print_recommendation(result: dict, out: str, out_md: str) -> None:
    print(f"[ok] recommendation -> {out}")
    print(f"[ok] readable report -> {out_md}")
    routes = result.get("build", {}).get("routes") or []
    boots = result.get("build", {}).get("boot_options") or []
    if boots:
        print("[ok] boot options -> " + " | ".join(boot.get("display_name") or boot.get("name") for boot in boots))
    if routes:
        print("[ok] routes -> " + " | ".join(route.get("label", "route") for route in routes))
    print("[ok] result is frozen for this match and will not change during play")


def main(argv: list[str] | None = None) -> None:
    _configure_stdout()
    args = parse_args(argv)

    if args.command == "cleanup":
        plan = build_cleanup_plan(keep_snapshots=args.keep_snapshots)
        for entry in plan.entries:
            relative = entry.path.relative_to(plan.root)
            print(f"- {relative} ({format_bytes(entry.size_bytes)}): {entry.reason}")
        print(f"[plan] {len(plan.entries)} paths / {format_bytes(plan.total_bytes)}")
        if not args.apply:
            print("[dry-run] no files removed; add --apply to execute")
            return
        removed = apply_cleanup_plan(plan)
        print(f"[ok] removed {len(removed.entries)} paths / {format_bytes(removed.total_bytes)}")
        return

    if args.command == "snapshot-live":
        path = capture_snapshot(out_dir=args.out_dir, timeout=args.timeout)
        print(f"[ok] sanitized snapshot -> {path}")
        return

    if args.command == "context":
        context = build_match_context(load_snapshot(args.snapshot), source_path=args.snapshot)
        Path(args.out).write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
        active = context.get("active_player") or {}
        print(f"[ok] context -> {args.out}")
        print(f"[ok] active champion -> {active.get('champion_id') or active.get('champion_name')}")
        return

    if args.command == "recommend-live":
        service = _service_from_args(args)
        try:
            if args.snapshot:
                result = service.recommend_snapshot(args.snapshot)
            else:
                snapshot, result = service.capture_and_recommend()
                print(f"[ok] sanitized snapshot -> {snapshot}")
        except Exception as exc:
            raise SystemExit(
                "[error] 無法產生本場方案。請確認已進入 loading 畫面或遊戲內，"
                "且本機 127.0.0.1:2999 可用。\n"
                f"        detail: {exc}"
            ) from exc
        _print_recommendation(result, args.out, args.out_md)
        return

    if args.command == "serve":
        from .server import serve

        serve(host=args.host, port=args.port, service=_service_from_args(args))
        return

    if args.command == "watch":
        from .watcher import run_assistant

        run_assistant(
            host=args.host,
            port=args.port,
            poll_interval=args.poll_interval,
            auto_open=args.auto_open,
            service=_service_from_args(args),
        )
        return

    if args.command == "sync-data":
        result = update_static_data(force=args.force)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "autostart":
        if args.action == "install":
            path = install_autostart()
            print(f"[ok] Windows 登入啟動已安裝 -> {path}")
        elif args.action == "remove":
            print("[ok] Windows 登入啟動已移除" if remove_autostart() else "[ok] 尚未安裝")
        else:
            print(json.dumps(autostart_status(), ensure_ascii=False, indent=2))
        return

    if args.command == "audit":
        report = audit_file(args.recommendation)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report["passed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()

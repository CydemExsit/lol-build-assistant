#!/usr/bin/env python3
"""Minimal end-to-end runner for a single hero."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.snapshot_loader import load_snapshot
from src.pipeline import run as run_pipeline
from src.render_build import render_markdown

DEF_MODE = "aram"
DEF_TIER = "d2_plus"
DEF_PATCH = "7d"
DEFAULT_LANG = "zh_tw"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Generate one ARAM loadout from offline snapshots or live scrape")
    ap.add_argument("--hero", required=True, help="Champion slug used by Lolalytics, e.g. varus")
    ap.add_argument("--mode", default=DEF_MODE, help=f"Game mode (default: {DEF_MODE})")
    ap.add_argument("--lang", default=DEFAULT_LANG, help=f"Locale slug (default: {DEFAULT_LANG})")
    ap.add_argument("--tier", default=DEF_TIER, help=f"Rank segment (default: {DEF_TIER})")
    ap.add_argument("--patch", default=DEF_PATCH, help=f"Time window or patch (default: {DEF_PATCH})")
    ap.add_argument("--out", default="data/processed", help="Directory for generated CSV/JSON")
    ap.add_argument("--topk", type=int, default=50, help="Candidate set size for the scoring algorithm")
    ap.add_argument("--cover", type=float, default=0.80, help="Pickrate coverage threshold")
    ap.add_argument("--md-topk", type=int, default=8, help="Number of sets to show in the Markdown table")
    ap.add_argument("--no-headless", action="store_true", help="Open a visible browser window during live scrape")
    ap.add_argument("--no-explain", dest="explain", action="store_false", help="Skip rationale in output JSON")
    ap.add_argument("--input-dir", help="Offline snapshot directory (defaults to snapshots/<hero>)")
    ap.add_argument("--online", dest="offline", action="store_false", help="Use Playwright to fetch live data")
    ap.add_argument("--offline", dest="offline", action="store_true", help="Force offline snapshot mode")
    ap.set_defaults(explain=True, offline=True)
    return ap.parse_args()


def _run_scrape(args: argparse.Namespace) -> Tuple:
    from src.scrape_lolalytics import scrape  # imported lazily to avoid Playwright dependency offline

    return scrape(
        args.hero,
        args.mode,
        args.tier,
        args.patch,
        args.lang,
        no_headless=args.no_headless,
    )


def main() -> None:
    args = parse_args()

    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    prefix = f"{args.hero}_{args.mode}_{args.tier}_{args.patch}"
    winning_path = out_dir / f"{prefix}_winning.csv"
    sets_path = out_dir / f"{prefix}_sets.csv"
    build_path = out_dir / f"{prefix}_build.json"
    md_path = out_dir / f"{prefix}_build.md"

    if args.offline:
        input_dir = Path(args.input_dir) if args.input_dir else ROOT / "snapshots" / args.hero
        win_df, set_df, source = load_snapshot(input_dir)
        url = f"offline://{source}"
    else:
        win_df, set_df, url = _run_scrape(args)

    win_df.to_csv(winning_path, index=False, encoding="utf-8")
    set_df.to_csv(sets_path, index=False, encoding="utf-8")

    run_pipeline(
        str(winning_path),
        str(sets_path),
        str(build_path),
        explain=args.explain,
        topk=args.topk,
        cover=args.cover,
    )

    render_markdown(sets_path, md_path, topk=args.md_topk)

    print("[ok] source:", url)
    print("[ok] winning csv:", winning_path)
    print("[ok] sets csv:", sets_path)
    print("[ok] build json:", build_path)
    print("[ok] build md:", md_path)


if __name__ == "__main__":
    main()

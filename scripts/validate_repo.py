from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path
from typing import Tuple

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.quickstart import DEF_MODE, DEF_PATCH, DEF_TIER, DEFAULT_LANG  # type: ignore

EXPECTED_WINNING_HEADER = ["img", "name", "win_rate", "pick_rate", "sample_size"]
EXPECTED_SETS_HEADER = ["items", "items_img", "set_win_rate", "set_pick_rate", "set_sample_size"]


def _run_cmd(cmd: list[str]) -> Tuple[int, str]:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return proc.returncode, proc.stdout


def _ensure_csv(path: Path, expected_header: list[str]) -> Tuple[list[str], int]:
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            raise ValueError(f"CSV empty: {path}")
        rows = sum(1 for _ in reader)
    if header != expected_header:
        raise ValueError(f"CSV header mismatch for {path}: expected {expected_header}, got {header}")
    if rows == 0:
        raise ValueError(f"CSV has no data rows: {path}")
    return header, rows


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Offline validation for lol-build-assistant")
    ap.add_argument("--hero", default="varus")
    ap.add_argument("--mode", default=DEF_MODE)
    ap.add_argument("--tier", default=DEF_TIER)
    ap.add_argument("--patch", default=DEF_PATCH)
    ap.add_argument("--lang", default=DEFAULT_LANG)
    ap.add_argument("--out", default="data/processed")
    ap.add_argument("--input-dir", help="Override snapshot directory")
    ap.add_argument("--online", dest="offline", action="store_false", help="Run quickstart in live mode")
    ap.add_argument("--offline", dest="offline", action="store_true", help="Force offline snapshot mode")
    ap.set_defaults(offline=True)
    return ap.parse_args()


def main() -> None:
    args = parse_args()

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable, "-m", "compileall", "scripts"]
    code, output = _run_cmd(cmd)
    print("$", " ".join(cmd))
    print(output.strip())
    if code != 0:
        raise SystemExit(code)

    quickstart_cmd = [
        sys.executable,
        "scripts/quickstart.py",
        "--hero",
        args.hero,
        "--mode",
        args.mode,
        "--tier",
        args.tier,
        "--patch",
        args.patch,
        "--lang",
        args.lang,
        "--out",
        str(out_dir),
    ]

    if args.offline:
        quickstart_cmd.extend(["--offline"])
        snapshot_dir = Path(args.input_dir) if args.input_dir else ROOT / "snapshots" / args.hero
        quickstart_cmd.extend(["--input-dir", str(snapshot_dir)])
    else:
        quickstart_cmd.extend(["--online"])

    print("$", " ".join(quickstart_cmd))
    code, output = _run_cmd(quickstart_cmd)
    print(output.strip())
    if code != 0:
        raise SystemExit(code)

    prefix = f"{args.hero}_{args.mode}_{args.tier}_{args.patch}"
    winning_csv = out_dir / f"{prefix}_winning.csv"
    sets_csv = out_dir / f"{prefix}_sets.csv"

    _, win_rows = _ensure_csv(winning_csv, EXPECTED_WINNING_HEADER)
    _, set_rows = _ensure_csv(sets_csv, EXPECTED_SETS_HEADER)

    print("[PASS]", winning_csv, f"rows={win_rows}")
    print("[PASS]", sets_csv, f"rows={set_rows}")

    print("Validation PASS")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Validation FAILED: {exc}")
        raise SystemExit(1)

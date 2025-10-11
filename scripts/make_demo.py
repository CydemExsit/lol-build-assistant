from __future__ import annotations

import argparse
import csv
from pathlib import Path


def _read_head(path: Path, limit: int) -> list[list[str]]:
    rows: list[list[str]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return rows
        rows.append(header)
        for idx, row in enumerate(reader):
            if limit >= 0 and idx >= limit:
                break
            rows.append(row)
    return rows


def _write_rows(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description="Create demo CSV snippets from existing outputs")
    ap.add_argument("--sets", required=True, help="Path to the processed *_sets.csv file")
    ap.add_argument("--winning", required=True, help="Path to the processed *_winning.csv file")
    ap.add_argument(
        "--max-lines",
        type=int,
        default=50,
        help="Maximum number of lines (including header) to keep in demo CSVs",
    )
    ap.add_argument("--out-dir", default="demo", help="Destination directory for demo samples")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    sets_src = Path(args.sets)
    win_src = Path(args.winning)
    limit = max(args.max_lines - 1, 0)

    sets_rows = _read_head(sets_src, limit)
    win_rows = _read_head(win_src, limit)

    if sets_rows:
        _write_rows(out_dir / "sets.sample.csv", sets_rows)
    if win_rows:
        _write_rows(out_dir / "winning.sample.csv", win_rows)


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple

import pandas as pd

REQUIRED_WINNING = ["img", "name", "win_rate", "pick_rate", "sample_size"]
REQUIRED_SETS = ["items", "items_img", "set_win_rate", "set_pick_rate", "set_sample_size"]


def _load_records(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if isinstance(payload, dict):
        if "data" in payload and isinstance(payload["data"], list):
            return list(payload["data"])
        return [payload]
    if not isinstance(payload, list):
        raise ValueError(f"Unsupported JSON structure in {path}")
    return payload


def _coerce_numeric(df: pd.DataFrame, columns: list[str]) -> None:
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")


def _coerce_int(df: pd.DataFrame, columns: list[str]) -> None:
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)


def load_snapshot(input_dir: Path) -> Tuple[pd.DataFrame, pd.DataFrame, str]:
    """Load winning/sets tables from an offline snapshot directory."""

    base = input_dir
    if not base.exists():
        raise FileNotFoundError(f"Snapshot directory not found: {base}")

    winning_path = base / "winning.json"
    sets_path = base / "sets.json"
    meta_path = base / "meta.json"

    if not winning_path.exists() or not sets_path.exists():
        raise FileNotFoundError(f"Snapshot directory missing required JSON: {winning_path} or {sets_path}")

    winning_records = _load_records(winning_path)
    sets_records = _load_records(sets_path)

    win_df = pd.DataFrame(winning_records)
    sets_df = pd.DataFrame(sets_records)

    for required, label, df in [
        (REQUIRED_WINNING, "winning", win_df),
        (REQUIRED_SETS, "sets", sets_df),
    ]:
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"Snapshot {label} JSON missing columns: {', '.join(missing)}")

    _coerce_numeric(win_df, ["win_rate", "pick_rate"])
    _coerce_numeric(sets_df, ["set_win_rate", "set_pick_rate"])
    _coerce_int(win_df, ["sample_size"])
    _coerce_int(sets_df, ["set_sample_size"])

    source = str(base)
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding='utf-8'))
            if isinstance(meta, dict) and meta.get('source'):
                source = str(meta['source'])
            elif isinstance(meta, dict):
                source = json.dumps(meta, ensure_ascii=False)
        except Exception:
            source = meta_path.read_text(encoding='utf-8')
    return win_df, sets_df, source

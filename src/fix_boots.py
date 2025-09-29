# src/fix_boots.py
from __future__ import annotations
import argparse, json
from pathlib import Path
import pandas as pd

BOOT_HINT = "靴|鞋|護脛|Greaves|Treads|Tabi|Boots"

def _to_unit(s):
    v = pd.to_numeric(s, errors="coerce").fillna(0.0).astype(float)
    return v.where(v <= 1.0, v / 100.0)

def pick_boot_from_winning(winning_csv: Path) -> str | None:
    if not winning_csv.exists():
        print(f"[warn] winning.csv not found: {winning_csv}")
        return None

    df = pd.read_csv(winning_csv, encoding="utf-8")
    if df.empty or "name" not in df.columns:
        print("[warn] winning.csv empty or missing 'name'")
        return None

    # 對齊欄位名稱
    if "pick_rate" not in df.columns and "pick" in df.columns:
        df["pick_rate"] = df["pick"]
    if "win_rate" not in df.columns and "win" in df.columns:
        df["win_rate"] = df["win"]
    if "pick_rate" not in df.columns or "win_rate" not in df.columns:
        print("[warn] winning.csv missing pick_rate/win_rate")
        return None

    # 僅保留疑似靴子，排除「鞋子」
    name = df["name"].astype(str)
    mask = name.str.contains(BOOT_HINT, regex=True, na=False) & (name != "鞋子")
    cand = df.loc[mask, ["name", "pick_rate", "win_rate"]].copy()
    if cand.empty:
        return None

    # 數值正規化
    cand["pick_rate"] = _to_unit(cand["pick_rate"])
    cand["win_rate"]  = _to_unit(cand["win_rate"])

    # 依 選取率↓、勝率↓ 排序
    cand = cand.sort_values(["pick_rate", "win_rate"], ascending=[False, False])

    best = cand.iloc[0]["name"].strip()
    return best or None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True, help="path to build json (will be updated in-place)")
    ap.add_argument("--winning_csv", required=True)
    ap.add_argument("--sets_csv", required=False)  # 兼容 batch 參數，實際不使用
    args = ap.parse_args()

    json_path = Path(args.json)
    boots = pick_boot_from_winning(Path(args.winning_csv))

    # 載入/更新 JSON
    cfg = json.loads(json_path.read_text(encoding="utf-8"))
    if "build" not in cfg:
        cfg["build"] = {}

    if boots:
        print(f"[ok] boots -> {boots}")
        cfg["build"]["boots"] = boots
    else:
        print("[warn] boots -> 無法從 winning.csv 判定，沿用 JSON 內容")

    json_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()

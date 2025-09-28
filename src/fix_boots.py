# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse, json, re
from pathlib import Path
import pandas as pd

# 升級靴關鍵詞；避免把「鞋子」(未升級) 選到
BOOT_RE = re.compile(r"(?:靴|護脛)")

def _read_csv(p: Path) -> pd.DataFrame:
    df = pd.read_csv(p)
    df.columns = [c.strip() for c in df.columns]
    return df

def _choose_from_sets(sets_csv: Path) -> str | None:
    if not sets_csv.exists():
        return None
    df = _read_csv(sets_csv)
    if "items" not in df.columns:
        return None

    # 權重來源：set_pick_rate（沒有就當 1）
    w = pd.to_numeric(df.get("set_pick_rate", 1.0), errors="coerce").fillna(1.0)

    weight: dict[str, float] = {}
    for items_str, ww in zip(df["items"].astype(str), w):
        for it in items_str.split("|"):
            it = it.strip()
            if not it: 
                continue
            if it == "鞋子":          # 明確排除未升級靴
                continue
            if BOOT_RE.search(it):    # 只算升級靴
                weight[it] = weight.get(it, 0.0) + float(ww)

    if not weight:
        return None
    return sorted(weight.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]

def _fallback_from_winning(win_csv: Path) -> str | None:
    if not win_csv.exists():
        return None
    df = _read_csv(win_csv)
    need = {"name", "pick_rate"}
    if not need.issubset(df.columns):
        return None

    cand = df.loc[(df["name"] != "鞋子") & (df["name"].astype(str).str.contains(BOOT_RE, regex=True, na=False))].copy()
    if cand.empty:
        return None
    cand.loc[:, "pick_rate"] = pd.to_numeric(cand["pick_rate"], errors="coerce").fillna(0.0)
    cand = cand.sort_values(["pick_rate", "name"], ascending=[False, True])
    return str(cand.iloc[0]["name"])

def _patch_json_boot(json_path: Path, boots_name: str) -> None:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    data.setdefault("build", {})
    data["build"]["boots"] = boots_name
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True, help="要覆寫的輸入/輸出 JSON（build.boots）")
    ap.add_argument("--sets_csv", required=True, help="Actually Built Sets csv")
    ap.add_argument("--winning_csv", help="Winning Items csv（回退來源）")
    args = ap.parse_args()

    best = _choose_from_sets(Path(args.sets_csv))
    if not best and args.winning_csv:
        best = _fallback_from_winning(Path(args.winning_csv))
    if not best:
        best = "鞋子"  # 兩邊都找不到升級靴才回退

    _patch_json_boot(Path(args.json), best)
    print(f"[ok] boots -> {best}")

if __name__ == "__main__":
    main()

import argparse, os, re, glob
import pandas as pd
from pathlib import Path

# ---------------------- util ----------------------

def ensure_dir(p: str):
    if p:
        os.makedirs(p, exist_ok=True)


def _norm_rate(v):
    if pd.isna(v):
        return None
    if isinstance(v, str):
        s = v.strip().replace('%', '')
        try:
            v = float(s)
        except ValueError:
            return None
    return float(v) / 100.0 if v > 1 else float(v)


def _norm_str(s):
    return None if pd.isna(s) else str(s).strip()


def _slug(s):
    s = _norm_str(s) or ""
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s

# ---------------------- items map ----------------------

def load_items_map(path: str) -> pd.DataFrame:
    m = pd.read_csv(path, dtype={"item_id": int, "en_name": str, "zh_tw_name": str})
    m["key_en"] = m["en_name"].str.lower()
    return m


def find_item(token, items_map: pd.DataFrame):
    s = _norm_str(token)
    if s is None:
        return None
    if s.isdigit():
        hit = items_map[items_map["item_id"] == int(s)]
        return hit.iloc[0] if len(hit) else None
    key = s.lower()
    hit = items_map[items_map["key_en"] == key]
    return hit.iloc[0] if len(hit) else None

# ---------------------- filename parse ----------------------

FNAME_RE = re.compile(r"^(?P<champ>[^_]+)_(?P<middle>.+?)_(?P<window>\d+d)_(?P<kind>sets|winning)\.csv$",
                      re.IGNORECASE)


def parse_meta_from_name(name: str):
    """從檔名萃取 champion、window、kind 與中段 tag。
    例：vayne_aram_d2_plus_7d_sets.csv -> champ=vayne, window=7d, kind=sets, middle=aram_d2_plus
    若不匹配，回傳 None 使之走 fallback。
    """
    m = FNAME_RE.match(name)
    if not m:
        return None
    d = m.groupdict()
    return {
        "champion": d["champ"],
        "window": d["window"],
        "kind": d["kind"].lower(),
        "tag": d["middle"],
    }

# ---------------------- normalization core ----------------------

ITEM_COL_RE = re.compile(r"item[1-5]$", re.IGNORECASE)


def split_set(x):
    if isinstance(x, (list, tuple)):
        return list(x)[:5]
    if pd.isna(x):
        return []
    parts = re.split(r"[,\|\s]+", str(x))
    return [p for p in parts if p][:5]


def normalize_sets(df: pd.DataFrame, items_map: pd.DataFrame) -> pd.DataFrame:
    champ_col = next((c for c in df.columns if c.lower() in ["champion", "champ", "character"]), None)
    games_col = next((c for c in df.columns if c.lower() in ["games", "matches", "count"]), None)
    win_col = next((c for c in df.columns if c.lower() in ["winrate", "win%", "win_rate", "wr"]), None)
    pick_col = next((c for c in df.columns if c.lower() in ["pickrate", "pick%", "pr"]), None)

    item_cols = [c for c in df.columns if ITEM_COL_RE.fullmatch(c)]
    set_col = next((c for c in df.columns if c.lower() in ["set", "items", "build", "combo"]), None)

    out_rows = []
    for _, r in df.iterrows():
        champ = _norm_str(r.get(champ_col, "")) if champ_col else ""
        games = int(r.get(games_col, 0) or 0) if games_col else None
        winrt = _norm_rate(r.get(win_col)) if win_col else None
        pickr = _norm_rate(r.get(pick_col)) if pick_col else None

        raw_items = []
        if item_cols:
            for ic in sorted(item_cols, key=lambda x: int(x[-1])):
                raw_items.append(r.get(ic))
        elif set_col:
            raw_items = split_set(r.get(set_col))

        item_ids, item_en, item_zh = [], [], []
        for it in raw_items[:5]:
            hit = find_item(it, items_map)
            if hit is None:
                item_ids.append(None); item_en.append(_norm_str(it)); item_zh.append(None)
            else:
                item_ids.append(int(hit["item_id"]))
                item_en.append(hit["en_name"])
                item_zh.append(hit["zh_tw_name"])

        out_rows.append({
            "champion": champ,
            "champion_slug": _slug(champ),
            "games": games,
            "winrate": winrt,
            "pickrate": pickr,
            "item_id1": item_ids[0] if len(item_ids) > 0 else None,
            "item_id2": item_ids[1] if len(item_ids) > 1 else None,
            "item_id3": item_ids[2] if len(item_ids) > 2 else None,
            "item_id4": item_ids[3] if len(item_ids) > 3 else None,
            "item_id5": item_ids[4] if len(item_ids) > 4 else None,
            "item_en1": item_en[0] if len(item_en) > 0 else None,
            "item_en2": item_en[1] if len(item_en) > 1 else None,
            "item_en3": item_en[2] if len(item_en) > 2 else None,
            "item_en4": item_en[3] if len(item_en) > 3 else None,
            "item_en5": item_en[4] if len(item_en) > 4 else None,
            "item_zh1": item_zh[0] if len(item_zh) > 0 else None,
            "item_zh2": item_zh[1] if len(item_zh) > 1 else None,
            "item_zh3": item_zh[2] if len(item_zh) > 2 else None,
            "item_zh4": item_zh[3] if len(item_zh) > 3 else None,
            "item_zh5": item_zh[4] if len(item_zh) > 4 else None,
        })
    return pd.DataFrame(out_rows)


def normalize_winning(df: pd.DataFrame, items_map: pd.DataFrame) -> pd.DataFrame:
    item_col = next((c for c in df.columns if c.lower() in ["item", "item_name", "name"]), None)
    games_col = next((c for c in df.columns if c.lower() in ["games", "matches", "count"]), None)
    win_col = next((c for c in df.columns if c.lower() in ["winrate", "win%", "win_rate", "wr"]), None)
    pick_col = next((c for c in df.columns if c.lower() in ["pickrate", "pick%", "pr"]), None)

    out_rows = []
    for _, r in df.iterrows():
        item_raw = r.get(item_col)
        games = int(r.get(games_col, 0) or 0) if games_col else None
        winrt = _norm_rate(r.get(win_col)) if win_col else None
        pickr = _norm_rate(r.get(pick_col)) if pick_col else None
        hit = find_item(item_raw, items_map)

        out_rows.append({
            "item_id": int(hit["item_id"]) if hit is not None else None,
            "item_en": hit["en_name"] if hit is not None else _norm_str(item_raw),
            "item_zh": hit["zh_tw_name"] if hit is not None else None,
            "games": games,
            "winrate": winrt,
            "pickrate": pickr,
        })
    return pd.DataFrame(out_rows)

# ---------------------- main ----------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-dir", default="data/raw")
    ap.add_argument("--glob-sets", default=None, help="自訂 sets 檔案樣式，例如 data/raw/*_sets.csv")
    ap.add_argument("--glob-winning", default=None, help="自訂 winning 檔案樣式，例如 data/raw/*_winning.csv")
    ap.add_argument("--hero", default=None, help="只處理指定英雄（小寫，如 vayne）")
    ap.add_argument("--items-map", default="data/ref/items_map.csv")
    ap.add_argument("--out-dir", default="data/processed")
    args = ap.parse_args()

    items_map = load_items_map(args.items_map)

    in_dir = Path(args.in_dir)
    ensure_dir(args.out_dir)

    # 掃描檔案
    sets_glob = args.glob_sets or str(in_dir / "*_sets.csv")
    winning_glob = args.glob_winning or str(in_dir / "*_winning.csv")

    set_files = sorted(glob.glob(sets_glob))
    winning_files = sorted(glob.glob(winning_glob))

    # 依檔名分組
    by_hero_sets = {}
    for p in set_files:
        name = os.path.basename(p)
        meta = parse_meta_from_name(name)
        champ = (meta or {}).get("champion") or name.split("_")[0]
        if args.hero and champ.lower() != args.hero.lower():
            continue
        by_hero_sets.setdefault(champ, []).append((p, meta))

    by_hero_win = {}
    for p in winning_files:
        name = os.path.basename(p)
        meta = parse_meta_from_name(name)
        champ = (meta or {}).get("champion") or name.split("_")[0]
        if args.hero and champ.lower() != args.hero.lower():
            continue
        by_hero_win.setdefault(champ, []).append((p, meta))

    all_sets_frames, all_win_frames = [], []

    for champ in sorted(set(by_hero_sets.keys()) | set(by_hero_win.keys())):
        out_dir_champ = os.path.join(args.out_dir, champ.lower())
        ensure_dir(out_dir_champ)

        # 處理 sets
        merged_sets = []
        for p, meta in by_hero_sets.get(champ, []):
            df = pd.read_csv(p)
            norm = normalize_sets(df, items_map)
            # 附帶來源欄位
            norm.insert(0, "source_file", os.path.basename(p))
            if meta:
                norm.insert(1, "window", meta["window"])  # 如 7d
                norm.insert(2, "source_tag", meta["tag"]) # 中段字串（mode+tier 等）
            else:
                norm.insert(1, "window", None)
                norm.insert(2, "source_tag", None)
            norm.insert(3, "source_champion", champ)
            merged_sets.append(norm)
        if merged_sets:
            df_sets_all = pd.concat(merged_sets, ignore_index=True)
            df_sets_all.to_csv(os.path.join(out_dir_champ, "sets_normalized.csv"), index=False, encoding="utf-8")
            all_sets_frames.append(df_sets_all)

        # 處理 winning
        merged_win = []
        for p, meta in by_hero_win.get(champ, []):
            df = pd.read_csv(p)
            norm = normalize_winning(df, items_map)
            norm.insert(0, "source_file", os.path.basename(p))
            if meta:
                norm.insert(1, "window", meta["window"])  # 如 7d
                norm.insert(2, "source_tag", meta["tag"]) # 中段字串
            else:
                norm.insert(1, "window", None)
                norm.insert(2, "source_tag", None)
            norm.insert(3, "source_champion", champ)
            merged_win.append(norm)
        if merged_win:
            df_win_all = pd.concat(merged_win, ignore_index=True)
            df_win_all.to_csv(os.path.join(out_dir_champ, "winning_normalized.csv"), index=False, encoding="utf-8")
            all_win_frames.append(df_win_all)

    # 彙整輸出
    if all_sets_frames:
        pd.concat(all_sets_frames, ignore_index=True).to_csv(
            os.path.join(args.out_dir, "all_sets_normalized.csv"), index=False, encoding="utf-8"
        )
    if all_win_frames:
        pd.concat(all_win_frames, ignore_index=True).to_csv(
            os.path.join(args.out_dir, "all_winning_normalized.csv"), index=False, encoding="utf-8"
        )

    print("Done.")


if __name__ == "__main__":
    main()

# --------------------------------------------------------------
# PowerShell 使用範例
# 單行：
# python scripts/normalize_outputs_batch.py --in-dir data/raw --items-map data/ref/items_map.csv --out-dir data/processed
# 只處理特定英雄：
# python scripts/normalize_outputs_batch.py --in-dir data/raw --items-map data/ref/items_map.csv --out-dir data/processed --hero vayne
# 客製掃描樣式：
# python scripts/normalize_outputs_batch.py --glob-sets "data/raw/*_sets.csv" --glob-winning "data/raw/*_winning.csv" --items-map data/ref/items_map.csv --out-dir data/processed

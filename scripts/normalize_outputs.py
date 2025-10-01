# -*- coding: utf-8 -*-
import argparse, os, re
import pandas as pd

def ensure_dir(p): os.makedirs(p, exist_ok=True)

def _norm_rate(v):
    if pd.isna(v): return None
    if isinstance(v, str):
        v = v.strip().replace("%","")
        try: v = float(v)
        except: return None
    # 若大於1，視為百分比
    return float(v)/100.0 if v>1 else float(v)

def _norm_str(s):
    return None if pd.isna(s) else str(s).strip()

def _slug(s):
    s = _norm_str(s) or ""
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+","-", s).strip("-")
    return s

def _load_items_map(path):
    m = pd.read_csv(path, dtype={"item_id":int, "en_name":str, "zh_tw_name":str})
    # 建立反查
    m["key_en"] = m["en_name"].str.lower()
    return m

def _find_item(row_name, items_map):
    """row_name 可能是數字ID或英文名"""
    s = _norm_str(row_name)
    if s is None: return None
    if s.isdigit():
        hit = items_map[items_map["item_id"]==int(s)]
        return hit.iloc[0] if len(hit) else None
    key = s.lower()
    hit = items_map[items_map["key_en"]==key]
    return hit.iloc[0] if len(hit) else None

def _split_set(x):
    # 支援 "item1..item5" 欄位，或單欄位用逗號/空白/| 分隔
    if isinstance(x, (list, tuple)): return list(x)[:5]
    if pd.isna(x): return []
    s = str(x)
    parts = re.split(r"[,\|\s]+", s)
    return [p for p in parts if p][:5]

def normalize_sets(df, items_map):
    # 可能欄位別名
    champ_col = next((c for c in df.columns if c.lower() in ["champion","champ","character"]), None)
    games_col = next((c for c in df.columns if c.lower() in ["games","matches","count"]), None)
    win_col   = next((c for c in df.columns if c.lower() in ["winrate","win%","win_rate","wr"]), None)
    pick_col  = next((c for c in df.columns if c.lower() in ["pickrate","pick%","pr"]), None)

    # 取得物品來源：item1..item5 或 set/ items
    item_cols = [c for c in df.columns if re.fullmatch(r"item[1-5]", c.lower())]
    set_col = next((c for c in df.columns if c.lower() in ["set","items","build","combo"]), None)

    out_rows = []
    for _, r in df.iterrows():
        champ = _norm_str(r.get(champ_col, "")) if champ_col else ""
        games = int(r.get(games_col, 0) or 0) if games_col else None
        winrt = _norm_rate(r.get(win_col)) if win_col else None
        pickr = _norm_rate(r.get(pick_col)) if pick_col else None

        # 取五件
        raw_items = []
        if item_cols:
            for ic in sorted(item_cols, key=lambda x: int(x[-1])):
                raw_items.append(r.get(ic))
        elif set_col:
            raw_items = _split_set(r.get(set_col))
        # 映射
        item_ids, item_en, item_zh = [], [], []
        for it in raw_items[:5]:
            hit = _find_item(it, items_map)
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
            "item_id1": item_ids[0] if len(item_ids)>0 else None,
            "item_id2": item_ids[1] if len(item_ids)>1 else None,
            "item_id3": item_ids[2] if len(item_ids)>2 else None,
            "item_id4": item_ids[3] if len(item_ids)>3 else None,
            "item_id5": item_ids[4] if len(item_ids)>4 else None,
            "item_en1": item_en[0] if len(item_en)>0 else None,
            "item_en2": item_en[1] if len(item_en)>1 else None,
            "item_en3": item_en[2] if len(item_en)>2 else None,
            "item_en4": item_en[3] if len(item_en)>3 else None,
            "item_en5": item_en[4] if len(item_en)>4 else None,
            "item_zh1": item_zh[0] if len(item_zh)>0 else None,
            "item_zh2": item_zh[1] if len(item_zh)>1 else None,
            "item_zh3": item_zh[2] if len(item_zh)>2 else None,
            "item_zh4": item_zh[3] if len(item_zh)>3 else None,
            "item_zh5": item_zh[4] if len(item_zh)>4 else None,
        })
    return pd.DataFrame(out_rows)

def normalize_winning(df, items_map):
    item_col = next((c for c in df.columns if c.lower() in ["item","item_name","name"]), None)
    games_col = next((c for c in df.columns if c.lower() in ["games","matches","count"]), None)
    win_col   = next((c for c in df.columns if c.lower() in ["winrate","win%","win_rate","wr"]), None)
    pick_col  = next((c for c in df.columns if c.lower() in ["pickrate","pick%","pr"]), None)

    out_rows = []
    for _, r in df.iterrows():
        item_raw = r.get(item_col)
        games = int(r.get(games_col, 0) or 0) if games_col else None
        winrt = _norm_rate(r.get(win_col)) if win_col else None
        pickr = _norm_rate(r.get(pick_col)) if pick_col else None
        hit = _find_item(item_raw, items_map)

        out_rows.append({
            "item_id": int(hit["item_id"]) if hit is not None else None,
            "item_en": hit["en_name"] if hit is not None else _norm_str(item_raw),
            "item_zh": hit["zh_tw_name"] if hit is not None else None,
            "games": games,
            "winrate": winrt,
            "pickrate": pickr
        })
    return pd.DataFrame(out_rows)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", default="data/raw/sets.csv")
    ap.add_argument("--winning", default="data/raw/winning.csv")
    ap.add_argument("--items-map", default="data/ref/items_map.csv")
    ap.add_argument("--out-dir", default="data/processed")
    args = ap.parse_args()

    items_map = _load_items_map(args.items_map)

    df_sets = pd.read_csv(args.sets)
    df_win  = pd.read_csv(args.winning)

    out_sets = normalize_sets(df_sets, items_map)
    out_win  = normalize_winning(df_win, items_map)

    ensure_dir(args.out_dir)
    out_sets.to_csv(os.path.join(args.out_dir, "sets_normalized.csv"), index=False, encoding="utf-8")
    out_win.to_csv(os.path.join(args.out_dir, "winning_normalized.csv"), index=False, encoding="utf-8")

if __name__ == "__main__":
    main()

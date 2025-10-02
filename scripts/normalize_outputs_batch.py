# -*- coding: utf-8 -*-
import argparse, os, re, glob, json, datetime, csv
import pandas as pd
from pathlib import Path

ITEM_COL_RE = re.compile(r"item[1-5]$", re.IGNORECASE)
FNAME_RE = re.compile(r"^(?P<champ>[^_]+)_(?P<middle>.+?)_(?P<window>\d+d)_(?P<kind>sets|winning)\.csv$", re.IGNORECASE)

GAMES_KEYS = {"games","matches","count","對局數","場次","對局","比賽數"}
WIN_KEYS   = {"winrate","win%","win_rate","wr","勝率"}
PICK_KEYS  = {"pickrate","pick%","pr","選用率","出場率","選取率","登場率"}
ITEM_KEYS  = {"item","item_name","name","物品","道具","裝備"}
SET_KEYS   = {"set","items","build","combo","組合","套裝","出裝"}
CHAMP_KEYS = {"champion","champ","character","英雄","角色"}


def ensure_dir(p: str):
    if p: os.makedirs(p, exist_ok=True)


def _norm_rate(v):
    if pd.isna(v): return None
    if isinstance(v, str):
        s = v.strip().replace('%','').replace(',','')
        if not s: return None
        try: v = float(s)
        except ValueError: return None
    return float(v)/100.0 if v > 1 else float(v)


def _to_int(v):
    if v is None or pd.isna(v): return None
    if isinstance(v, int): return v
    s = str(v).strip().replace(',','').replace(' ','')
    if not s: return None
    try: return int(float(s))
    except ValueError: return None


def _norm_str(s):
    return None if pd.isna(s) else str(s).strip()


def _slug(s):
    s = _norm_str(s) or ""; s = s.lower(); return re.sub(r"[^a-z0-9]+","-", s).strip("-")


def _norm_key(s: str):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", s.lower())


def _col(df: pd.DataFrame, keys: set):
    lower_map = {c.lower(): c for c in df.columns}
    for k in keys:
        if k.isascii() and k in lower_map: return lower_map[k]
    for c in df.columns:
        if c in keys: return c
    return None


def split_set(x):
    if isinstance(x, (list, tuple)): return list(x)[:5]
    if pd.isna(x): return []
    parts = re.split(r"[,\|\s]+", str(x))
    return [p for p in parts if p][:5]


def parse_meta_from_name(name: str):
    m = FNAME_RE.match(name)
    if not m: return None
    d = m.groupdict(); tag = d["middle"]
    parts = tag.split("_"); mode = parts[0] if len(parts)>=1 else None; tier = "_".join(parts[1:]) if len(parts)>=2 else None
    return {"champion": d["champ"], "window": d["window"], "kind": d["kind"].lower(), "tag": tag, "mode": mode, "tier": tier}


# 物品索引（O(1) 查詢）；可選別名表
class ItemIndex:
    def __init__(self, df: pd.DataFrame, alias_csv: str|None):
        self.by_id: dict[int, tuple] = {}
        self.key_en: dict[str, tuple] = {}
        self.key_zh: dict[str, tuple] = {}
        self.norm_en: dict[str, tuple] = {}
        self.norm_zh: dict[str, tuple] = {}
        for _, r in df.iterrows():
            tup = (int(r["item_id"]), r["en_name"], r.get("zh_tw_name"))
            self.by_id[int(r["item_id"])] = tup
            if isinstance(r["en_name"], str):
                k = r["en_name"].lower(); self.key_en[k] = tup; self.norm_en[_norm_key(k)] = tup
            if isinstance(r.get("zh_tw_name"), str):
                z = r["zh_tw_name"].lower(); self.key_zh[z] = tup; self.norm_zh[_norm_key(z)] = tup
        self.alias: dict[str, tuple|None] = {}
        if alias_csv and os.path.exists(alias_csv):
            with open(alias_csv, newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    zh = (row.get('alias_zh') or '').strip(); en = (row.get('alias_en') or '').strip().lower(); iid = (row.get('item_id') or '').strip()
                    key = _norm_key(zh) if zh else None
                    tgt = None
                    if iid.isdigit(): tgt = self.by_id.get(int(iid))
                    if tgt is None and en: tgt = self.key_en.get(en) or self.norm_en.get(_norm_key(en))
                    if key: self.alias[key] = tgt

    def find(self, token):
        s = _norm_str(token)
        if s is None: return None
        if s.isdigit(): return self.by_id.get(int(s))
        norm = _norm_key(s); low = s.lower()
        return (self.alias.get(norm) or self.key_en.get(low) or self.key_zh.get(low)
                or self.norm_en.get(norm) or self.norm_zh.get(norm))


def load_items_map(path: str) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"item_id": int, "en_name": str, "zh_tw_name": str})


def read_items_map_version(items_map_path: str) -> str:
    meta_path = os.path.join(os.path.dirname(os.path.abspath(items_map_path)), "items_map_meta.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f).get("ddragon_version") or ""
        except Exception: pass
    m = re.search(r"items_map_([0-9.]+)\.csv$", items_map_path)
    return m.group(1) if m else ""


def _item_index(col_name: str) -> int:
    m = re.search(r"(\d+)$", str(col_name)); return int(m.group(1)) if m else 999


def normalize_sets(df: pd.DataFrame, idx: ItemIndex) -> tuple[pd.DataFrame, dict]:
    champ_col = _col(df, CHAMP_KEYS); games_col = _col(df, GAMES_KEYS)
    win_col = _col(df, WIN_KEYS); pick_col = _col(df, PICK_KEYS)
    item_cols = [c for c in df.columns if ITEM_COL_RE.fullmatch(c)]; set_col = _col(df, SET_KEYS)
    rows = []
    for _, r in df.iterrows():
        champ = _norm_str(r.get(champ_col, "")) if champ_col else ""
        games = _to_int(r.get(games_col)) if games_col else None
        winrt = _norm_rate(r.get(win_col)) if win_col else None
        pickr = _norm_rate(r.get(pick_col)) if pick_col else None
        raw_items = [r.get(ic) for ic in sorted(item_cols, key=_item_index)] if item_cols else (split_set(r.get(set_col)) if set_col else [])
        item_ids, item_en, item_zh = [], [], []
        for it in raw_items[:5]:
            hit = idx.find(it)
            if hit is None:
                item_ids.append(None); item_en.append(_norm_str(it)); item_zh.append(None)
            else:
                item_ids.append(hit[0]); item_en.append(hit[1]); item_zh.append(hit[2])
        rows.append({
            "champion": champ, "champion_slug": _slug(champ), "games": games, "winrate": winrt, "pickrate": pickr,
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
    out = pd.DataFrame(rows)
    cols = [
        "source_file","window","source_tag","source_mode","source_tier","source_champion",
        "champion","champion_slug","games","winrate","pickrate",
        "item_id1","item_id2","item_id3","item_id4","item_id5",
        "item_en1","item_en2","item_en3","item_en4","item_en5",
        "item_zh1","item_zh2","item_zh3","item_zh4","item_zh5",
    ]
    for c in cols:
        if c not in out.columns: out[c] = None
    out = out[cols]
    flags = {"has_winrate": win_col is not None, "has_pickrate": pick_col is not None}
    return out, flags


def normalize_winning(df: pd.DataFrame, idx: ItemIndex) -> tuple[pd.DataFrame, dict]:
    item_col = _col(df, ITEM_KEYS); games_col = _col(df, GAMES_KEYS)
    win_col = _col(df, WIN_KEYS); pick_col = _col(df, PICK_KEYS)
    rows = []
    for _, r in df.iterrows():
        item_raw = r.get(item_col); games = _to_int(r.get(games_col)) if games_col else None
        winrt = _norm_rate(r.get(win_col)) if win_col else None
        pickr = _norm_rate(r.get(pick_col)) if pick_col else None
        hit = idx.find(item_raw)
        rows.append({
            "item_id": hit[0] if hit else None,
            "item_en": hit[1] if hit else _norm_str(item_raw),
            "item_zh": hit[2] if hit else None,
            "games": games, "winrate": winrt, "pickrate": pickr,
        })
    out = pd.DataFrame(rows)
    cols = ["source_file","window","source_tag","source_mode","source_tier","source_champion","item_id","item_en","item_zh","games","winrate","pickrate"]
    for c in cols:
        if c not in out.columns: out[c] = None
    out = out[cols]
    flags = {"has_winrate": win_col is not None, "has_pickrate": pick_col is not None}
    return out, flags


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-dir", default="data/raw")
    ap.add_argument("--glob-sets", default=None)
    ap.add_argument("--glob-winning", default=None)
    ap.add_argument("--hero", default=None)
    ap.add_argument("--items-map", default="data/ref/items_map.csv")
    ap.add_argument("--item-aliases", default="data/ref/item_aliases.csv")
    ap.add_argument("--out-dir", default="data/processed")
    args = ap.parse_args()

    items_df = load_items_map(args.items_map)
    idx = ItemIndex(items_df, args.item_aliases)
    ddragon_ver = read_items_map_version(args.items_map)

    in_dir = Path(args.in_dir); ensure_dir(args.out_dir)
    sets_glob = args.glob_sets or str(in_dir / "*_sets.csv")
    winning_glob = args.glob_winning or str(in_dir / "*_winning.csv")
    set_files = sorted(glob.glob(sets_glob)); winning_files = sorted(glob.glob(winning_glob))

    by_hero_sets, by_hero_win = {}, {}
    modes, tiers, windows = set(), set(), set()

    for p in set_files:
        name = os.path.basename(p); meta = parse_meta_from_name(name)
        champ = (meta or {}).get("champion") or name.split("_")[0]
        if args.hero and champ.lower() != args.hero.lower(): continue
        by_hero_sets.setdefault(champ, []).append((p, meta))
        if meta:
            if meta.get("mode"): modes.add(meta["mode"]) 
            if meta.get("tier"): tiers.add(meta["tier"]) 
            if meta.get("window"): windows.add(meta["window"]) 

    for p in winning_files:
        name = os.path.basename(p); meta = parse_meta_from_name(name)
        champ = (meta or {}).get("champion") or name.split("_")[0]
        if args.hero and champ.lower() != args.hero.lower(): continue
        by_hero_win.setdefault(champ, []).append((p, meta))
        if meta:
            if meta.get("mode"): modes.add(meta["mode"]) 
            if meta.get("tier"): tiers.add(meta["tier"]) 
            if meta.get("window"): windows.add(meta["window"]) 

    all_sets_frames, all_win_frames = [], []
    audit_missing_rows, audit_rate_rows = [], []

    def audit_rates(row: pd.Series, fields: list[str], ctx: dict):
        for c in fields:
            v = row.get(c)
            bad = v is None or pd.isna(v) or (isinstance(v, float) and (v < 0 or v > 1))
            if bad: audit_rate_rows.append({**ctx, "field": c, "value": v})

    for champ in sorted(set(by_hero_sets.keys()) | set(by_hero_win.keys())):
        out_dir_champ = os.path.join(args.out_dir, champ.lower()); ensure_dir(out_dir_champ)

        merged_sets = []
        for p, meta in by_hero_sets.get(champ, []):
            df = pd.read_csv(p)
            norm, flags = normalize_sets(df, idx)
            norm["source_file"] = os.path.basename(p)
            if meta:
                norm["window"] = meta["window"]; norm["source_tag"] = meta["tag"]; norm["source_mode"] = meta.get("mode"); norm["source_tier"] = meta.get("tier")
            else:
                norm["window"] = norm["source_tag"] = norm["source_mode"] = norm["source_tier"] = None
            norm["source_champion"] = champ
            if norm["champion"].isna().all() or (norm["champion"].astype(str).str.strip()=="").all(): norm["champion"] = champ
            if norm["champion_slug"].isna().all() or (norm["champion_slug"].astype(str).str.strip()=="").all(): norm["champion_slug"] = _slug(champ)
            front = ["source_file","window","source_tag","source_mode","source_tier","source_champion"]; norm = norm[front + [c for c in norm.columns if c not in front]]
            miss_mask = norm[[f"item_id{i}" for i in range(1,6)]].isna().any(axis=1)
            for _, r in norm[miss_mask].iterrows():
                audit_missing_rows.append({"kind": "sets","source_file": r["source_file"],"source_champion": champ,"window": r["window"],"source_tag": r["source_tag"]})
            fields = [c for c, ok in (("winrate", flags["has_winrate"]),("pickrate", flags["has_pickrate"])) if ok]
            for _, r in norm.iterrows(): audit_rates(r, fields, {"kind":"sets","source_file":r["source_file"],"source_champion":champ,"window":r["window"],"source_tag":r["source_tag"]})
            merged_sets.append(norm)
        if merged_sets:
            df_sets_all = pd.concat(merged_sets, ignore_index=True).sort_values(["champion_slug","games"], ascending=[True, False], kind="mergesort")
            df_sets_all.to_csv(os.path.join(out_dir_champ, "sets_normalized.csv"), index=False, encoding="utf-8")
            all_sets_frames.append(df_sets_all)

        merged_win = []
        for p, meta in by_hero_win.get(champ, []):
            df = pd.read_csv(p)
            norm, flags = normalize_winning(df, idx)
            norm["source_file"] = os.path.basename(p)
            if meta:
                norm["window"] = meta["window"]; norm["source_tag"] = meta["tag"]; norm["source_mode"] = meta.get("mode"); norm["source_tier"] = meta.get("tier")
            else:
                norm["window"] = norm["source_tag"] = norm["source_mode"] = norm["source_tier"] = None
            norm["source_champion"] = champ
            front = ["source_file","window","source_tag","source_mode","source_tier","source_champion"]; norm = norm[front + [c for c in norm.columns if c not in front]]
            miss_mask = norm["item_id"].isna()
            for _, r in norm[miss_mask].iterrows():
                audit_missing_rows.append({"kind": "winning","source_file": r["source_file"],"source_champion": champ,"window": r["window"],"source_tag": r["source_tag"]})
            fields = [c for c, ok in (("winrate", flags["has_winrate"]),("pickrate", flags["has_pickrate"])) if ok]
            for _, r in norm.iterrows(): audit_rates(r, fields, {"kind":"winning","source_file":r["source_file"],"source_champion":champ,"window":r["window"],"source_tag":r["source_tag"]})
            merged_win.append(norm)
        if merged_win:
            df_win_all = pd.concat(merged_win, ignore_index=True).sort_values(["item_id","games"], ascending=[True, False], kind="mergesort")
            df_win_all.to_csv(os.path.join(out_dir_champ, "winning_normalized.csv"), index=False, encoding="utf-8")
            all_win_frames.append(df_win_all)

    if all_sets_frames:
        pd.concat(all_sets_frames, ignore_index=True).to_csv(os.path.join(args.out_dir, "all_sets_normalized.csv"), index=False, encoding="utf-8")
    if all_win_frames:
        pd.concat(all_win_frames, ignore_index=True).to_csv(os.path.join(args.out_dir, "all_winning_normalized.csv"), index=False, encoding="utf-8")

    if audit_missing_rows:
        pd.DataFrame(audit_missing_rows).to_csv(os.path.join(args.out_dir, "_audit_items_missing.csv"), index=False, encoding="utf-8")
    else:
        open(os.path.join(args.out_dir, "_audit_items_missing.csv"), "w", encoding="utf-8").write("")
    if audit_rate_rows:
        pd.DataFrame(audit_rate_rows).to_csv(os.path.join(args.out_dir, "_audit_rates.csv"), index=False, encoding="utf-8")
    else:
        open(os.path.join(args.out_dir, "_audit_rates.csv"), "w", encoding="utf-8").write("")

    meta = {"ddragon_version": ddragon_ver, "modes": sorted(modes), "tiers": sorted(tiers), "windows": sorted(windows),
            "run_at": datetime.datetime.now().astimezone().isoformat(), "inputs": {"in_dir": str(in_dir)},
            "counts": {"set_files": len(set_files), "winning_files": len(winning_files), "champions": len(set(by_hero_sets.keys()) | set(by_hero_win.keys()))}}
    with open(os.path.join(args.out_dir, "_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print("Done.")


if __name__ == "__main__":
    main()

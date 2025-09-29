# src/render_build.py
from __future__ import annotations
import argparse, json, re
from pathlib import Path
import pandas as pd

def _percentish_to_unit(x):
    """把看起來像百分比的數字（>1）轉為 0~1；保留 NaN -> 0"""
    s = pd.to_numeric(x, errors="coerce")
    s = s.fillna(0.0).astype(float)
    return s.where(s <= 1.0, s / 100.0)

def _fmt_pct(v: float) -> str:
    try:
        if pd.isna(v):
            return "-"
        # v 若已是 0~1，直接乘 100；否則視為已是百分比
        x = float(v)
        if x <= 1.0:
            x *= 100.0
        return f"{x:.2f}%"
    except Exception:
        return "-"

def _guess_hero_from_path(p: Path) -> str:
    # e.g. varus_aram_d2_plus_7d_sets.csv -> varus
    m = re.match(r"([a-z0-9]+)_", p.name, flags=re.I)
    return m.group(1).lower() if m else p.stem

def render_markdown(in_json: Path, sets_csv: Path) -> str:
    cfg = json.loads(in_json.read_text(encoding="utf-8"))

    # ---- 基本資訊 ----
    spec = cfg.get("spec", {})
    mode   = spec.get("mode", "").upper() or "ARAM"
    tier   = spec.get("tier", "")
    window = spec.get("window", "")

    hero = _guess_hero_from_path(sets_csv)

    # ---- 鞋子：優先信任 JSON ----
    boots = (cfg.get("build") or {}).get("boots")
    if not boots or boots == "鞋子":
        boots = "（尚未決定）"

    # ---- 常見出裝（sets_csv） ----
    sets_md = ""
    if sets_csv.exists():
        df = pd.read_csv(sets_csv, encoding="utf-8")
        if not df.empty:
            # 欄位對齊
            if "items" not in df.columns:
                # 兼容舊欄位（極少見）
                raise SystemExit("[error] sets_csv 缺少 items 欄位")

            # 兼容欄位命名
            if "set_pick_rate" not in df.columns and "pick_rate" in df.columns:
                df["set_pick_rate"] = df["pick_rate"]
            if "set_win_rate" not in df.columns and "win_rate" in df.columns:
                df["set_win_rate"] = df["win_rate"]

            # 數值正規化
            for col in ("set_pick_rate", "set_win_rate"):
                if col in df.columns:
                    df[col] = _percentish_to_unit(df[col])
                else:
                    df[col] = 0.0

            # 排序：選取率優先、勝率次之
            df = df.sort_values(["set_pick_rate", "set_win_rate"], ascending=[False, False])

            # 只顯示前 8 組
            topn = df.head(8).copy()

            # 渲染表格
            rows = ["| # | 出裝 | 勝率 | 選取率 |",
                    "|:-:|:-----|:----:|:------:|"]
            for i, r in enumerate(topn.itertuples(index=False), start=1):
                items_str = str(getattr(r, "items", ""))
                # 用「 | 」或「 > 」較好讀；這裡用「 | 」
                items_pretty = " | ".join(items_str.split("|")) if "|" in items_str else items_str
                wr = _fmt_pct(getattr(r, "set_win_rate", 0))
                pr = _fmt_pct(getattr(r, "set_pick_rate", 0))
                rows.append(f"| {i} | {items_pretty} | {wr} | {pr} |")
            sets_md = "\n".join(rows)
        else:
            sets_md = "_（無套裝資料）_"
    else:
        sets_md = "_（找不到套裝 CSV）_"

    # ---- 組裝 Markdown ----
    hdr = f"# {hero.title()} · {mode}\n"
    meta = []
    if tier:   meta.append(f"- **分段**：{tier}")
    if window: meta.append(f"- **視窗**：{window}")
    meta_s = "\n".join(meta)

    md = []
    md.append(hdr)
    if meta_s: md.append(meta_s)
    md.append("\n## 推薦鞋子\n")
    md.append(f"- {boots}\n")
    md.append("\n## 常見出裝（Actually Built Sets）\n")
    md.append(sets_md)
    md.append("")  # 結尾換行
    return "\n".join(md)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_json", required=True)
    ap.add_argument("--sets_csv", required=True)
    ap.add_argument("--out_md", required=True)
    args = ap.parse_args()

    out = render_markdown(Path(args.in_json), Path(args.sets_csv))
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).write_text(out, encoding="utf-8")
    print(f"[ok] wrote -> {args.out_md}")

if __name__ == "__main__":
    main()

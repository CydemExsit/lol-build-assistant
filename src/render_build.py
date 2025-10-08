# -*- coding: utf-8 -*-
import argparse
import os
from pathlib import Path

import pandas as pd

STYLE_IMG = 'width="32" height="32" style="margin-right:4px;border:1px solid #666;border-radius:4px;"'

def _mkdir_for(path: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def _img_row(items_img: str, items_names: str) -> str:
    # items_img: pipe 分隔的圖片 URL；items_names: pipe 分隔名稱 (備用 alt)
    urls  = [s for s in (items_img or "").split("|") if s]
    names = (items_names or "").split("|")
    if urls:
        tags = []
        for i,u in enumerate(urls):
            alt = names[i] if i < len(names) and names[i] else os.path.basename(u).split(".")[0]
            tags.append(f'<img src="{u}" alt="{alt}" {STYLE_IMG} />')
        return "".join(tags)
    # 沒有圖片就顯示名稱
    return "".join(names)

def render_markdown(sets_csv: str | os.PathLike[str], out_md: str | os.PathLike[str], *, topk: int = 8) -> Path:
    """Render a Markdown table from Lolalytics set data."""

    df = pd.read_csv(sets_csv)
    # 只保留有 5 件的列（保險）
    df = df[(df["items"].str.count(r"\|")==4) | (df["items"].str.count(r"\|")==4)]
    # 排序：先 Win 再 Games（網站的 Pick 是百分比，Games 才是樣本數）
    if "set_sample_size" in df.columns:
        df = df.sort_values(["set_win_rate","set_sample_size"], ascending=[False,False])
    else:
        df = df.sort_values(["set_win_rate"], ascending=[False])

    if topk > 0:
        df = df.head(topk)

    lines = []
    lines.append("| Set | Win | Pick | Games |")
    lines.append("|---|---:|---:|---:|")
    for _,row in df.iterrows():
        imgs  = _img_row(row.get("items_img",""), row.get("items",""))
        win   = f"{float(row['set_win_rate']):.2f}%"
        pick  = f"{float(row['set_pick_rate']):.2f}%"
        games = int(row.get("set_sample_size", 0))
        lines.append(f"| {imgs} | {win} | {pick} | {games} |")

    out_path = Path(out_md)
    _mkdir_for(str(out_path))
    with out_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[ok] wrote -> {out_path}")
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets_csv", required=True)
    ap.add_argument("--out_md", required=True)
    ap.add_argument("--topk", type=int, default=8)
    args = ap.parse_args()

    render_markdown(args.sets_csv, args.out_md, topk=args.topk)

if __name__ == "__main__":
    main()

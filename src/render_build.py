# -*- coding: utf-8 -*-
import argparse, json, os
import pandas as pd

def _mkdir_for(path: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def _fmt_pct(val) -> str:
    try:
        v = float(val)
    except:
        return ""
    return f"{v:.2f}%"

def _fmt_rate_fraction_to_pct(val) -> str:
    """輸入可能是 fraction(0~1) 或已經是百分比數值(>1)，做安全格式化。"""
    try:
        v = float(val)
    except:
        return ""
    if v <= 1.0:
        v *= 100.0
    return f"{v:.2f}%"

def _collect_img_map_from_json(obj) -> dict:
    """盡可能從 JSON 內挖出 name -> img 的對照（適配多種結構）。"""
    out = {}
    def rec(o):
        if isinstance(o, dict):
            # 典型: {"name": "...", "img": "http.../item64/..."}
            if "name" in o and "img" in o:
                name = str(o["name"]).strip()
                img = str(o["img"]).strip()
                if name and img.startswith("http"):
                    out[name] = img
            for k, v in o.items():
                rec(v)
        elif isinstance(o, list):
            for it in o:
                rec(it)
    rec(obj)
    return out

def _items_to_html(items_str: str, img_map: dict, items_img_str: str | None = None) -> str:
    names = [s.strip() for s in str(items_str).split("|") if s.strip()]
    urls = []
    if items_img_str:
        urls = [s.strip() for s in str(items_img_str).split("|")]
        if len(urls) != len(names) or not all(u.startswith("http") for u in urls):
            urls = [img_map.get(n, "") for n in names]
    else:
        urls = [img_map.get(n, "") for n in names]

    parts = []
    for n, u in zip(names, urls):
        if u:
            parts.append(
                f'<img src="{u}" alt="{n}" width="32" height="32" '
                f'style="margin-right:4px;border:1px solid #666;border-radius:4px;" />'
            )
        else:
            parts.append(n)  # 仍對不到就顯示名稱
    return "".join(parts)

def render(in_json: str, sets_csv: str, out_md: str) -> None:
    # 讀 JSON（用來拿 img 對照與可能的 Winning Items 區塊）
    data = {}
    if os.path.exists(in_json):
        with open(in_json, "r", encoding="utf-8") as f:
            data = json.load(f)

    img_map = _collect_img_map_from_json(data)

    # 讀 Actually Built Sets(5)
    sets_df = pd.read_csv(sets_csv)
    has_items_img = "items_img" in sets_df.columns

    # 產生 Set 欄（優先 items_img）
    sets_df["Set"] = sets_df.apply(
        lambda r: _items_to_html(
            r.get("items",""),
            img_map,
            r.get("items_img","") if has_items_img else None
        ),
        axis=1
    )

    # 排序（可用 pick 或 sample）
    if "set_sample_size" in sets_df.columns:
        sets_df = sets_df.sort_values(["set_sample_size","set_pick_rate","set_win_rate"], ascending=[False,False,False])
    else:
        sets_df = sets_df.sort_values(["set_pick_rate","set_win_rate"], ascending=[False,False])

    # 格式化數字
    sets_view = sets_df[["Set","set_win_rate","set_pick_rate"] + ([ "set_sample_size" ] if "set_sample_size" in sets_df.columns else [])].copy()
    sets_view.rename(columns={"set_win_rate":"Win","set_pick_rate":"Pick","set_sample_size":"Games"}, inplace=True)
    sets_view["Win"]  = sets_view["Win"].map(_fmt_pct)
    sets_view["Pick"] = sets_view["Pick"].map(_fmt_pct)
    if "Games" in sets_view.columns:
        sets_view["Games"] = sets_view["Games"].map(lambda x: f"{int(x):d}" if pd.notnull(x) else "")

    # 嘗試從 JSON 找 Winning Items（若不存在就略過）
    winning_rows = []
    def _collect_winning(obj):
        if isinstance(obj, list):
            for it in obj:
                if isinstance(it, dict) and ("img" in it) and ("win_rate" in it) and ("pick_rate" in it):
                    winning_rows.append(it)
        elif isinstance(obj, dict):
            for v in obj.values():
                _collect_winning(v)
    _collect_winning(data)

    winning_md = ""
    if winning_rows:
        wdf = pd.DataFrame(winning_rows)
        # 只挑有圖片的
        wdf = wdf[pd.notnull(wdf["img"])]
        # 排序（以 pick_rate 降序）
        if "pick_rate" in wdf.columns:
            wdf = wdf.sort_values("pick_rate", ascending=False)
        wdf = wdf[["img","name","win_rate","pick_rate"]].copy()

        # 轉成 MD：圖片 + 數值（win/pick 若為 fraction 則 *100）
        def _cell_img(row):
            url = row["img"]
            name = row.get("name","") or ""
            return f'<img src="{url}" alt="{name}" width="32" height="32" style="margin-right:4px;border:1px solid #666;border-radius:4px;" /> {name}'
        wdf["Item"] = wdf.apply(_cell_img, axis=1)
        wdf["Win"]  = wdf["win_rate"].map(_fmt_rate_fraction_to_pct)
        wdf["Pick"] = wdf["pick_rate"].map(_fmt_rate_fraction_to_pct)
        wdf = wdf[["Item","Win","Pick"]]

        winning_md = wdf.to_markdown(index=False)

    # 輸出 MD
    _mkdir_for(out_md)
    lines = []
    lines.append("| Set | Win | Pick | Games |")
    lines.append("|---|---:|---:|---:|")
    for _, r in sets_view.iterrows():
        games = r["Games"] if "Games" in sets_view.columns else ""
        lines.append(f"| {r['Set']} | {r['Win']} | {r['Pick']} | {games} |")

    md = "\n".join(lines)
    if winning_md:
        md += "\n\n## Winning Items\n\n" + winning_md

    with open(out_md, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"[ok] wrote -> {out_md}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_json", required=True)
    ap.add_argument("--sets_csv", required=True)
    ap.add_argument("--out_md", required=True)
    args = ap.parse_args()
    render(args.in_json, args.sets_csv, args.out_md)

if __name__ == "__main__":
    main()

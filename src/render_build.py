from __future__ import annotations
import argparse, json, re
from pathlib import Path
import pandas as pd

# ====== 取鞋：從 winning.csv 精準挑一雙 ======================================

UPGRADED_HINTS = [
    "之靴","護脛","艾歐尼亞之靴","明朗之靴","狂戰士護脛","法師之靴","水星之靴",
    "鋼鐵護脛","輕靈之靴","機動靴","離群之靴",
    "Greaves","Treads","Sorcerer","Ionian","Mercury","Plated","Swiftness","Mobility"
]

def _normalize_rates(df: pd.DataFrame) -> pd.DataFrame:
    for col in ("win_rate", "pick_rate"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            df[col] = df[col].where(df[col] <= 1, df[col]/100.0)
    return df

def _is_boot_row(name: str) -> bool:
    if not isinstance(name, str): return False
    n = name.strip().lower()
    if not n: return False
    if n in {"鞋子","boots","boots of speed"}:  # 基礎靴
        return True
    return any(k.lower() in n for k in UPGRADED_HINTS)

def _is_upgraded_boot(name: str) -> bool:
    n = (name or "").lower()
    if n in {"鞋子","boots","boots of speed"}: return False
    return any(k.lower() in n for k in UPGRADED_HINTS)

def pick_boot_from_winning(winning_csv: str) -> str | None:
    p = Path(winning_csv)
    if not p.exists(): return None
    df = pd.read_csv(p)
    if df.empty or "name" not in df.columns: return None
    df = _normalize_rates(df)
    boots = df[df["name"].apply(_is_boot_row)].copy()
    if boots.empty: return None

    upg = boots[boots["name"].apply(_is_upgraded_boot)].copy()
    cand = upg if not upg.empty else boots

    # 同名合併：pick_rate 加總、win_rate 平均，然後 pick desc / win desc
    cand = cand.groupby("name", as_index=False).agg(
        pick_rate=("pick_rate","sum"),
        win_rate=("win_rate","mean")
    ).sort_values(["pick_rate","win_rate"], ascending=[False, False])

    return str(cand.iloc[0]["name"])

# ====== Markdown 渲染 ========================================================

def render_card(data: dict, sets_csv: str) -> str:
    hero = data.get("hero") or data.get("spec", {}).get("hero") or "Hero"
    spec = data.get("spec", {})
    mode = spec.get("mode", "ARAM")
    tier = spec.get("tier", "d2_plus")
    window = spec.get("window", "7d")
    build = data.get("build", {})
    boots = build.get("boots") or "（未定）"

    # 讀取 sets.csv，取前 10 組（依 set_pick_rate desc）
    top_sets_md = ""
    p = Path(sets_csv)
    if p.exists():
        df = pd.read_csv(p)
        if not df.empty and {"items","set_pick_rate","set_win_rate"} <= set(df.columns):
            df["set_pick_rate"] = pd.to_numeric(df["set_pick_rate"], errors="coerce").fillna(0)
            df["set_win_rate"] = pd.to_numeric(df["set_win_rate"], errors="coerce").fillna(0)
            df = df.sort_values(["set_pick_rate","set_win_rate"], ascending=[False, False]).head(10)
            lines = []
            for _, row in df.iterrows():
                items = str(row["items"]).split("|")
                pr = row["set_pick_rate"]
                wr = row["set_win_rate"]
                # 介面顯示成百分比
                pr_show = f"{pr*100:.2f}%"
                wr_show = f"{wr*100:.2f}%"
                lines.append(f"- `{wr_show} / {pr_show}`  —  " + " > ".join(items))
            top_sets_md = "\n".join(lines)

    md = []
    md.append(f"# {hero.title()} — {mode}（{tier}，{window}）")
    md.append("")
    md.append(f"**推薦鞋子：** {boots}")
    md.append("")
    if top_sets_md:
        md.append("## Top Sets")
        md.append(top_sets_md)
        md.append("")

    # 額外：把演算法輸出的 order（如果有）展示一下
    order = build.get("order") or []
    if order:
        md.append("## Runes / Order（原始 JSON 中的順序資訊，僅供參考）")
        md.append(" > " + " / ".join(map(str, order)))
        md.append("")

    return "\n".join(md).strip() + "\n"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_json", required=True)
    ap.add_argument("--sets_csv", required=True)
    ap.add_argument("--out_md", required=True)
    args = ap.parse_args()

    # 讀 JSON
    data = json.loads(Path(args.in_json).read_text(encoding="utf-8"))

    # 從 sets_csv 推回 winning.csv 路徑
    sets_path = Path(args.sets_csv)
    winning_csv = str(sets_path).replace("_sets.csv", "_winning.csv")

    # 以 winning.csv 覆寫 JSON 內 boots
    boot_choice = pick_boot_from_winning(winning_csv)
    if boot_choice:
        data.setdefault("build", {})["boots"] = boot_choice
        print(f"[ok] boots -> {boot_choice}")
    else:
        # 沒抓到也不要中斷
        print("[warn] boots -> 無法從 winning.csv 判定，沿用 JSON 內容")

    # Render
    card = render_card(data, args.sets_csv)
    Path(args.out_md).write_text(card, encoding="utf-8")
    print(f"[ok] wrote -> {args.out_md}")

if __name__ == "__main__":
    main()

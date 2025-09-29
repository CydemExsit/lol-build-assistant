from pathlib import Path
import json, glob

OUT = Path("outputs/index.md")
rows = []
for fp in sorted(glob.glob("outputs/*_aram_7d.json")):
    data = json.loads(Path(fp).read_text(encoding="utf-8"))
    hero = Path(fp).name.split("_")[0]
    boots = data["build"]["boots"]
    order_list = [str(x) for x in data.get("build", {}).get("order", []) if x is not None and str(x) != "nan"]
    order = " → ".join(order_list)
    mdfile = Path(fp).with_suffix(".md").name
    rows.append(f"- **{hero}**｜鞋：{boots}｜順序：`{order}` ｜ [卡片]({mdfile})")

OUT.write_text("# ARAM 7d Build 索引\n\n" + "\n".join(rows) + "\n", encoding="utf-8")
print(f"[ok] wrote -> {OUT}")

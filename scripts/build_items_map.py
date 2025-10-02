# -*- coding: utf-8 -*-
import argparse, os, csv, json, datetime, requests
VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
DATA_URL = "https://ddragon.leagueoflegends.com/cdn/{ver}/data/{lang}/item.json"


def fetch_json(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def ensure_dir(p):
    if p:
        os.makedirs(p, exist_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="zh_TW")
    ap.add_argument("--out", default="data/ref/items_map.csv")
    args = ap.parse_args()

    versions = fetch_json(VERSIONS_URL)
    ver = versions[0]

    data_zh = fetch_json(DATA_URL.format(ver=ver, lang=args.lang))
    data_en = fetch_json(DATA_URL.format(ver=ver, lang="en_US"))

    items_zh = data_zh.get("data", {})
    items_en = data_en.get("data", {})

    rows = []
    for item_id, meta_zh in items_zh.items():
        meta_en = items_en.get(item_id, {})
        rows.append({
            "item_id": int(item_id),
            "en_name": meta_en.get("name", ""),
            "zh_tw_name": meta_zh.get("name", ""),
            "tags": ",".join(meta_en.get("tags", [])),
            "ddragon_version": ver,
        })

    out_dir = os.path.dirname(os.path.abspath(args.out))
    ensure_dir(out_dir)

    # 版本化輸出：items_map_{ver}.csv + 最新副本 items_map.csv
    versioned = os.path.join(out_dir, f"items_map_{ver}.csv")
    with open(versioned, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["item_id","en_name","zh_tw_name","tags","ddragon_version"])
        w.writeheader()
        for r in sorted(rows, key=lambda x: x["item_id"]):
            w.writerow(r)

    # 複製一份為 items_map.csv（避免 Windows 權限問題不用 symlink）
    with open(versioned, "r", encoding="utf-8") as src, open(args.out, "w", encoding="utf-8") as dst:
        dst.write(src.read())

    # 寫入中繼資料
    meta_path = os.path.join(out_dir, "items_map_meta.json")
    meta = {
        "ddragon_version": ver,
        "generated_at": datetime.datetime.now().astimezone().isoformat(),
        "row_count": len(rows),
        "source": {
            "versions": VERSIONS_URL,
            "item_zh": DATA_URL.format(ver=ver, lang=args.lang),
            "item_en": DATA_URL.format(ver=ver, lang="en_US"),
        },
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"Wrote: {versioned}")
    print(f"Wrote: {args.out}")
    print(f"Wrote: {meta_path}")


if __name__ == "__main__":
    main()
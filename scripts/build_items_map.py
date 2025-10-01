# -*- coding: utf-8 -*-
import argparse, os, csv, requests

VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
DATA_URL = "https://ddragon.leagueoflegends.com/cdn/{ver}/data/{lang}/item.json"

def fetch_json(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()

def ensure_dir(p):
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
        name_zh = meta_zh.get("name", "")
        meta_en = items_en.get(item_id, {})
        name_en = meta_en.get("name", "")
        tags = ",".join(meta_en.get("tags", []))
        row = {
            "item_id": int(item_id),
            "en_name": name_en,
            "zh_tw_name": name_zh,
            "tags": tags
        }
        rows.append(row)

    ensure_dir(os.path.dirname(args.out) or ".")
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["item_id","en_name","zh_tw_name","tags"])
        w.writeheader()
        for r in sorted(rows, key=lambda x: x["item_id"]):
            w.writerow(r)

if __name__ == "__main__":
    main()

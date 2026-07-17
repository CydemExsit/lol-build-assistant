from __future__ import annotations

import argparse
import csv
import datetime
import json
import urllib.request
from pathlib import Path


VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
DATA_URL = "https://ddragon.leagueoflegends.com/cdn/{ver}/data/{lang}/item.json"
FIELD_NAMES = [
    "item_id",
    "en_name",
    "zh_tw_name",
    "tags",
    "from",
    "into",
    "gold_total",
    "gold_base",
    "gold_purchasable",
    "maps",
    "ddragon_version",
]


def fetch_json(url: str) -> dict | list:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "lol-build-assistant/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", default="zh_TW")
    parser.add_argument("--out", default="data/ref/items_map.csv")
    args = parser.parse_args()

    version = fetch_json(VERSIONS_URL)[0]
    data_zh = fetch_json(DATA_URL.format(ver=version, lang=args.lang))
    data_en = fetch_json(DATA_URL.format(ver=version, lang="en_US"))
    items_zh = data_zh.get("data", {})
    items_en = data_en.get("data", {})

    rows = []
    for item_id, meta_zh in items_zh.items():
        meta_en = items_en.get(item_id, {})
        rows.append(
            {
                "item_id": int(item_id),
                "en_name": meta_en.get("name", ""),
                "zh_tw_name": meta_zh.get("name", ""),
                "tags": ",".join(meta_en.get("tags", [])),
                "from": ",".join(meta_en.get("from", [])),
                "into": ",".join(meta_en.get("into", [])),
                "gold_total": int(meta_en.get("gold", {}).get("total") or 0),
                "gold_base": int(meta_en.get("gold", {}).get("base") or 0),
                "gold_purchasable": bool(meta_en.get("gold", {}).get("purchasable")),
                "maps": ",".join(
                    sorted(key for key, enabled in (meta_en.get("maps") or {}).items() if enabled)
                ),
                "ddragon_version": version,
            }
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=FIELD_NAMES)
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: row["item_id"]))

    meta_path = out_path.parent / "items_map_meta.json"
    metadata = {
        "ddragon_version": version,
        "generated_at": datetime.datetime.now().astimezone().isoformat(),
        "row_count": len(rows),
        "source": {
            "versions": VERSIONS_URL,
            "item_zh": DATA_URL.format(ver=version, lang=args.lang),
            "item_en": DATA_URL.format(ver=version, lang="en_US"),
        },
    }
    with meta_path.open("w", encoding="utf-8") as output:
        json.dump(metadata, output, ensure_ascii=False, indent=2)

    print(f"Wrote: {out_path}")
    print(f"Wrote: {meta_path}")


if __name__ == "__main__":
    main()

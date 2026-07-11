from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def load_items_map(path: str | Path = "data/ref/items_map.csv") -> dict[int, dict[str, Any]]:
    items: dict[int, dict[str, Any]] = {}
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            item_id = int(row["item_id"])
            tags = [tag for tag in (row.get("tags") or "").split(",") if tag]
            into = [value for value in (row.get("into") or "").split(",") if value]
            from_items = [value for value in (row.get("from") or "").split(",") if value]
            maps = [value for value in (row.get("maps") or "").split(",") if value]
            items[item_id] = {
                "item_id": item_id,
                "en_name": row.get("en_name") or "",
                "zh_tw_name": row.get("zh_tw_name") or "",
                "tags": tags,
                "from": from_items,
                "into": into,
                "gold_total": _to_int(row.get("gold_total")),
                "gold_base": _to_int(row.get("gold_base")),
                "gold_purchasable": _to_bool(row.get("gold_purchasable")),
                "maps": maps,
                "ddragon_version": row.get("ddragon_version") or "",
            }
    return items


def _to_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    return str(value).strip().lower() in {"1", "true", "yes"}


def enrich_item(item: dict[str, Any], item_map: dict[int, dict[str, Any]]) -> dict[str, Any]:
    item_id = int(item["item_id"])
    meta = item_map.get(item_id, {})
    return {
        "item_id": item_id,
        "name": meta.get("en_name") or item.get("name") or str(item_id),
        "zh_tw_name": meta.get("zh_tw_name") or "",
        "tags": meta.get("tags") or [],
        "from": meta.get("from") or [],
        "into": meta.get("into") or [],
        "gold_total": meta.get("gold_total"),
        "gold_purchasable": meta.get("gold_purchasable"),
        "maps": meta.get("maps") or [],
        "win_rate": item.get("win_rate"),
        "games": item.get("games"),
    }


def is_boot(item: dict[str, Any]) -> bool:
    return "Boots" in set(item.get("tags") or [])


def is_completed_non_boot_item(item: dict[str, Any]) -> bool:
    tags = set(item.get("tags") or [])
    if "Boots" in tags or "Consumable" in tags or "Trinket" in tags or "Jungle" in tags:
        return False
    if item.get("into"):
        return False
    gold_total = item.get("gold_total")
    if isinstance(gold_total, int) and gold_total < 1600:
        return False
    if item.get("gold_purchasable") is False:
        return False
    return True

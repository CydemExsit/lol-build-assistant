from __future__ import annotations

import csv
import datetime
import json
import urllib.request
from pathlib import Path
from typing import Any


VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
DATA_URL = "https://ddragon.leagueoflegends.com/cdn/{version}/data/{language}/{kind}.json"
ITEM_FIELD_NAMES = [
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


def fetch_json(url: str) -> dict[str, Any] | list[Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "lol-build-assistant/2.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def latest_version() -> str:
    versions = fetch_json(VERSIONS_URL)
    if not isinstance(versions, list) or not versions:
        raise RuntimeError("Data Dragon versions response is empty")
    return str(versions[0])


def _data_url(version: str, language: str, kind: str) -> str:
    return DATA_URL.format(version=version, language=language, kind=kind)


def _atomic_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding=encoding)
    temporary.replace(path)


def _write_items(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=ITEM_FIELD_NAMES)
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: row["item_id"]))
    temporary.replace(path)


def update_static_data(
    *,
    items_path: str | Path = "data/ref/items_map.csv",
    champions_path: str | Path = "data/ref/champions_map.json",
    metadata_path: str | Path = "data/ref/items_map_meta.json",
    language: str = "zh_TW",
    force: bool = False,
) -> dict[str, Any]:
    items_target = Path(items_path)
    champions_target = Path(champions_path)
    metadata_target = Path(metadata_path)
    version = latest_version()

    current = {}
    if metadata_target.exists():
        try:
            current = json.loads(metadata_target.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            current = {}
    if (
        not force
        and current.get("ddragon_version") == version
        and items_target.exists()
        and champions_target.exists()
    ):
        return {"updated": False, "ddragon_version": version, "reason": "already_current"}

    item_zh_url = _data_url(version, language, "item")
    item_en_url = _data_url(version, "en_US", "item")
    champion_zh_url = _data_url(version, language, "champion")
    champion_en_url = _data_url(version, "en_US", "champion")
    item_zh = fetch_json(item_zh_url).get("data", {})
    item_en = fetch_json(item_en_url).get("data", {})
    champion_zh = fetch_json(champion_zh_url).get("data", {})
    champion_en = fetch_json(champion_en_url).get("data", {})

    item_rows = []
    for item_id, meta_zh in item_zh.items():
        meta_en = item_en.get(item_id, {})
        item_rows.append(
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
                    sorted(
                        key
                        for key, enabled in (meta_en.get("maps") or {}).items()
                        if enabled
                    )
                ),
                "ddragon_version": version,
            }
        )

    champions: dict[str, dict[str, Any]] = {}
    for champion_id, meta_en in champion_en.items():
        meta_zh = champion_zh.get(champion_id, {})
        slug = "".join(char for char in champion_id.lower() if char.isalnum())
        champions[slug] = {
            "id": champion_id,
            "key": int(meta_en.get("key") or 0),
            "en_name": meta_en.get("name", champion_id),
            "zh_tw_name": meta_zh.get("name", meta_en.get("name", champion_id)),
            "tags": list(meta_en.get("tags") or []),
            "ddragon_version": version,
        }

    generated_at = datetime.datetime.now().astimezone().isoformat()
    metadata = {
        "ddragon_version": version,
        "generated_at": generated_at,
        "row_count": len(item_rows),
        "champion_count": len(champions),
        "source": {
            "versions": VERSIONS_URL,
            "item_zh": item_zh_url,
            "item_en": item_en_url,
            "champion_zh": champion_zh_url,
            "champion_en": champion_en_url,
        },
    }
    _write_items(items_target, item_rows)
    _atomic_text(
        champions_target,
        json.dumps(champions, ensure_ascii=False, indent=2) + "\n",
    )
    _atomic_text(
        metadata_target,
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
    )
    return {
        "updated": True,
        "ddragon_version": version,
        "items": len(item_rows),
        "champions": len(champions),
    }


def local_data_status(
    *,
    metadata_path: str | Path = "data/ref/items_map_meta.json",
    champions_path: str | Path = "data/ref/champions_map.json",
) -> dict[str, Any]:
    metadata_target = Path(metadata_path)
    if not metadata_target.exists():
        return {"ok": False, "error": "items_map_meta.json is missing"}
    try:
        metadata = json.loads(metadata_target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": True,
        "ddragon_version": metadata.get("ddragon_version"),
        "generated_at": metadata.get("generated_at"),
        "item_count": metadata.get("row_count"),
        "champion_count": metadata.get("champion_count"),
        "champions_available": Path(champions_path).exists(),
    }

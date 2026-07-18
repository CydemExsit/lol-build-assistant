from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .compliance import validate_static_recommendation
from .history import route_key
from .items import is_boot, is_completed_non_boot_item, load_items_map


def _component_ids(item_id: int, item_map: dict[int, dict[str, Any]]) -> set[int]:
    found: set[int] = set()
    stack = [item_id]
    while stack:
        current = stack.pop()
        for raw_component in item_map.get(current, {}).get("from") or []:
            component_id = int(raw_component)
            if component_id not in found:
                found.add(component_id)
                stack.append(component_id)
    return found


def audit_recommendation(result: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        validate_static_recommendation(result)
    except ValueError as exc:
        errors.append(str(exc))

    routes = result.get("build", {}).get("routes") or []
    if len(routes) < 2:
        warnings.append("only one static route is available")

    item_map = load_items_map()
    seen_routes: set[str] = set()
    starter_count = 0
    for index, route in enumerate(routes, start=1):
        items = route.get("items") or []
        ids = [int(item.get("item_id") or 0) for item in items]
        prefix = f"route {index}"
        if len(items) != 5:
            errors.append(f"{prefix} does not contain exactly five items")
        if len(ids) != len(set(ids)):
            errors.append(f"{prefix} contains duplicate items")
        key = route_key(route)
        if key in seen_routes:
            errors.append(f"{prefix} duplicates another route")
        seen_routes.add(key)
        for item_id in ids:
            metadata = item_map.get(item_id)
            if not metadata:
                errors.append(f"{prefix} references unknown item {item_id}")
            elif is_boot(metadata) or not is_completed_non_boot_item(metadata):
                errors.append(f"{prefix} item {item_id} is not a completed non-boot item")
        stats = route.get("set_stats") or {}
        if int(stats.get("games") or 0) <= 0:
            errors.append(f"{prefix} is missing Actually Built Sets sample data")
        if not route.get("confidence"):
            warnings.append(f"{prefix} has no confidence label")
        starter = route.get("starter_option") or {}
        if starter:
            starter_count += 1
            starter_items = starter.get("items") or []
            starter_ids = [int(item.get("item_id") or 0) for item in starter_items]
            target_id = int((starter.get("target") or {}).get("item_id") or 0)
            if ids and target_id != ids[0]:
                errors.append(f"{prefix} starter does not target its first completed item")
            calculated_gold = sum(int((item_map.get(item_id) or {}).get("gold_total") or 0) for item_id in starter_ids)
            if calculated_gold != int(starter.get("total_gold") or 0):
                errors.append(f"{prefix} starter gold total is inconsistent")
            components = _component_ids(target_id, item_map)
            source_name = starter.get("source")
            matching_components = [item_id for item_id in starter_ids if item_id in components]
            if source_name in {"data_dragon_component_tree", "lolalytics_starting_items"} and not matching_components:
                errors.append(f"{prefix} starter does not advance its first completed item")
            if source_name == "route_requirement" and 3070 not in starter_ids:
                errors.append(f"{prefix} tear requirement starter is missing Tear of the Goddess")

    source = result.get("build", {}).get("source") or {}
    data_health = source.get("data_health") or {}
    if data_health.get("level") == "limited":
        warnings.append("aggregate data health is limited")

    boots = result.get("build", {}).get("boot_options") or []
    for boot in boots:
        item_id = int(boot.get("item_id") or 0)
        if item_id in item_map and not is_boot(item_map[item_id]):
            errors.append(f"boot option {item_id} is not tagged as boots")

    return {
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "metrics": {
            "routes": len(routes),
            "route_starters": starter_count,
            "boot_options": len(boots),
            "champions_analysed": int(source.get("champions_analysed") or 0),
            "data_health": data_health.get("level") or "unknown",
        },
    }


def audit_file(path: str | Path) -> dict[str, Any]:
    result = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError("recommendation file must contain a JSON object")
    return audit_recommendation(result)

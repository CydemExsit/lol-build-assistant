from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .data_dragon import local_data_status
from .history import DEFAULT_HISTORY_PATH, history_metrics


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def age_hours(value: Any) -> float | None:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return None
    delta = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
    return max(0.0, delta.total_seconds() / 3600.0)


def assess_recommendation_data(
    *,
    fetched_at: str | None,
    champions_analysed: int,
    built_sets: int,
    boots: int,
    popular_items: int,
    winning_items: int,
    max_age_hours: int = 168,
) -> dict[str, Any]:
    age = age_hours(fetched_at)
    checks = {
        "champion_sample": champions_analysed >= 1_000_000,
        "built_sets": built_sets > 0,
        "boots": boots > 0,
        "popular_items": popular_items > 0,
        "winning_items": winning_items > 0,
        "fresh": age is not None and age <= max_age_hours,
    }
    score = round(sum(1 for passed in checks.values() if passed) / len(checks) * 100)
    if all(checks.values()):
        level, label = "healthy", "資料完整"
    elif checks["built_sets"] and checks["popular_items"] and checks["winning_items"]:
        level, label = "usable", "可用但需留意"
    else:
        level, label = "limited", "資料有限"
    return {
        "level": level,
        "label": label,
        "score": score,
        "fetched_at": fetched_at,
        "age_hours": round(age, 1) if age is not None else None,
        "checks": checks,
    }


def system_health(
    *,
    recommendation_path: str | Path = "data/processed/live_recommendation.json",
    cache_dir: str | Path = "data/cache",
    history_path: str | Path = DEFAULT_HISTORY_PATH,
) -> dict[str, Any]:
    cache_files = list(Path(cache_dir).glob("*.json")) if Path(cache_dir).exists() else []
    recommendation_target = Path(recommendation_path)
    recommendation_updated_at = (
        datetime.fromtimestamp(recommendation_target.stat().st_mtime, tz=timezone.utc).astimezone().isoformat()
        if recommendation_target.exists()
        else None
    )
    item_status = local_data_status()
    item_status["age_hours"] = age_hours(item_status.get("generated_at"))
    return {
        "item_map": item_status,
        "cache": {
            "json_files": len(cache_files),
            "size_bytes": sum(path.stat().st_size for path in cache_files),
        },
        "recommendation": {
            "available": recommendation_target.exists(),
            "updated_at": recommendation_updated_at,
        },
        "history": history_metrics(history_path),
    }

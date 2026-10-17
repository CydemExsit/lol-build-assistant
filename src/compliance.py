from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any


COMPLIANCE_MODE = "static_pregame_v1"
RIOT_LOL_POLICY_URL = "https://developer.riotgames.com/docs/lol"
RIOT_GENERAL_POLICY_URL = "https://developer.riotgames.com/policies/general"
LEGAL_NOTICE = (
    "LoL Build Assistant isn't endorsed by Riot Games and doesn't reflect the views or opinions "
    "of Riot Games or anyone officially involved in producing or managing Riot Games properties. "
    "Riot Games, and all associated properties are trademarks or registered trademarks of Riot Games, Inc."
)

PRIVATE_OR_DYNAMIC_KEYS = {
    "riotid",
    "riot_id",
    "riotidgamename",
    "riotidtagline",
    "summonername",
    "puuid",
    "gametime",
    "currentgold",
    "scores",
    "events",
    "eventdata",
}
STATIC_GAME_FIELDS = ("gameMode", "mapName", "mapNumber", "mapTerrain")
STATIC_PLAYER_FIELDS = (
    "champion_name",
    "champion_id",
    "champion_slug",
    "team",
    "position",
    "is_bot",
)


def public_player(player: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(player, dict):
        return None
    return {key: player.get(key) for key in STATIC_PLAYER_FIELDS if key in player}


def public_game(game: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(game, dict):
        return {}
    return {key: game.get(key) for key in STATIC_GAME_FIELDS if key in game}


def _forbidden_paths(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key).lower() in PRIVATE_OR_DYNAMIC_KEYS:
                found.append(child_path)
            found.extend(_forbidden_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_forbidden_paths(child, f"{path}[{index}]"))
    return found


def validate_static_recommendation(result: dict[str, Any]) -> None:
    forbidden = _forbidden_paths(result)
    if forbidden:
        raise ValueError("static recommendation contains private or dynamic fields: " + ", ".join(forbidden))
    session = result.get("session") or {}
    if session.get("scope") != COMPLIANCE_MODE or session.get("frozen") is not True:
        raise ValueError("recommendation is missing the static pre-game freeze marker")
    routes = result.get("build", {}).get("routes") or []
    if not routes:
        raise ValueError("static recommendation must contain at least one aggregate-data route")


def freeze_static_recommendation(
    result: dict[str, Any],
    *,
    match_key: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    frozen = copy.deepcopy(result)
    timestamp = generated_at or datetime.now(timezone.utc).astimezone().isoformat()
    frozen["active_player"] = public_player(frozen.get("active_player"))
    frozen["game"] = public_game(frozen.get("game"))
    frozen["session"] = {
        "match_key": match_key,
        "generated_at": timestamp,
        "revision": f"{match_key}:{timestamp}",
        "scope": COMPLIANCE_MODE,
        "frozen": True,
        "updates_during_match": False,
    }
    frozen["compliance"] = {
        "mode": COMPLIANCE_MODE,
        "data_used": [
            "champions and teams visible for the current match",
            "LoLalytics aggregate pre-game build statistics",
            "Riot Data Dragon static item metadata",
            "curated static champion damage-type profiles",
            "local feedback from completed prior recommendations",
        ],
        "not_used": [
            "player identifiers or opponent profile analysis",
            "current gold, items, scores, events, cooldowns, or positions",
            "real-time recommendation changes during the match",
        ],
        "policy_urls": [RIOT_LOL_POLICY_URL, RIOT_GENERAL_POLICY_URL],
        "legal_notice": LEGAL_NOTICE,
    }
    validate_static_recommendation(frozen)
    return frozen

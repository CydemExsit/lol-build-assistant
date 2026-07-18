from __future__ import annotations

import copy
import hashlib
import json
import ssl
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://127.0.0.1:2999/liveclientdata"
ENDPOINTS = {
    "playerlist": "/playerlist",
    "activeplayer": "/activeplayer",
    "activeplayername": "/activeplayername",
    "gamestats": "/gamestats",
    "eventdata": "/eventdata",
    "allgamedata": "/allgamedata",
}
PREGAME_ENDPOINTS = {
    "playerlist": "/playerlist",
    "activeplayer": "/activeplayer",
    "activeplayername": "/activeplayername",
    "gamestats": "/gamestats",
}

PRIVATE_PLAYER_FIELDS = {
    "riotId",
    "riotIdGameName",
    "riotIdTagLine",
    "summonerName",
}
STATIC_PLAYER_FIELDS = {
    "championName",
    "rawChampionName",
    "team",
    "position",
    "isBot",
    "isActivePlayer",
}
STATIC_GAME_FIELDS = {"gameMode", "mapName", "mapNumber", "mapTerrain"}


@dataclass(frozen=True)
class LivePlayer:
    riot_id: str
    champion_name: str
    champion_id: str | None
    team: str
    position: str | None
    is_bot: bool
    level: int | None
    is_active: bool = False

    @property
    def champion_slug(self) -> str:
        return champion_slug(self.champion_id or self.champion_name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "champion_name": self.champion_name,
            "champion_id": self.champion_id,
            "champion_slug": self.champion_slug,
            "team": self.team,
            "position": self.position,
            "is_bot": self.is_bot,
            "is_active": self.is_active,
        }


def _json_loads(payload: bytes) -> Any:
    return json.loads(payload.decode("utf-8-sig"))


def fetch_live_data(
    *,
    base_url: str = DEFAULT_BASE_URL,
    timeout: float = 5.0,
    endpoints: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Read Riot's local Live Client Data API.

    The game client serves this API with a self-signed certificate, so this
    uses an unverified SSL context intentionally for localhost only.
    """

    selected = endpoints or PREGAME_ENDPOINTS
    ssl_context = ssl._create_unverified_context()
    data: dict[str, Any] = {}
    for name, path in selected.items():
        url = base_url.rstrip("/") + path
        with urllib.request.urlopen(url, timeout=timeout, context=ssl_context) as response:
            data[name] = _json_loads(response.read())
    return data


def _identity_values(value: dict[str, Any]) -> set[str]:
    identities = {
        str(value.get(field) or "").strip().lower()
        for field in PRIVATE_PLAYER_FIELDS
        if value.get(field)
    }
    game_name = str(value.get("riotIdGameName") or "").strip()
    tag_line = str(value.get("riotIdTagLine") or "").strip()
    if game_name and tag_line:
        identities.add(f"{game_name}#{tag_line}".lower())
    return identities


def _retain_fields(payload: dict[str, Any], allowed: set[str]) -> None:
    for key in tuple(payload):
        if key not in allowed:
            payload.pop(key, None)


def sanitize_live_data(data: dict[str, Any]) -> dict[str, Any]:
    """Retain only player-visible facts needed for one static pre-game result."""

    sanitized = copy.deepcopy(data)
    active = sanitized.get("activeplayer") if isinstance(sanitized.get("activeplayer"), dict) else {}
    all_game_data = sanitized.get("allgamedata") if isinstance(sanitized.get("allgamedata"), dict) else {}
    if not active and isinstance(all_game_data.get("activePlayer"), dict):
        active = all_game_data["activePlayer"]
    active_identities = _identity_values(active)
    active_name = str(sanitized.get("activeplayername") or "").strip().lower()
    if active_name:
        active_identities.add(active_name)

    player_groups: list[list[dict[str, Any]]] = []
    if isinstance(sanitized.get("playerlist"), list):
        player_groups.append(sanitized["playerlist"])
    if isinstance(all_game_data.get("allPlayers"), list):
        player_groups.append(all_game_data["allPlayers"])
    for players in player_groups:
        for player in players:
            if not isinstance(player, dict):
                continue
            player["isActivePlayer"] = bool(active_identities & _identity_values(player))
            _retain_fields(player, STATIC_PLAYER_FIELDS)

    if isinstance(sanitized.get("activeplayer"), dict):
        sanitized["activeplayer"] = {}
    if "activeplayername" in sanitized:
        sanitized["activeplayername"] = ""

    if isinstance(sanitized.get("gamestats"), dict):
        _retain_fields(sanitized["gamestats"], STATIC_GAME_FIELDS)
    sanitized.pop("eventdata", None)
    if isinstance(all_game_data, dict):
        if isinstance(all_game_data.get("gameData"), dict):
            _retain_fields(all_game_data["gameData"], STATIC_GAME_FIELDS)
        all_game_data.pop("activePlayer", None)
        all_game_data.pop("events", None)
        _retain_fields(all_game_data, {"allPlayers", "gameData"})
    return sanitized


def save_snapshot(
    data: dict[str, Any],
    out_dir: str | Path | None = None,
    *,
    sanitize: bool = True,
) -> Path:
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")
    target = Path(out_dir) if out_dir else Path("data/raw") / f"live_{stamp}"
    target.mkdir(parents=True, exist_ok=True)
    snapshot_data = sanitize_live_data(data) if sanitize else data
    for name, payload in snapshot_data.items():
        (target / f"{name}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    (target / "snapshot_meta.json").write_text(
        json.dumps(
            {
                "captured_at": datetime.now(timezone.utc).astimezone().isoformat(),
                "source": DEFAULT_BASE_URL,
                "endpoints": sorted(data),
                "scope": "static_pregame",
                "sanitized": bool(sanitize),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return target


def capture_snapshot(out_dir: str | Path | None = None, timeout: float = 5.0) -> Path:
    return save_snapshot(fetch_live_data(timeout=timeout), out_dir=out_dir)


def load_snapshot(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if p.is_dir():
        data: dict[str, Any] = {}
        for name in ENDPOINTS:
            fp = p / f"{name}.json"
            if fp.exists():
                data[name] = json.loads(fp.read_text(encoding="utf-8-sig"))
        meta = p / "snapshot_meta.json"
        if meta.exists():
            data["snapshot_meta"] = json.loads(meta.read_text(encoding="utf-8-sig"))
        return data
    payload = json.loads(p.read_text(encoding="utf-8-sig"))
    if "allPlayers" in payload and "activePlayer" in payload:
        return {"allgamedata": payload}
    return payload


def champion_id_from_raw(raw_name: str | None) -> str | None:
    if not raw_name:
        return None
    marker = "game_character_displayname_"
    lowered = raw_name.lower()
    if marker in lowered:
        marker_index = lowered.index(marker)
        return raw_name[marker_index + len(marker) :]
    if lowered.startswith("character_") and lowered.endswith("_name"):
        return raw_name[len("Character_") : -len("_Name")]
    return raw_name.rsplit("_", 1)[-1] if "_" in raw_name else raw_name


def champion_slug(value: str | None) -> str:
    if not value:
        return ""
    special = {
        "MonkeyKing": "wukong",
        "FiddleSticks": "fiddlesticks",
        "Renata": "renataglasc",
    }
    cleaned = "".join(ch for ch in str(value) if ch.isalnum())
    return special.get(cleaned, cleaned).lower()


def _riot_id(value: dict[str, Any]) -> str:
    riot_id = value.get("riotId") or value.get("summonerName") or ""
    if riot_id:
        return str(riot_id)
    game_name = value.get("riotIdGameName")
    tag = value.get("riotIdTagLine")
    if game_name and tag:
        return f"{game_name}#{tag}"
    return str(game_name or "")


def _players_from_snapshot(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(snapshot.get("playerlist"), list):
        return snapshot["playerlist"]
    all_game_data = snapshot.get("allgamedata") or {}
    if isinstance(all_game_data.get("allPlayers"), list):
        return all_game_data["allPlayers"]
    return []


def _active_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    if isinstance(snapshot.get("activeplayer"), dict):
        return snapshot["activeplayer"]
    all_game_data = snapshot.get("allgamedata") or {}
    return all_game_data.get("activePlayer") or {}


def _game_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    if isinstance(snapshot.get("gamestats"), dict):
        return snapshot["gamestats"]
    all_game_data = snapshot.get("allgamedata") or {}
    return all_game_data.get("gameData") or {}


def _to_live_player(player: dict[str, Any]) -> LivePlayer:
    return LivePlayer(
        riot_id=_riot_id(player),
        champion_name=str(player.get("championName") or ""),
        champion_id=champion_id_from_raw(player.get("rawChampionName")),
        team=str(player.get("team") or ""),
        position=player.get("position"),
        is_bot=bool(player.get("isBot", False)),
        level=int(player["level"]) if player.get("level") is not None else None,
        is_active=bool(player.get("isActivePlayer", False)),
    )


def _active_raw_player(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    raw_players = _players_from_snapshot(snapshot)
    marked = next(
        (player for player in raw_players if isinstance(player, dict) and player.get("isActivePlayer")),
        None,
    )
    if marked is not None:
        return marked
    active = _active_from_snapshot(snapshot)
    active_name = str(
        active.get("riotId")
        or active.get("summonerName")
        or snapshot.get("activeplayername")
        or ""
    )
    active_key = active_name.split("#", 1)[0].lower()
    if active_key:
        matched = next(
            (
                player
                for player in raw_players
                if _riot_id(player).split("#", 1)[0].lower() == active_key
            ),
            None,
        )
        if matched is not None:
            return matched
    return next((player for player in raw_players if not bool(player.get("isBot"))), None)


def build_match_key(snapshot: dict[str, Any], *, captured_at: datetime | None = None) -> str:
    players = [_to_live_player(player) for player in _players_from_snapshot(snapshot)]
    active = _active_raw_player(snapshot)
    game = _game_from_snapshot(snapshot)
    game_time = float(game.get("gameTime") or 0.0)
    observed_at = captured_at or datetime.now(timezone.utc).astimezone()
    estimated_start = observed_at - timedelta(seconds=max(game_time, 0.0))
    start_minute = int(round(estimated_start.timestamp() / 60.0))
    roster = sorted(f"{player.team}:{player.champion_slug}" for player in players)
    active_slug = champion_slug(
        champion_id_from_raw((active or {}).get("rawChampionName"))
        or (active or {}).get("championName")
    )
    material = "|".join(
        [
            str(game.get("gameMode") or ""),
            str(game.get("mapNumber") or game.get("mapName") or ""),
            str(start_minute),
            active_slug,
            *roster,
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]


def build_snapshot_match_key(snapshot: dict[str, Any]) -> str:
    """Build a stable key for a saved snapshot without retaining game time."""

    captured_at: datetime | None = None
    raw_captured_at = str((snapshot.get("snapshot_meta") or {}).get("captured_at") or "")
    if raw_captured_at:
        try:
            captured_at = datetime.fromisoformat(raw_captured_at.replace("Z", "+00:00"))
        except ValueError:
            captured_at = None
    return build_match_key(snapshot, captured_at=captured_at)


def build_match_context(snapshot: dict[str, Any], *, source_path: str | None = None) -> dict[str, Any]:
    raw_players = _players_from_snapshot(snapshot)
    players = [_to_live_player(p) for p in raw_players]
    active = _active_from_snapshot(snapshot)
    active_name = snapshot.get("activeplayername")
    active_riot_id = str(active.get("riotId") or active.get("summonerName") or active_name or "")

    active_player = next((p for p in players if p.is_active), None)
    if active_player is None:
        active_player = next((p for p in players if p.riot_id == active_riot_id), None)
    if active_player is None and active_riot_id:
        active_key = active_riot_id.split("#", 1)[0].lower()
        active_player = next((p for p in players if p.riot_id.split("#", 1)[0].lower() == active_key), None)
    if active_player is None and players:
        active_player = next((p for p in players if not p.is_bot), players[0])

    my_team = active_player.team if active_player else None
    allies = [p for p in players if p.team == my_team]
    enemies = [p for p in players if p.team != my_team]

    teams: dict[str, list[dict[str, Any]]] = {}
    for p in players:
        payload = p.to_dict()
        payload["is_active"] = p is active_player
        teams.setdefault(p.team, []).append(payload)

    ally_payloads = []
    for player in allies:
        payload = player.to_dict()
        payload["is_active"] = player is active_player
        ally_payloads.append(payload)

    return {
        "source": {
            "kind": "riot_live_client",
            "path": source_path,
            "captured_at": (snapshot.get("snapshot_meta") or {}).get("captured_at"),
        },
        "game": _game_from_snapshot(snapshot),
        "active_player": active_player.to_dict() if active_player else None,
        "teams": teams,
        "allies": ally_payloads,
        "enemies": [p.to_dict() for p in enemies],
    }


def load_match_context(path: str | Path) -> dict[str, Any]:
    return build_match_context(load_snapshot(path), source_path=str(path))

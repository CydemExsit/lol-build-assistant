from __future__ import annotations

import json
import ssl
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://127.0.0.1:2999/liveclientdata"
ENDPOINTS = {
    "playerlist": "/playerlist",
    "activeplayer": "/activeplayer",
    "activeplayername": "/activeplayername",
    "gamestats": "/gamestats",
    "allgamedata": "/allgamedata",
}


@dataclass(frozen=True)
class LivePlayer:
    riot_id: str
    champion_name: str
    champion_id: str | None
    team: str
    position: str | None
    is_bot: bool
    level: int | None

    @property
    def champion_slug(self) -> str:
        return champion_slug(self.champion_id or self.champion_name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "riot_id": self.riot_id,
            "champion_name": self.champion_name,
            "champion_id": self.champion_id,
            "champion_slug": self.champion_slug,
            "team": self.team,
            "position": self.position,
            "is_bot": self.is_bot,
            "level": self.level,
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

    selected = endpoints or ENDPOINTS
    ssl_context = ssl._create_unverified_context()
    data: dict[str, Any] = {}
    for name, path in selected.items():
        url = base_url.rstrip("/") + path
        with urllib.request.urlopen(url, timeout=timeout, context=ssl_context) as response:
            data[name] = _json_loads(response.read())
    return data


def save_snapshot(data: dict[str, Any], out_dir: str | Path | None = None) -> Path:
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")
    target = Path(out_dir) if out_dir else Path("data/raw") / f"live_{stamp}"
    target.mkdir(parents=True, exist_ok=True)
    for name, payload in data.items():
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
    if marker in raw_name:
        return raw_name.split(marker, 1)[1]
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
    )


def build_match_context(snapshot: dict[str, Any], *, source_path: str | None = None) -> dict[str, Any]:
    raw_players = _players_from_snapshot(snapshot)
    players = [_to_live_player(p) for p in raw_players]
    active = _active_from_snapshot(snapshot)
    active_name = snapshot.get("activeplayername")
    active_riot_id = str(active.get("riotId") or active.get("summonerName") or active_name or "")

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
        teams.setdefault(p.team, []).append(p.to_dict())

    return {
        "source": {
            "kind": "riot_live_client",
            "path": source_path,
            "captured_at": (snapshot.get("snapshot_meta") or {}).get("captured_at"),
        },
        "game": _game_from_snapshot(snapshot),
        "active_player": active_player.to_dict() if active_player else None,
        "teams": teams,
        "allies": [p.to_dict() for p in allies],
        "enemies": [p.to_dict() for p in enemies],
    }


def load_match_context(path: str | Path) -> dict[str, Any]:
    return build_match_context(load_snapshot(path), source_path=str(path))

from copy import deepcopy
from pathlib import Path

from src.watcher import MatchWatcher


class FakeService:
    def __init__(self, status_path: Path):
        self.status_path = status_path
        self.calls = []

    def capture_and_recommend(self, raw_data, *, match_key, reuse_existing):
        self.calls.append((raw_data, match_key, reuse_existing))
        return Path("snapshot"), {"session": {"match_key": match_key}}


class FlakyService(FakeService):
    def capture_and_recommend(self, raw_data, *, match_key, reuse_existing):
        self.calls.append((raw_data, match_key, reuse_existing))
        if len(self.calls) == 1:
            raise RuntimeError("temporary failure")
        return Path("snapshot"), {"session": {"match_key": match_key}}


def _observation():
    order = ["Ashe", "Garen", "Lux", "Nami", "XinZhao"]
    chaos = ["Brand", "Jax", "Zyra", "Corki", "Kindred"]
    players = []
    for index, champion in enumerate(order):
        players.append(
            {
                "riotId": "Self#TW2" if index == 0 else f"Ally{index}#TW2",
                "championName": champion,
                "rawChampionName": f"game_character_displayname_{champion}",
                "team": "ORDER",
            }
        )
    for index, champion in enumerate(chaos):
        players.append(
            {
                "riotId": f"Enemy{index}#TW2",
                "championName": champion,
                "rawChampionName": f"game_character_displayname_{champion}",
                "team": "CHAOS",
            }
        )
    return {
        "activeplayer": {"riotId": "Self#TW2"},
        "gamestats": {"gameMode": "ARAM", "mapNumber": 12, "gameTime": 15},
        "playerlist": players,
    }


def test_watcher_processes_a_match_once_without_opening_browser_by_default(tmp_path):
    service = FakeService(tmp_path / "status.json")
    opened = []
    watcher = MatchWatcher(service, browser_open=opened.append)

    assert watcher.process_observation(_observation()) is True
    assert watcher.process_observation(_observation()) is False
    assert len(service.calls) == 1
    assert opened == []


def test_watcher_ignores_loading_mutations_inside_the_locked_session(tmp_path):
    service = FakeService(tmp_path / "status.json")
    watcher = MatchWatcher(service)
    changed = deepcopy(_observation())
    changed["gamestats"]["gameTime"] = 87
    changed["playerlist"][-1]["championName"] = "Varus"
    changed["playerlist"][-1]["rawChampionName"] = "game_character_displayname_Varus"

    assert watcher.process_observation(_observation()) is True
    assert watcher.process_observation(changed) is False
    assert len(service.calls) == 1


def test_watcher_releases_session_after_sustained_disconnect(tmp_path):
    service = FakeService(tmp_path / "status.json")
    watcher = MatchWatcher(service, disconnect_threshold=2)
    next_match = deepcopy(_observation())
    next_match["playerlist"][-1]["championName"] = "Varus"
    next_match["playerlist"][-1]["rawChampionName"] = "game_character_displayname_Varus"

    assert watcher.process_observation(_observation()) is True
    assert watcher.note_api_unavailable() is False
    assert watcher.note_api_unavailable() is True
    watcher.note_api_available()
    assert watcher.process_observation(next_match) is True
    assert len(service.calls) == 2


def test_watcher_retries_failed_match_without_opening_another_tab(tmp_path):
    service = FlakyService(tmp_path / "status.json")
    opened = []
    watcher = MatchWatcher(service, auto_open=True, browser_open=opened.append)

    assert watcher.process_observation(_observation()) is True
    watcher._retry_after = 0
    assert watcher.process_observation(_observation()) is True
    assert len(service.calls) == 2
    assert opened == ["http://127.0.0.1:8765"]

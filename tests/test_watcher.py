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
    return {
        "activeplayer": {"riotId": "Self#TW2"},
        "gamestats": {"gameMode": "ARAM", "mapNumber": 12, "gameTime": 15},
        "playerlist": [
            {
                "riotId": "Self#TW2",
                "championName": "Ashe",
                "rawChampionName": "game_character_displayname_Ashe",
                "team": "ORDER",
            },
            {
                "riotId": "Enemy#TW2",
                "championName": "Brand",
                "rawChampionName": "game_character_displayname_Brand",
                "team": "CHAOS",
            },
        ],
    }


def test_watcher_processes_a_match_once_and_opens_browser_once(tmp_path):
    service = FakeService(tmp_path / "status.json")
    opened = []
    watcher = MatchWatcher(service, browser_open=opened.append)

    assert watcher.process_observation(_observation()) is True
    assert watcher.process_observation(_observation()) is False
    assert len(service.calls) == 1
    assert opened == ["http://127.0.0.1:8765"]


def test_watcher_retries_failed_match_without_opening_another_tab(tmp_path):
    service = FlakyService(tmp_path / "status.json")
    opened = []
    watcher = MatchWatcher(service, browser_open=opened.append)

    assert watcher.process_observation(_observation()) is True
    watcher._retry_after = 0
    assert watcher.process_observation(_observation()) is True
    assert len(service.calls) == 2
    assert opened == ["http://127.0.0.1:8765"]

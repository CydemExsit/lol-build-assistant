import json

from src.compliance import freeze_static_recommendation
from src.history import record_recommendation
from src.live_client import build_snapshot_match_key, load_snapshot
from src.service import RecommendationService


def test_service_reuses_frozen_result_for_same_snapshot_by_default(tmp_path, monkeypatch):
    snapshot_dir = tmp_path / "live_snapshot"
    snapshot_dir.mkdir()
    (snapshot_dir / "playerlist.json").write_text(
        json.dumps(
            [
                {
                    "championName": "Ashe",
                    "rawChampionName": "game_character_displayname_Ashe",
                    "team": "ORDER",
                    "isActivePlayer": True,
                }
            ]
        ),
        encoding="utf-8",
    )
    (snapshot_dir / "gamestats.json").write_text(
        json.dumps({"gameMode": "ARAM", "mapNumber": 12}),
        encoding="utf-8",
    )
    (snapshot_dir / "snapshot_meta.json").write_text(
        json.dumps({"captured_at": "2026-07-18T10:00:00+08:00"}),
        encoding="utf-8",
    )
    match_key = build_snapshot_match_key(load_snapshot(snapshot_dir))
    frozen = freeze_static_recommendation(
        {
            "active_player": {"champion_id": "Ashe", "champion_slug": "ashe"},
            "build": {
                "routes": [
                    {
                        "label": "AD",
                        "items": [{"item_id": value} for value in (3032, 6675, 3031, 3036, 3072)],
                    }
                ]
            },
        },
        match_key=match_key,
    )
    history_path = tmp_path / "history.db"
    record_recommendation(frozen, history_path)
    service = RecommendationService(
        out_path=tmp_path / "current.json",
        out_markdown_path=tmp_path / "current.md",
        history_path=history_path,
        status_path=tmp_path / "status.json",
    )

    def fail_if_regenerated(*args, **kwargs):
        raise AssertionError("same match should reuse its frozen result")

    monkeypatch.setattr("src.service.recommend_from_snapshot", fail_if_regenerated)
    reused = service.recommend_snapshot(snapshot_dir)

    assert reused["session"]["revision"] == frozen["session"]["revision"]
    assert json.loads(service.out_path.read_text(encoding="utf-8"))["session"]["frozen"] is True

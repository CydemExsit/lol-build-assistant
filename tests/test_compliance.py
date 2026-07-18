from src.compliance import LEGAL_NOTICE, freeze_static_recommendation, validate_static_recommendation
from src.evaluation import audit_recommendation


def _result():
    item_ids = [3032, 6675, 3031, 3036, 3072]
    return {
        "active_player": {
            "champion_id": "Tristana",
            "champion_slug": "tristana",
            "team": "CHAOS",
            "riot_id": "private#id",
        },
        "game": {"gameMode": "ARAM", "gameTime": 42.0},
        "build": {
            "boot_options": [{"item_id": 3006}],
            "routes": [
                {
                    "label": "暴擊 AD",
                    "items": [{"item_id": item_id} for item_id in item_ids],
                    "set_stats": {"games": 120, "win_rate": 0.54, "pick_rate": 0.01},
                    "confidence": {"level": "high", "label": "較高可信"},
                }
            ],
            "source": {
                "champions_analysed": 2_000_000,
                "data_health": {"level": "healthy"},
            },
        },
    }


def test_freeze_strips_identity_and_dynamic_game_fields():
    frozen = freeze_static_recommendation(_result(), match_key="match-1")

    assert "riot_id" not in frozen["active_player"]
    assert "gameTime" not in frozen["game"]
    assert frozen["session"]["frozen"] is True
    assert frozen["session"]["updates_during_match"] is False
    assert frozen["compliance"]["legal_notice"] == LEGAL_NOTICE
    validate_static_recommendation(frozen)


def test_audit_accepts_static_five_item_route_and_flags_single_choice_only_as_warning():
    report = audit_recommendation(freeze_static_recommendation(_result(), match_key="match-1"))

    assert report["passed"] is True
    assert report["errors"] == []
    assert "only one static route is available" in report["warnings"]

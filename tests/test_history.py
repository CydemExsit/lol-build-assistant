from src.compliance import freeze_static_recommendation
from src.history import (
    learned_item_adjustments,
    list_history,
    record_outcome,
    record_recommendation,
    record_route_feedback,
    route_key,
)


def _recommendation():
    route = {
        "label": "暴擊 AD",
        "items": [{"item_id": item_id} for item_id in (3032, 6675, 3031, 3036, 3072)],
        "set_stats": {"games": 80},
    }
    result = {
        "active_player": {"champion_id": "Tristana", "champion_slug": "tristana"},
        "ally_team": [{"champion": "Tristana", "slug": "tristana"}],
        "enemy_team": [{"champion": "Ashe", "slug": "ashe"}],
        "build": {"routes": [route]},
    }
    return freeze_static_recommendation(result, match_key="history-match"), route


def test_history_records_feedback_outcome_and_learns_item_adjustments(tmp_path):
    database = tmp_path / "assistant.db"
    result, route = _recommendation()
    record_recommendation(result, database)
    record_route_feedback("history-match", route_key(route), 1, database)
    record_outcome("history-match", 1, database)

    adjustments, event_count = learned_item_adjustments(database)
    history = list_history(database)

    assert event_count == 1
    assert adjustments[3072] > 0
    assert history[0]["outcome"] == 1
    assert history[0]["feedback"][0]["sentiment"] == 1

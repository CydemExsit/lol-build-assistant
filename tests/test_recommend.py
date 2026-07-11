from src.recommend import (
    MIN_ROUTE_CANDIDATE_PICK_RATE,
    ThreatProfile,
    _extreme_damage_type,
    _is_full_ap_marksman_route,
    _is_pure_defense_item,
    _route_candidate_sets,
    _route_reasons,
    _route_starting_reminders,
    _score_route,
    analyze_threats,
    load_user_preferences,
)


def test_route_candidate_floor_uses_pick_rate_instead_of_game_count():
    included = {"pick_rate": 0.0003, "games": 2}
    excluded = {"pick_rate": 0.00029, "games": 200}

    assert MIN_ROUTE_CANDIDATE_PICK_RATE == 0.0003
    assert _route_candidate_sets([excluded, included]) == [included]


def test_route_reasons_do_not_repeat_set_statistics():
    reasons = _route_reasons(
        {
            "win_rate": 0.5405,
            "pick_rate": 0.0156,
            "games": 185,
            "source_params": {"patch": "7"},
        },
        "crit",
        [{"item_id": 3031, "tags": ["CriticalStrike"]}],
        ThreatProfile(
            magic_count=0,
            physical_count=0,
            tank_count=0,
            cc_count=0,
            shield_count=0,
            healing_count=0,
        ),
    )

    assert reasons == ["偏暴擊 AD，適合穩定普攻爆發"]


def test_personal_item_scores_prefer_bork_over_zhonya():
    preferences = load_user_preferences()
    threats = ThreatProfile(0, 0, 0, 0, 0, 0)
    row = {"win_rate": 0.5, "pick_rate": 0.001, "games": 100}
    neutral_items = [
        {"item_id": item_id, "tags": ["Damage"]}
        for item_id in (3031, 3036, 3085, 3094)
    ]
    liked_items = neutral_items + [{"item_id": 3153, "tags": ["Damage", "AttackSpeed", "OnHit"]}]
    disliked_items = neutral_items + [{"item_id": 3157, "tags": ["Armor", "SpellDamage"]}]
    scored_by_id = {int(item["item_id"]): {"score": 0.0} for item in liked_items + disliked_items}

    liked_score = _score_route(row, liked_items, scored_by_id, threats, "crit", "ashe", preferences)
    disliked_score = _score_route(row, disliked_items, scored_by_id, threats, "crit", "ashe", preferences)

    assert liked_score > disliked_score


def test_extreme_damage_enables_matching_pure_tank_items():
    preferences = load_user_preferences()
    magic_threats = ThreatProfile(4, 1, 0, 0, 0, 0)
    physical_threats = ThreatProfile(1, 4, 0, 0, 0, 0)
    kaenic = {"item_id": 2504, "tags": ["Health", "SpellBlock", "HealthRegen"]}
    randuin = {"item_id": 3143, "tags": ["Health", "Armor", "Slow"]}
    maw = {"item_id": 3156, "tags": ["SpellBlock", "Damage"]}

    assert _extreme_damage_type(magic_threats, preferences) == "magic"
    assert _extreme_damage_type(physical_threats, preferences) == "physical"
    assert _is_pure_defense_item(kaenic, "magic")
    assert not _is_pure_defense_item(kaenic, "physical")
    assert _is_pure_defense_item(randuin, "physical")
    assert not _is_pure_defense_item(maw, "magic")


def test_magic_heavy_comp_counts_ap_tanks_and_hybrids():
    context = {
        "enemies": [
            {"champion_slug": champion}
            for champion in ("brand", "maokai", "kayle", "rumble", "blitzcrank")
        ]
    }

    threats = analyze_threats(context)

    assert threats.magic_count == 5
    assert _extreme_damage_type(threats, load_user_preferences()) == "magic"


def test_marksman_full_ap_penalty_does_not_hit_mixed_damage():
    preferences = load_user_preferences()
    pure_ap = [
        {"item_id": 1, "tags": ["SpellDamage"]},
        {"item_id": 2, "tags": ["SpellDamage"]},
        {"item_id": 3, "tags": ["SpellDamage"]},
        {"item_id": 4, "tags": ["SpellDamage"]},
        {"item_id": 5, "tags": ["Damage"]},
    ]
    mixed = [{**pure_ap[0], "tags": ["SpellDamage", "AttackSpeed", "OnHit"]}, *pure_ap[1:]]

    assert _is_full_ap_marksman_route(pure_ap, "kaisa", preferences)
    assert not _is_full_ap_marksman_route(mixed, "kaisa", preferences)
    assert not _is_full_ap_marksman_route(pure_ap, "veigar", preferences)


def test_tear_upgrade_adds_starting_reminder():
    assert _route_starting_reminders([{"item_id": 3004}], {}) == ["開場先買女神之淚"]

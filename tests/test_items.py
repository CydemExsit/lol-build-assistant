from src.items import is_completed_non_boot_item


def test_is_completed_non_boot_item_filters_components_boots_and_starters():
    assert is_completed_non_boot_item(
        {"item_id": 3153, "tags": ["Damage", "AttackSpeed", "OnHit"], "into": [], "gold_total": 3200, "gold_purchasable": True}
    )
    assert not is_completed_non_boot_item(
        {"item_id": 3070, "tags": ["Mana", "ManaRegen"], "into": ["3004"], "gold_total": 400, "gold_purchasable": True}
    )
    assert not is_completed_non_boot_item(
        {"item_id": 3006, "tags": ["AttackSpeed", "Boots"], "into": [], "gold_total": 1100, "gold_purchasable": True}
    )
    assert not is_completed_non_boot_item(
        {"item_id": 1055, "tags": ["Damage", "Lane"], "into": [], "gold_total": 450, "gold_purchasable": True}
    )

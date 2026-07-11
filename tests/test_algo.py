from pathlib import Path

from src.algo import load_built_sets, load_winning_items


def test_loaders_normalize_percent_rates_and_skip_empty_names(tmp_path: Path):
    winning = tmp_path / "winning.csv"
    winning.write_text(
        "name,win_rate,pick_rate,sample_size\n"
        "Blade,55.5,12.0,100\n"
        ",60.0,1.0,5\n",
        encoding="utf-8",
    )
    sets = tmp_path / "sets.csv"
    sets.write_text(
        "items,set_win_rate,set_pick_rate,set_sample_size\n"
        "Blade|Boots,59.21,0.88,76\n",
        encoding="utf-8",
    )

    winning_items = load_winning_items(str(winning))
    built_sets = load_built_sets(str(sets))

    assert len(winning_items) == 1
    assert winning_items[0].win_rate == 0.555
    assert winning_items[0].pick_rate == 0.12
    assert built_sets[0].set_win_rate == 0.5921
    assert built_sets[0].set_pick_rate == 0.88

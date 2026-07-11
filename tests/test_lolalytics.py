import pytest

import src.lolalytics as lolalytics
from src.lolalytics import (
    _normalize_item_sets_api_payload,
    _scroll_collect_sets_script,
    _normalize_playwright_boot_rows,
    _normalize_playwright_item_rows,
    _normalize_playwright_sets,
    item_sets_api_url,
    lolalytics_url,
    parse_build_html,
)


def test_sets_scraper_targets_lazy_build_sets_section():
    script = _scroll_collect_sets_script()

    assert "Sets With Boots" in script
    assert "section.scrollIntoView" in script
    assert "section?.querySelector('.overflow-x-scroll')" in script


def test_item_sets_api_url_matches_aram_filters():
    assert item_sets_api_url("ashe") == (
        "https://a1.lolalytics.com/mega/?ep=build-itemset&v=1&patch=7&c=ashe&lane=all"
        "&tier=gold_plus&queue=aram&region=all"
    )


def test_normalize_item_sets_api_payload_restores_set_stats():
    payload = {
        "itemSets": {
            "itemSet1": [["3032", 100, 50]],
            "itemSet2": [["3032_3085", 50, 25]],
            "itemSet3": [],
            "itemSet4": [],
            "itemSet5": [["3032_3085_3031_3036_3153", 50, 30]],
        }
    }

    sets = _normalize_item_sets_api_payload(payload)

    assert sets == [
        {
            "item_ids": [3032, 3085, 3031, 3036, 3153],
            "item_names": ["3032", "3085", "3031", "3036", "3153"],
            "win_rate": 0.6,
            "pick_rate": 0.25,
            "games": 50,
            "data_source": "build_itemset_api",
        }
    ]


def test_fetch_actual_sets_prefers_api_payload(monkeypatch, tmp_path):
    payload = {
        "itemSets": {
            "itemSet1": [["3032", 100, 50]],
            "itemSet2": [],
            "itemSet3": [],
            "itemSet4": [],
            "itemSet5": [["3032_3085_3031_3036_3153", 25, 15]],
        },
        "response": {"valid": True},
    }
    monkeypatch.setattr(lolalytics, "_fetch_item_sets_api_payload", lambda *args, **kwargs: payload)

    sets = lolalytics.fetch_actual_built_sets_5("ashe", cache_dir=tmp_path, refresh=True)

    assert len(sets) == 1
    assert sets[0]["games"] == 25
    assert sets[0]["pick_rate"] == 0.2
    assert sets[0]["data_source"] == "build_itemset_api"


def test_lolalytics_url_defaults_to_aram_all_ranks_recent_window():
    assert lolalytics_url("vayne") == "https://lolalytics.com/lol/vayne/aram/build/?tier=gold_plus&patch=7"


def test_parse_build_html_extracts_core_and_branch_items():
    markup = """
    <title>Vayne Build</title>
    <div>Patch</div><!--t=p-->16.13<!---->
    All Ranks Champions Analysed: <!--t=a-->1,234,567<!---->
    <div>Core Build</div>
    <img src="https://cdn5.lolalytics.com/item64/3153.webp" alt="Blade of The Ruined King">
    <img src="https://cdn5.lolalytics.com/item64/3006.webp" alt="Berserker&#39;s Greaves">
    <!--t=w-->53.52<!---->%</span><br><span>18,379</span>
    <div>Item 4</div>
    <img src="https://cdn5.lolalytics.com/item64/3031.webp" alt="Infinity Edge">
    <!--t=w2-->58.3<!---->%</span><br><span>20,104</span>
    <div>Item 5</div>
    <img src="https://cdn5.lolalytics.com/item64/3036.webp" alt="Lord Dominik&#39;s Regards">
    <div>Item 6</div>
    <img src="https://cdn5.lolalytics.com/item64/3139.webp" alt="Mercurial Scimitar">
    <div>LEGEND:</div>
    <img src="https://cdn5.lolalytics.com/item64/3091.webp" alt="Wit&#39;s End" data-id="3091">
    """

    parsed = parse_build_html(markup)

    assert parsed["patch"] == "16.13"
    assert parsed["champions_analysed"] == 1234567
    assert [item["item_id"] for item in parsed["sections"]["Core Build"]] == [3153, 3006]
    assert parsed["sections"]["Core Build"][1]["name"] == "Berserker's Greaves"
    assert parsed["sections"]["Core Build"][1]["win_rate"] == 0.5352
    assert parsed["sections"]["Item 4"][0]["games"] == 20104
    assert parsed["candidate_items"] == [{"item_id": 3091, "name": "Wit's End"}]


def test_normalize_playwright_sets_parses_stats_and_rejects_duplicate_items():
    rows = [
        {
            "item_ids": [3070, 3134, 3070, 6694, 3814],
            "item_names": ["Tear", "Dirk", "Tear", "Serylda", "Edge"],
            "stats": ["48.56", "51.98", "43,287"],
        },
        {
            "item_ids": [3153, 3124, 3091, 3302, 6665],
            "item_names": ["Blade", "Guinsoo", "Wit's End", "Terminus", "Jak'Sho"],
            "stats": ["54.30", "0.79", "512"],
        },
    ]

    sets = _normalize_playwright_sets(rows)

    assert len(sets) == 1
    assert sets[0]["item_ids"] == [3153, 3124, 3091, 3302, 6665]
    assert sets[0]["win_rate"] == pytest.approx(0.543)
    assert sets[0]["pick_rate"] == pytest.approx(0.0079)
    assert sets[0]["games"] == 512


def test_normalize_playwright_boot_rows_parses_boots_table_stats():
    rows = [
        {
            "item_id": 3008,
            "item_name": "Gluttonous Greaves",
            "stats": ["56.21", "4.72", "459"],
            "time": "8",
        }
    ]

    boots = _normalize_playwright_boot_rows(rows)

    assert boots == [
        {
            "item_id": 3008,
            "item_name": "Gluttonous Greaves",
            "win_rate": pytest.approx(0.5621),
            "pick_rate": pytest.approx(0.0472),
            "games": 459,
            "source": "Boots",
            "time": 8,
        }
    ]


def test_normalize_playwright_item_rows_parses_item_stats():
    rows = [
        {
            "item_id": 3156,
            "item_name": "Maw of Malmortius",
            "stats": ["51.94", "1.27", "150"],
            "time": "19",
        }
    ]

    items = _normalize_playwright_item_rows(rows, source="Winning Items")

    assert items[0]["item_id"] == 3156
    assert items[0]["win_rate"] == pytest.approx(0.5194)
    assert items[0]["pick_rate"] == pytest.approx(0.0127)
    assert items[0]["games"] == 150
    assert items[0]["source"] == "Winning Items"

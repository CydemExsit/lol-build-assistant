import json
import os
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src import lolalytics
from src.compliance import validate_static_recommendation
from src.evaluation import audit_recommendation
from src.main import parse_args
from src.service import RecommendationService
from src.watcher import MatchWatcher


def _write(path, payload, *, age_hours=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    timestamp = time.time() - age_hours * 3600
    os.utime(path, (timestamp, timestamp))


def _stat(item_id=3006):
    return {"item_id": item_id, "win_rate": 0.55, "pick_rate": 0.1, "games": 1000}


@pytest.fixture
def browser(monkeypatch):
    calls = []
    fail_tables = set()
    startup_failure = []

    class Page:
        def goto(self, *args, **kwargs):
            calls.append("goto")
            if startup_failure:
                raise OSError("offline")

        def wait_for_load_state(self, *args, **kwargs):
            pass

        def evaluate(self, script, argument):
            label = argument["label"]
            calls.append(label)
            if label in fail_tables:
                raise RuntimeError("table unavailable")
            return [{"item_id": 3006, "item_name": "Boots", "stats": ["55", "10", "1000"]}]

    class Browser:
        def new_page(self, **kwargs):
            return Page()

        def close(self):
            calls.append("close")

    class Playwright:
        def __enter__(self):
            return SimpleNamespace(chromium=self)

        def __exit__(self, *args):
            pass

        def launch(self, **kwargs):
            calls.append("launch")
            return Browser()

    monkeypatch.setattr("playwright.sync_api.sync_playwright", Playwright)
    return SimpleNamespace(calls=calls, fail_tables=fail_tables, startup_failure=startup_failure)


def test_three_missing_tables_share_one_page_and_next_request_stays_offline(tmp_path, browser):
    first = lolalytics.fetch_stat_tables("ashe", cache_dir=tmp_path)
    second = lolalytics.fetch_stat_tables("ashe", cache_dir=tmp_path)

    assert all(first.values())
    assert first == second
    assert browser.calls == ["launch", "goto", "Boots", "Popular Items", "Winning Items", "close"]


def test_only_expired_table_is_refetched(tmp_path, browser):
    boots = [_stat()]
    _write(lolalytics.boot_stats_cache_path_for("ashe", tmp_path), boots)
    _write(lolalytics.item_stats_cache_path_for("ashe", tmp_path, table="Popular Items"), [_stat(3031)], age_hours=7)
    _write(lolalytics.item_stats_cache_path_for("ashe", tmp_path, table="Winning Items"), [_stat(3153)])

    result = lolalytics.fetch_stat_tables("ashe", cache_dir=tmp_path)

    assert result["Boots"] == boots
    assert result["Winning Items"] == [_stat(3153)]
    assert browser.calls == ["launch", "goto", "Popular Items", "close"]


@pytest.mark.parametrize("payload", [
    "broken json", "{}", "[]", '[{"item_id":3006}]',
    json.dumps([{**_stat(), "item_id": "invalid"}]),
    json.dumps([{**_stat(), "win_rate": float("nan")}]),
    json.dumps([{**_stat(), "pick_rate": 5.0}]),
])
def test_corrupt_or_empty_table_is_rebuilt(tmp_path, browser, payload):
    target = lolalytics.boot_stats_cache_path_for("ashe", tmp_path)
    target.write_text(payload, encoding="utf-8")

    rows = lolalytics.fetch_boot_stats("ashe", cache_dir=tmp_path)

    assert rows[0]["games"] == 1000
    assert json.loads(target.read_text(encoding="utf-8")) == rows


def test_force_refresh_bypasses_fresh_tables(tmp_path, browser):
    _write(lolalytics.boot_stats_cache_path_for("ashe", tmp_path), [_stat()])

    lolalytics.fetch_boot_stats("ashe", cache_dir=tmp_path, refresh=True)

    assert "Boots" in browser.calls


def test_one_table_failure_does_not_discard_other_tables(tmp_path, browser):
    browser.fail_tables.add("Popular Items")

    result = lolalytics.fetch_stat_tables("ashe", cache_dir=tmp_path)

    assert result["Boots"]
    assert result["Popular Items"] == []
    assert result["Winning Items"]
    assert browser.calls[-1] == "close"
    assert not lolalytics.item_stats_cache_path_for("ashe", tmp_path, table="Popular Items").exists()


def test_offline_browser_preserves_fresh_hits_and_closes(tmp_path, browser):
    _write(lolalytics.boot_stats_cache_path_for("ashe", tmp_path), [_stat()])
    browser.startup_failure.append(True)

    result = lolalytics.fetch_stat_tables("ashe", cache_dir=tmp_path)

    assert result["Boots"] == [_stat()]
    assert result["Popular Items"] == result["Winning Items"] == []
    assert browser.calls == ["launch", "goto", "close"]


def test_fresh_actual_set_cache_avoids_network(tmp_path, monkeypatch):
    rows = [{"item_ids": [3031, 3036, 3085, 3094, 3153], "win_rate": 0.6,
             "pick_rate": 0.01, "games": 1000, "data_source": "build_itemset_api"}]
    _write(lolalytics.built_sets_cache_path_for("ashe", tmp_path), rows)
    monkeypatch.setattr(lolalytics, "_fetch_item_sets_api_payload", lambda *a, **k: pytest.fail("fresh sets should stay offline"))

    assert lolalytics.fetch_actual_built_sets_5("ashe", cache_dir=tmp_path) == rows


@pytest.mark.parametrize("source,age_hours", [("build_itemset_api", 7), ("page_scroll", 0)])
def test_expired_or_legacy_set_cache_is_refreshed(tmp_path, monkeypatch, source, age_hours):
    _write(lolalytics.built_sets_cache_path_for("ashe", tmp_path), [
        {"item_ids": [3031, 3036, 3085, 3094, 3153], "win_rate": 0.6,
         "pick_rate": 0.01, "games": 1000, "data_source": source}
    ], age_hours=age_hours)
    monkeypatch.setattr(lolalytics, "_fetch_item_sets_api_payload", lambda *a, **k: {
        "itemSets": {"itemSet5": [["3031_3036_3085_3094_3153", 2000, 1200]]}
    })

    assert lolalytics.fetch_actual_built_sets_5("ashe", cache_dir=tmp_path)[0]["games"] == 2000


@pytest.mark.parametrize("age_hours,expected_refresh", [(1, False), (7, True)])
def test_build_summary_uses_fetch_timestamp_and_honors_ttl(tmp_path, monkeypatch, age_hours, expected_refresh):
    _write(lolalytics.build_summary_cache_path_for("ashe", tmp_path), {
        "sections": {}, "params": {"mode": "aram", "tier": "gold_plus", "patch": "7"},
        "fetched_at": (datetime.now(timezone.utc) - timedelta(hours=age_hours)).isoformat(),
    })
    fetches = []

    def fetch(*args, **kwargs):
        fetches.append(kwargs["refresh"])
        path = lolalytics.cache_path_for("ashe", tmp_path)
        path.write_text("<title>Refreshed</title>", encoding="utf-8")
        _write(path.with_suffix(".meta.json"), {"fetched_at": datetime.now(timezone.utc).isoformat()})
        return path

    monkeypatch.setattr(lolalytics, "fetch_build_html", fetch)
    lolalytics.load_or_fetch_build("ashe", cache_dir=tmp_path)

    assert fetches == ([True] if expected_refresh else [])


def test_custom_cache_lifetime_is_honored(tmp_path, browser):
    _write(lolalytics.boot_stats_cache_path_for("ashe", tmp_path), [_stat()], age_hours=7)

    assert lolalytics.fetch_boot_stats("ashe", cache_dir=tmp_path, max_age_hours=12) == [_stat()]
    assert browser.calls == []
    assert parse_args(["watch"]).cache_max_age_hours == 6


def test_malformed_set_ids_do_not_break_recommendations(tmp_path, monkeypatch):
    _write(lolalytics.built_sets_cache_path_for("ashe", tmp_path), [{
        "item_ids": "not-an-item-list", "win_rate": 0.6, "pick_rate": 0.01,
        "games": 1000, "data_source": "build_itemset_api",
    }])
    monkeypatch.setattr(lolalytics, "_fetch_item_sets_api_payload", lambda *a, **k: {
        "itemSets": {"itemSet5": [["3031_3036_3085_3094_3153", 2000, 1200]]}
    })

    rows = lolalytics.fetch_actual_built_sets_5("ashe", cache_dir=tmp_path)

    assert rows[0]["item_ids"] == [3031, 3036, 3085, 3094, 3153]


def test_summary_with_missing_filters_is_rebuilt(tmp_path, monkeypatch):
    _write(lolalytics.build_summary_cache_path_for("ashe", tmp_path), {"sections": {}})
    html = lolalytics.cache_path_for("ashe", tmp_path)
    html.write_text("Champions Analysed: <!--t=a-->1,200,000", encoding="utf-8")

    result = lolalytics.load_best_build("ashe", cache_dir=tmp_path)

    assert result["params"] == {"mode": "aram", "tier": "gold_plus", "patch": "7"}
    assert result["champions_analysed"] == 1_200_000


@pytest.mark.parametrize("summary_age", [0, 7])
def test_new_match_reuses_fresh_tables_even_when_summary_expires(tmp_path, monkeypatch, summary_age):
    cache = tmp_path / "cache"
    _write(lolalytics.build_summary_cache_path_for("ashe", cache), {
        "sections": {}, "candidate_items": [], "champions_analysed": 1_200_000,
        "params": {"mode": "aram", "tier": "gold_plus", "patch": "7"},
        "fetched_at": (datetime.now(timezone.utc) - timedelta(hours=summary_age)).isoformat(),
    })
    ids = [3031, 3036, 3085, 3094, 3153]
    for patch in ("7", "14", "30"):
        _write(lolalytics.built_sets_cache_path_for("ashe", cache, patch=patch), [
            {"item_ids": ids, "item_names": [str(value) for value in ids], "win_rate": 0.6,
             "pick_rate": 0.01, "games": 1000, "data_source": "build_itemset_api"}
        ])
    _write(lolalytics.boot_stats_cache_path_for("ashe", cache), [_stat()])
    for table in ("Popular Items", "Winning Items"):
        _write(lolalytics.item_stats_cache_path_for("ashe", cache, table=table), [_stat(3031)])

    players = [
        {"championName": champion, "rawChampionName": f"game_character_displayname_{champion}",
         "team": "ORDER" if index < 5 else "CHAOS", "isActivePlayer": index == 0,
         "riotId": "Self#TW2" if index == 0 else f"Player{index}#TW2"}
        for index, champion in enumerate(("Ashe", "Garen", "Lux", "Nami", "XinZhao", "Brand", "Jax", "Zyra", "Corki", "Kindred"))
    ]
    raw = {"activeplayer": {"riotId": "Self#TW2"}, "playerlist": players,
           "gamestats": {"gameMode": "ARAM", "mapNumber": 12}}
    snapshot = tmp_path / "snapshot"
    from src.live_client import save_snapshot

    save_snapshot(raw, out_dir=snapshot)
    fetches = []

    def fetch_summary(*args, **kwargs):
        fetches.append(kwargs["refresh"])
        path = lolalytics.cache_path_for("ashe", cache)
        path.write_text("Champions Analysed: <!--t=a-->1,200,000", encoding="utf-8")
        _write(path.with_suffix(".meta.json"), {"fetched_at": datetime.now(timezone.utc).isoformat()})
        return path

    monkeypatch.setattr(lolalytics, "fetch_build_html", fetch_summary)
    monkeypatch.setattr("src.service.save_snapshot", lambda *a, **k: snapshot)
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: pytest.fail("warm match must stay offline"))
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: pytest.fail("warm match must not launch a browser"))
    service = RecommendationService(
        cache_dir=cache, out_path=tmp_path / "result.json", out_markdown_path=tmp_path / "result.md",
        history_path=tmp_path / "history.db", status_path=tmp_path / "status.json",
    )
    watcher = MatchWatcher(service)

    assert watcher.process_observation(raw) is True
    assert service.status()["state"] == "ready", service.status()
    first = json.loads(service.out_path.read_text(encoding="utf-8"))
    assert watcher.process_observation(raw) is False
    assert json.loads(service.out_path.read_text(encoding="utf-8")) == first
    validate_static_recommendation(first)
    audit = audit_recommendation(first)
    assert audit["passed"] is True, audit
    assert fetches == ([True] if summary_age else [])

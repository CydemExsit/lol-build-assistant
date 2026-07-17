import json

from src.maintenance import apply_cleanup_plan, build_cleanup_plan


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_cleanup_plan_keeps_latest_snapshots_and_current_caches(tmp_path):
    for index in range(7):
        snapshot = tmp_path / "data" / "raw" / f"live_20260711_00000{index}"
        snapshot.mkdir(parents=True)
        (snapshot / "snapshot.json").write_text("{}", encoding="utf-8")
    (tmp_path / "data" / "raw" / "page_last.html").write_text("legacy", encoding="utf-8")
    (tmp_path / "data" / "cache").mkdir(parents=True)
    (tmp_path / "data" / "cache" / "page.html").write_text("html", encoding="utf-8")
    _write_json(tmp_path / "data" / "cache" / "empty.json", [])
    _write_json(
        tmp_path / "data" / "cache" / "old_sets5.json",
        [{"item_ids": [1, 2, 3, 4, 5]}],
    )
    current_cache = tmp_path / "data" / "cache" / "current_sets5.json"
    _write_json(current_cache, [{"data_source": "build_itemset_api"}])
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    (processed / "live_recommendation.json").write_text("{}", encoding="utf-8")
    (processed / "ui_old.png").write_bytes(b"png")

    plan = build_cleanup_plan(tmp_path, keep_snapshots=5)
    planned = {entry.path.relative_to(tmp_path).as_posix() for entry in plan.entries}

    assert "data/raw/live_20260711_000000" in planned
    assert "data/raw/live_20260711_000001" in planned
    assert "data/raw/live_20260711_000002" not in planned
    assert "data/raw/page_last.html" in planned
    assert "data/cache/page.html" in planned
    assert "data/cache/empty.json" in planned
    assert "data/cache/old_sets5.json" in planned
    assert "data/cache/current_sets5.json" not in planned
    assert "data/processed/ui_old.png" in planned
    assert "data/processed/live_recommendation.json" not in planned


def test_apply_cleanup_plan_only_removes_planned_paths(tmp_path):
    old_snapshot = tmp_path / "data" / "raw" / "live_20260711_000000"
    new_snapshot = tmp_path / "data" / "raw" / "live_20260711_000001"
    old_snapshot.mkdir(parents=True)
    new_snapshot.mkdir(parents=True)
    (old_snapshot / "data.json").write_text("{}", encoding="utf-8")
    (new_snapshot / "data.json").write_text("{}", encoding="utf-8")

    removed = apply_cleanup_plan(build_cleanup_plan(tmp_path, keep_snapshots=1))

    assert len(removed.entries) == 1
    assert not old_snapshot.exists()
    assert new_snapshot.exists()

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from .health import system_health
from .history import (
    DEFAULT_HISTORY_PATH,
    learned_item_adjustments,
    list_history,
    record_outcome,
    record_recommendation,
    record_route_feedback,
    stored_recommendation,
)
from .live_client import (
    build_match_context,
    build_match_key,
    build_snapshot_match_key,
    fetch_live_data,
    load_snapshot,
    save_snapshot,
)
from .lolalytics import DEFAULT_MODE, DEFAULT_PATCH, DEFAULT_TIER, build_cache_is_stale
from .recommend import recommend_from_snapshot
from .report import write_recommendation_markdown
from .runtime_state import DEFAULT_STATUS_PATH, read_status, write_status


class RecommendationService:
    def __init__(
        self,
        *,
        out_path: str | Path = "data/processed/live_recommendation.json",
        out_markdown_path: str | Path = "data/processed/live_recommendation.md",
        history_path: str | Path = DEFAULT_HISTORY_PATH,
        status_path: str | Path = DEFAULT_STATUS_PATH,
        mode: str = DEFAULT_MODE,
        tier: str = DEFAULT_TIER,
        min_champions_analysed: int = 1_000_000,
        refresh_lolalytics: bool = False,
        cache_max_age_hours: int = 168,
    ) -> None:
        self.out_path = Path(out_path)
        self.out_markdown_path = Path(out_markdown_path)
        self.history_path = Path(history_path)
        self.status_path = Path(status_path)
        self.mode = mode
        self.tier = tier
        self.min_champions_analysed = min_champions_analysed
        self.refresh_lolalytics = refresh_lolalytics
        self.cache_max_age_hours = cache_max_age_hours
        self._lock = threading.Lock()

    def _should_refresh(self, snapshot_path: str | Path) -> bool:
        if self.refresh_lolalytics:
            return True
        context = build_match_context(load_snapshot(snapshot_path), source_path=str(snapshot_path))
        champion_slug = str((context.get("active_player") or {}).get("champion_slug") or "")
        return bool(champion_slug) and build_cache_is_stale(
            champion_slug,
            mode=self.mode,
            tier=self.tier,
            patch=DEFAULT_PATCH,
            max_age_hours=self.cache_max_age_hours,
        )

    def recommend_snapshot(
        self,
        snapshot_path: str | Path,
        *,
        match_key: str | None = None,
        reuse_existing: bool = True,
    ) -> dict[str, Any]:
        snapshot = load_snapshot(snapshot_path)
        static_match_key = match_key or build_snapshot_match_key(snapshot)
        if reuse_existing:
            existing = stored_recommendation(static_match_key, self.history_path)
            if existing is not None:
                self.out_path.parent.mkdir(parents=True, exist_ok=True)
                self.out_path.write_text(
                    json.dumps(existing, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                write_recommendation_markdown(existing, self.out_markdown_path)
                session = existing.get("session") or {}
                write_status(
                    {
                        "state": "ready",
                        "message": "本場靜態方案已凍結",
                        "current_match_key": static_match_key,
                        "handled_match_key": static_match_key,
                        "recommendation_revision": session.get("revision"),
                        "recommendation_generated_at": session.get("generated_at"),
                        "compliance_mode": "static_pregame_v1",
                    },
                    self.status_path,
                )
                return existing

        with self._lock:
            write_status(
                {
                    "state": "preparing",
                    "message": "正在產生本場靜態賽前方案",
                    "current_match_key": static_match_key,
                    "recommendation_revision": None,
                    "recommendation_generated_at": None,
                    "compliance_mode": "static_pregame_v1",
                },
                self.status_path,
            )
            learned, feedback_events = learned_item_adjustments(self.history_path)
            result = recommend_from_snapshot(
                snapshot_path,
                out_path=self.out_path,
                refresh_lolalytics=self._should_refresh(snapshot_path),
                mode=self.mode,
                tier=self.tier,
                min_champions_analysed=self.min_champions_analysed,
                match_key=static_match_key,
                learned_item_adjustments=learned,
                learned_feedback_events=feedback_events,
            )
            write_recommendation_markdown(result, self.out_markdown_path)
            record_recommendation(result, self.history_path)
            session = result.get("session") or {}
            write_status(
                {
                    "state": "ready",
                    "message": "本場靜態方案已凍結",
                    "current_match_key": static_match_key,
                    "handled_match_key": static_match_key,
                    "recommendation_revision": session.get("revision"),
                    "recommendation_generated_at": session.get("generated_at"),
                    "compliance_mode": "static_pregame_v1",
                },
                self.status_path,
            )
            return result

    def capture_and_recommend(
        self,
        raw_data: dict[str, Any] | None = None,
        *,
        match_key: str | None = None,
        reuse_existing: bool = True,
    ) -> tuple[Path, dict[str, Any]]:
        raw = raw_data or fetch_live_data()
        static_match_key = match_key or build_match_key(raw)
        snapshot_path = save_snapshot(raw)
        return snapshot_path, self.recommend_snapshot(
            snapshot_path,
            match_key=static_match_key,
            reuse_existing=reuse_existing,
        )

    def status(self) -> dict[str, Any]:
        return read_status(self.status_path)

    def health(self) -> dict[str, Any]:
        return system_health(
            recommendation_path=self.out_path,
            history_path=self.history_path,
        )

    def history(self, *, limit: int = 30) -> list[dict[str, Any]]:
        return list_history(self.history_path, limit=limit)

    def feedback(self, match_key: str, route_key: str, sentiment: float) -> dict[str, Any]:
        return record_route_feedback(
            match_key,
            route_key,
            sentiment,
            self.history_path,
        )

    def outcome(self, match_key: str, outcome: int | None) -> None:
        record_outcome(match_key, outcome, self.history_path)

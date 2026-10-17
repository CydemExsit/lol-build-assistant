from __future__ import annotations

import threading
import time
import webbrowser
from typing import Any, Callable

from .data_dragon import update_static_data
from .live_client import (
    build_match_key,
    build_roster_key,
    fetch_live_data,
    is_static_roster_ready,
)
from .runtime_state import read_status, write_status
from .service import RecommendationService


class MatchWatcher:
    def __init__(
        self,
        service: RecommendationService,
        *,
        poll_interval: float = 3.0,
        ui_url: str = "http://127.0.0.1:8765",
        auto_open: bool = False,
        browser_open: Callable[[str], Any] = webbrowser.open,
        disconnect_threshold: int = 5,
    ) -> None:
        self.service = service
        self.poll_interval = max(1.0, float(poll_interval))
        self.ui_url = ui_url
        self.auto_open = auto_open
        self.browser_open = browser_open
        self.disconnect_threshold = max(1, int(disconnect_threshold))
        self._stop = threading.Event()
        status = read_status(self.service.status_path)
        self._handled_match_key = str(status.get("handled_match_key") or "")
        self._restored_roster_key = str(status.get("current_roster_key") or "")
        self._restored_match_key = str(status.get("current_match_key") or "")
        if not self._restored_roster_key or not self._restored_match_key:
            self._restored_roster_key = ""
            self._restored_match_key = ""
        self._session_roster_key = ""
        self._session_match_key = ""
        self._opened_match_key = ""
        self._failed_match_key = ""
        self._retry_after = 0.0
        self._disconnect_count = 0

    def stop(self) -> None:
        self._stop.set()

    def note_api_available(self) -> None:
        self._disconnect_count = 0

    def note_api_unavailable(self) -> bool:
        """Release the frozen Live API session after a sustained disconnect."""

        self._disconnect_count += 1
        if self._disconnect_count != self.disconnect_threshold:
            return False
        had_session = bool(
            self._session_match_key
            or self._session_roster_key
            or self._restored_match_key
            or self._restored_roster_key
        )
        self._session_match_key = ""
        self._session_roster_key = ""
        self._restored_match_key = ""
        self._restored_roster_key = ""
        self._opened_match_key = ""
        self._failed_match_key = ""
        self._retry_after = 0.0
        write_status(
            {
                "state": "waiting",
                "message": "等待新的英雄聯盟對局",
                "current_match_key": None,
                "current_roster_key": None,
                "last_error": None,
            },
            self.service.status_path,
        )
        return had_session

    def _session_for_observation(self, raw_data: dict[str, Any]) -> tuple[str, str] | None:
        if not is_static_roster_ready(raw_data):
            return None
        roster_key = build_roster_key(raw_data)

        if self._session_match_key:
            if roster_key != self._session_roster_key:
                return None
            return self._session_match_key, self._session_roster_key

        if self._restored_match_key:
            if roster_key == self._restored_roster_key:
                self._session_match_key = self._restored_match_key
                self._session_roster_key = self._restored_roster_key
                self._restored_match_key = ""
                self._restored_roster_key = ""
                return self._session_match_key, self._session_roster_key
            self._restored_match_key = ""
            self._restored_roster_key = ""

        self._session_match_key = build_match_key(raw_data)
        self._session_roster_key = roster_key
        return self._session_match_key, self._session_roster_key

    def process_observation(self, raw_data: dict[str, Any]) -> bool:
        session = self._session_for_observation(raw_data)
        if session is None:
            return False
        match_key, roster_key = session
        if not match_key or match_key == self._handled_match_key:
            return False
        if match_key == self._failed_match_key and time.monotonic() < self._retry_after:
            return False
        write_status(
            {
                "state": "detected",
                "message": "已發現新對局",
                "current_match_key": match_key,
                "current_roster_key": roster_key,
                "recommendation_revision": None,
                "recommendation_generated_at": None,
                "compliance_mode": "static_pregame_v1",
            },
            self.service.status_path,
        )
        if self.auto_open and self._opened_match_key != match_key:
            self.browser_open(self.ui_url)
            self._opened_match_key = match_key
        try:
            self.service.capture_and_recommend(
                raw_data,
                match_key=match_key,
                reuse_existing=True,
            )
        except Exception as exc:
            self._failed_match_key = match_key
            self._retry_after = time.monotonic() + 30.0
            write_status(
                {
                    "state": "error",
                    "message": "本場靜態方案產生失敗，稍後重試",
                    "last_error": str(exc),
                    "current_match_key": match_key,
                    "current_roster_key": roster_key,
                },
                self.service.status_path,
            )
        else:
            self._handled_match_key = match_key
            self._failed_match_key = ""
            self._retry_after = 0.0
        return True

    def run_forever(self) -> None:
        write_status(
            {
                "state": "waiting",
                "message": "等待新的英雄聯盟對局",
                "compliance_mode": "static_pregame_v1",
                "browser_auto_open": self.auto_open,
            },
            self.service.status_path,
        )
        while not self._stop.is_set():
            try:
                observation = fetch_live_data(timeout=1.5)
            except Exception:
                self.note_api_unavailable()
            else:
                self.note_api_available()
                self.process_observation(observation)
            self._stop.wait(self.poll_interval)


def refresh_static_data_in_background(service: RecommendationService) -> threading.Thread:
    def worker() -> None:
        try:
            result = update_static_data()
            write_status(
                {"static_data": result},
                service.status_path,
            )
        except Exception as exc:
            write_status(
                {"static_data": {"updated": False, "error": str(exc)}},
                service.status_path,
            )

    thread = threading.Thread(target=worker, name="data-dragon-refresh", daemon=True)
    thread.start()
    return thread


def run_assistant(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    poll_interval: float = 3.0,
    auto_open: bool = False,
    service: RecommendationService | None = None,
) -> None:
    """Run the browser UI and static pre-game watcher as one local service."""

    from .server import create_server

    active_service = service or RecommendationService()
    httpd = create_server(active_service, host=host, port=port)
    server_thread = threading.Thread(
        target=httpd.serve_forever,
        name="lol-build-assistant-http",
        daemon=True,
    )
    server_thread.start()
    ui_url = f"http://{host}:{port}"
    write_status(
        {
            "state": "starting",
            "message": "背景服務已啟動",
            "service_mode": "watch",
            "ui_url": ui_url,
            "compliance_mode": "static_pregame_v1",
            "browser_auto_open": bool(auto_open),
        },
        active_service.status_path,
    )
    refresh_static_data_in_background(active_service)
    watcher = MatchWatcher(
        active_service,
        poll_interval=poll_interval,
        ui_url=ui_url,
        auto_open=auto_open,
    )
    print(f"[ok] ui -> {ui_url}")
    print("[ok] waiting for a new match; recommendations are generated once and frozen")
    try:
        watcher.run_forever()
    except KeyboardInterrupt:
        print("\n[ok] watcher stopped")
    finally:
        watcher.stop()
        httpd.shutdown()
        httpd.server_close()
        write_status(
            {"state": "offline", "message": "背景服務已停止"},
            active_service.status_path,
        )

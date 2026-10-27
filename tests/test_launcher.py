import importlib
import io
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest


pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows shortcut launcher")


@pytest.fixture
def launcher(monkeypatch, tmp_path):
    module = importlib.import_module("scripts.launch_assistant")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "RUNTIME", tmp_path / "data" / "runtime")
    python = tmp_path / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.touch()
    return module


def mock_response(launcher, monkeypatch, payload, server="LolBuildAssistant/1.0"):
    response = io.BytesIO(json.dumps(payload).encode())
    response.headers = {"Server": server}
    monkeypatch.setattr(launcher.urllib.request, "urlopen", lambda *a, **k: response)


def test_health_requires_automatic_match_watcher(launcher, monkeypatch):
    mock_response(launcher, monkeypatch, {"ok": True, "status": {"service_mode": "watch"}})
    assert launcher.service_ready() is True


@pytest.mark.parametrize("payload", [[], None, {"ok": True}, {"ok": True, "status": []},
                                    {"ok": False}, {"ok": 1, "status": {"service_mode": "watch"}},
                                    {"ok": True, "status": {}}])
def test_unrecognized_status_is_not_ready(launcher, monkeypatch, payload):
    mock_response(launcher, monkeypatch, payload)
    assert launcher.service_ready() is False


def test_rejects_another_server(launcher, monkeypatch):
    mock_response(launcher, monkeypatch, {"ok": True, "status": {"service_mode": "watch"}}, "Other/1")
    assert launcher.service_ready() is False


def test_manual_service_does_not_start_another_process_or_open_browser(launcher, monkeypatch):
    mock_response(launcher, monkeypatch, {"ok": True, "status": {"service_mode": "manual"}})
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *a, **k: pytest.fail("duplicate service"))
    monkeypatch.setattr(launcher.webbrowser, "open", lambda *a: pytest.fail("watcher not running"))
    with pytest.raises(RuntimeError, match="新對局偵測"):
        launcher.main()


def test_existing_watcher_is_reused(launcher, monkeypatch):
    monkeypatch.setattr(launcher, "service_ready", lambda: True)
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *a, **k: pytest.fail("duplicate service"))
    opened = []
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: opened.append(url) or True)
    assert launcher.main() == 0
    assert opened == [launcher.URL]


def test_stopped_watcher_starts_hidden_and_opens_only_after_ready(launcher, monkeypatch):
    readiness = iter([False, False, True])
    monkeypatch.setattr(launcher, "service_ready", lambda: next(readiness))
    events = []

    class Process:
        def poll(self):
            events.append("waiting")
            return None

    def start(args, **kwargs):
        assert args == [str(launcher.ROOT / ".venv/Scripts/python.exe"), "-u", "-B", "-m", "src.main", "watch"]
        assert kwargs["cwd"] == launcher.ROOT
        assert kwargs["creationflags"] & launcher.subprocess.CREATE_NO_WINDOW
        assert kwargs["creationflags"] & launcher.subprocess.DETACHED_PROCESS
        events.append("start")
        return Process()

    monkeypatch.setattr(launcher.subprocess, "Popen", start)
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: events.append("browser") or True)
    assert launcher.main() == 0
    assert events == ["start", "waiting", "browser"]


def test_start_failure_does_not_open_browser_and_releases_lock(launcher, monkeypatch):
    monkeypatch.setattr(launcher, "service_ready", lambda: False)

    class Process:
        def poll(self):
            return 1

    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *a, **k: Process())
    monkeypatch.setattr(launcher.webbrowser, "open", lambda *a: pytest.fail("failed service"))
    with pytest.raises(RuntimeError, match="啟動失敗"):
        launcher.main()
    # A later click can recover after failure instead of inheriting the lock.
    monkeypatch.setattr(launcher, "service_ready", lambda: True)
    monkeypatch.setattr(launcher.webbrowser, "open", lambda *a: True)
    assert launcher.main() == 0


def test_missing_environment_has_clear_error(launcher, monkeypatch):
    (launcher.ROOT / ".venv/Scripts/python.exe").unlink()
    monkeypatch.setattr(launcher, "service_ready", lambda: False)
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *a, **k: pytest.fail("missing environment"))
    with pytest.raises(RuntimeError, match="一次性安裝"):
        launcher.main()


def test_simultaneous_clicks_start_only_one_watcher(launcher, monkeypatch):
    ready = threading.Event()
    barrier = threading.Barrier(2)
    starts, opened = [], []
    monkeypatch.setattr(launcher, "service_ready", ready.is_set)

    def start(*args, **kwargs):
        starts.append(args)
        time.sleep(0.1)
        ready.set()
        return object()

    monkeypatch.setattr(launcher.subprocess, "Popen", start)
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: opened.append(url) or True)

    def click():
        barrier.wait(timeout=5)
        return launcher.main()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(click) for _ in range(2)]
        assert [f.result(timeout=10) for f in futures] == [0, 0]
    assert len(starts) == 1
    assert opened == [launcher.URL, launcher.URL]

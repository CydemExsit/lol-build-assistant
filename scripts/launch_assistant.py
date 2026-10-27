"""Windows shortcut entry point: start the local service and open its UI."""

from __future__ import annotations

import ctypes
import json
import msvcrt
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:8765"
RUNTIME = ROOT / "data" / "runtime"


def service_ready() -> bool:
    try:
        with urllib.request.urlopen(f"{URL}/api/status", timeout=1) as response:
            if not response.headers.get("Server", "").startswith("LolBuildAssistant/"):
                return False
            payload = json.load(response)
            if not isinstance(payload, dict) or payload.get("ok") is not True:
                return False
            status = payload.get("status")
            if not isinstance(status, dict):
                return False
            if status.get("service_mode") == "manual":
                raise RuntimeError(
                    "目前服務只有網頁介面，尚未開啟新對局偵測。"
                    "請先關閉手動啟動的網頁服務，再重新開啟助手。"
                )
            return status.get("service_mode") == "watch"
    except (OSError, ValueError):
        return False


def main() -> int:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    # Serialize rapid repeated clicks so they cannot start duplicate services.
    with (RUNTIME / "launcher.lock").open("a+b") as lock:
        lock.seek(0, 2)
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        deadline = time.monotonic() + 45
        while True:
            try:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("另一個啟動程序尚未完成，請稍後再試。")
                time.sleep(0.2)
        try:
            if not service_ready():
                python = ROOT / ".venv" / "Scripts" / "python.exe"
                if not python.is_file():
                    raise RuntimeError("找不到專案的 Python 環境，請先完成 README 的一次性安裝。")
                with (RUNTIME / "assistant-stdout.log").open("ab") as stdout, (
                    RUNTIME / "assistant-stderr.log"
                ).open("ab") as stderr:
                    process = subprocess.Popen(
                        [str(python), "-u", "-B", "-m", "src.main", "watch"],
                        cwd=ROOT,
                        stdin=subprocess.DEVNULL,
                        stdout=stdout,
                        stderr=stderr,
                        creationflags=subprocess.CREATE_NO_WINDOW
                        | subprocess.DETACHED_PROCESS,
                    )
                deadline = time.monotonic() + 30
                while not service_ready():
                    if process.poll() is not None:
                        raise RuntimeError("背景服務啟動失敗。")
                    if time.monotonic() >= deadline:
                        raise RuntimeError("背景服務啟動逾時。")
                    time.sleep(0.25)
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
    if not webbrowser.open(URL):
        raise RuntimeError(f"無法開啟瀏覽器，請手動開啟 {URL}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        ctypes.windll.user32.MessageBoxW(
            None,
            f"{exc}\n\n錯誤日誌：{RUNTIME / 'assistant-stderr.log'}",
            "LoL 出裝助手",
            0x10,
        )
        sys.exit(1)

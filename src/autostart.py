from __future__ import annotations

import os
import sys
from pathlib import Path


STARTUP_FILENAME = "LoL Build Assistant.vbs"


def startup_script_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is unavailable; Windows autostart cannot be configured")
    return (
        Path(appdata)
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
        / STARTUP_FILENAME
    )


def _pythonw_path(root: Path) -> Path:
    venv_pythonw = root / ".venv" / "Scripts" / "pythonw.exe"
    if venv_pythonw.exists():
        return venv_pythonw
    current = Path(sys.executable).resolve()
    pythonw = current.with_name("pythonw.exe")
    return pythonw if pythonw.exists() else current


def _vbs_string(value: str | Path) -> str:
    return str(value).replace('"', '""')


def install_autostart(root: str | Path = ".") -> Path:
    workspace = Path(root).resolve()
    pythonw = _pythonw_path(workspace)
    target = startup_script_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    script = "\n".join(
        [
            'Set shell = CreateObject("WScript.Shell")',
            f'shell.CurrentDirectory = "{_vbs_string(workspace)}"',
            (
                f'shell.Run Chr(34) & "{_vbs_string(pythonw)}" & Chr(34) & '
                ' " -B -m src.main watch", 0, False'
            ),
            "",
        ]
    )
    target.write_text(script, encoding="ascii")
    return target


def remove_autostart() -> bool:
    target = startup_script_path()
    if not target.exists():
        return False
    target.unlink()
    return True


def autostart_status() -> dict[str, object]:
    target = startup_script_path()
    return {"installed": target.exists(), "path": str(target)}

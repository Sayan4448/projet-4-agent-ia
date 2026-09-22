"""Path helpers that work both in development and inside a frozen (PyInstaller) exe.

Since v1.2 the app runs elevated (admin) and stores user data in
%LOCALAPPDATA%/AgentScreen so it never writes into Program Files.

The Windows well-known folders at the end of this module are shared by the
app catalogue (data) and app discovery (logic) so neither re-declares them.
"""
import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """Writable root for config-like files: %LOCALAPPDATA%/AgentScreen when
    frozen (works even when installed in Program Files), project root in dev."""
    if is_frozen():
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        d = Path(base) / "AgentScreen"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    d = app_root() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_file() -> Path:
    return data_dir() / "config.json"


def shots_dir() -> Path:
    d = data_dir() / "shots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def conversations_file() -> Path:
    return data_dir() / "conversations.json"


def recordings_dir() -> Path:
    """Where the agent saves the short MP4 clips it records for editing."""
    d = data_dir() / "recordings"
    d.mkdir(parents=True, exist_ok=True)
    return d


def legacy_config_candidates():
    """Configs written by earlier versions (v1.0-1.2) that may hold keys.

    The current config is never a source: reading it as an "older" file would
    make the migration write to whatever path it was given.
    """
    out = []
    if is_frozen():
        exe_dir = Path(sys.executable).resolve().parent
        out.append(exe_dir / "data" / "config.json")          # v1.1-1.2 (exe folder)
        out.append(exe_dir.parent / "Program Files" / "AgentScreen" / "data" / "config.json")
    else:
        root = Path(__file__).resolve().parent.parent
        out.append(root / "dist" / "data" / "config.json")    # v1.0 exe
    here = config_file()
    return [p for p in out if p != here]


def env_file_candidates():
    """Optional .env fallback locations (first match wins)."""
    if is_frozen():
        return [app_root() / ".env"]
    root = app_root()
    return [root / ".env", root.parent / ".env"]


# ------------------------------------------------- Windows well-known folders
PROGRAM_FILES = os.environ.get("ProgramFiles", r"C:\Program Files")
PROGRAM_FILES_X86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
LOCAL_APPDATA = os.environ.get("LOCALAPPDATA", "")
ROAMING_APPDATA = os.environ.get("APPDATA", "")
PROGRAM_DATA = os.environ.get("ProgramData", r"C:\ProgramData")
WINDOWS_DIR = os.environ.get("WINDIR", r"C:\Windows")


def join(*parts: str) -> str:
    """os.path.join that drops empty parts (unset env vars produce ''),
    so a missing %LOCALAPPDATA% never turns a path into a relative one."""
    parts = [p for p in parts if p]
    return os.path.join(*parts) if parts else ""


def load_dotenv_if_present() -> None:
    """Tiny .env loader (no dependency): sets os.environ vars not already set."""
    for candidate in env_file_candidates():
        if not candidate.is_file():
            continue
        try:
            for raw in candidate.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
        except OSError:
            pass
        break

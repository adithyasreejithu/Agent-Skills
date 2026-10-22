"""Small cross-platform process and stream helpers; no optional dependencies."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def configure_stdio() -> None:
    """Call at script entry only, leaving imported modules' streams untouched."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if reconfigure is not None:
            try:
                reconfigure(encoding='utf-8', errors='backslashreplace')
            except (OSError, ValueError):
                pass


def diagnostic(value, limit: int = 3000) -> str:
    if isinstance(value, bytes):
        value = value.decode('utf-8', errors='replace')
    return str(value or '').strip()[-limit:]


def find_tool(name: str) -> str | None:
    """PATH first, then beside this interpreter: an unactivated venv (e.g. a scheduled task) keeps yt-dlp there."""
    return shutil.which(name) or shutil.which(name, path=str(Path(sys.executable).parent))


def run_text(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Capture diagnostics predictably, including Windows pipes and launch failures."""
    try:
        return subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace', **kwargs)
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(f'{cmd[0]} timed out: {diagnostic(exc.stderr)}') from None
    except OSError as exc:
        raise SystemExit(
            f'Cannot run {cmd[0]} ({type(exc).__name__}). Check that the executable is installed '
            'and permitted by your operating system, then retry.'
        ) from None

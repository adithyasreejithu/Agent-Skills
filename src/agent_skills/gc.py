"""Garbage collector for watch-output/.

Only ever deletes the heavy, regenerable artifacts inside per-video folders
(frames and downloads). Reports (*.md) and anything else is left alone.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# Video data lives in watch-output/video-data/; summaries are stored outside watch-output and never touched here.
WATCH_OUTPUT = Path(os.environ.get("WATCH_OUTPUT_DIR") or REPO_ROOT / "watch-output" / "video-data").expanduser().resolve()

FRAME_TARGETS = ("frames", "cues", "sheets")
DOWNLOAD_TARGETS = ("download", "download-test", "video", "audio.mp3")
LEGACY_TEMP_RE = re.compile(r"^watch-")  # old default: %TEMP%\watch-<random>


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _fmt(n: int) -> str:
    return f"{n / 1_048_576:.1f} MB"


def _video_dirs(video: str | None) -> list[Path]:
    if not WATCH_OUTPUT.is_dir():
        return []
    if video:
        target = (WATCH_OUTPUT / video).resolve()
        if target.parent != WATCH_OUTPUT or not target.is_dir():
            raise SystemExit(f"no such video folder in watch-output: {video}")
        return [target]
    return sorted(p for p in WATCH_OUTPUT.iterdir() if p.is_dir())


def _targets(video_dirs: list[Path], names: tuple[str, ...]) -> list[Path]:
    return [d / n for d in video_dirs for n in names if (d / n).exists()]


def _legacy_temp_dirs() -> list[Path]:
    tmp = Path(tempfile.gettempdir())
    return sorted(p for p in tmp.iterdir() if p.is_dir() and LEGACY_TEMP_RE.match(p.name))


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def status() -> None:
    print(f"watch-output: {WATCH_OUTPUT}")
    dirs = _video_dirs(None)
    if not dirs:
        print("  (no videos stored)")
    for d in dirs:
        frames = sum(_size(p) for p in _targets([d], FRAME_TARGETS))
        downloads = sum(_size(p) for p in _targets([d], DOWNLOAD_TARGETS))
        print(f"  {d.name}: frames {_fmt(frames)}, downloads {_fmt(downloads)}")
    legacy = _legacy_temp_dirs()
    if legacy:
        print(f"  {len(legacy)} legacy watch-* folder(s) in system temp (clear with --temp)")
    print("Nothing deleted. Use: agent-skills clean --frames | --downloads | --all [--video ID] [--temp] [--dry-run]")


def clean(
    *,
    frames: bool = False,
    downloads: bool = False,
    video: str | None = None,
    temp: bool = False,
    dry_run: bool = False,
) -> int:
    if not (frames or downloads or temp):
        status()
        return 0

    victims: list[Path] = []
    dirs = _video_dirs(video)
    if frames:
        victims += _targets(dirs, FRAME_TARGETS)
    if downloads:
        victims += _targets(dirs, DOWNLOAD_TARGETS)
    if temp:
        victims += _legacy_temp_dirs()

    freed = 0
    for path in victims:
        size = _size(path) if path.exists() else 0
        freed += size
        print(f"{'would remove' if dry_run else 'removing'}: {path} ({_fmt(size)})")
        if not dry_run:
            _remove(path)
    if not dry_run:
        for d in dirs:
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
    verb = "would free" if dry_run else "freed"
    print(f"{verb} {_fmt(freed)} across {len(victims)} item(s). Reports (*.md) were kept.")
    return 0

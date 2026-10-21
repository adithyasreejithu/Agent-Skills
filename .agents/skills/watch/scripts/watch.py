#!/usr/bin/env python3
"""/watch entry point: download video, extract frames, parse transcript.

Prints a markdown report to stdout listing frame paths + transcript. Claude
then Reads each frame path to see the video.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

from config import ConfigError, frame_cap, get_config, load_gemini_key, resolve_engine  # noqa: E402
import gemini  # noqa: E402
from download import download, fetch_captions, is_url, auth_args  # noqa: E402
from frames import MAX_FPS, auto_fps, auto_fps_focus, extract_at_timestamps, extract_keyframes, extract_scene_or_uniform, format_time, get_metadata, merge_frames, parse_time, parse_timestamps, validate_controls  # noqa: E402
from transcribe import filter_range, format_transcript, parse_vtt  # noqa: E402
from whisper import extract_audio, load_api_key, transcribe_video  # noqa: E402
from runtime import configure_stdio  # noqa: E402
from testing import CONTROL_FRAMES, build_sheets, find_cues, load_bank, parse_offsets, propose_terms, select_cues, timestamps_for, write_outputs  # noqa: E402


REPO_ROOT = SCRIPT_DIR.parents[3]  # scripts -> watch -> skills -> .agents -> repo
# Everything a video produces (downloads, frames, sheets, cue data) lives under watch-output/video-data/.
# Written summaries are kept elsewhere (summaries/ at the repo root).
WATCH_OUTPUT = Path(os.environ.get("WATCH_OUTPUT_DIR") or REPO_ROOT / "watch-output" / "video-data").expanduser().resolve()
BANK_PATH = REPO_ROOT / "training" / "word-bank.json"
LABELS_DIR = REPO_ROOT / "training" / "labels"
YOUTUBE_ID_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11})")


def default_work_dir(source: str) -> Path:
    """watch-output/video-data/<video-id> so every video lands in one known, gc-able place."""
    if is_url(source):
        match = YOUTUBE_ID_RE.search(source)
        slug = match.group(1) if match else "url-" + hashlib.sha1(source.encode()).hexdigest()[:10]
    else:
        slug = re.sub(r"[^A-Za-z0-9_-]+", "-", Path(source).stem).strip("-") or "local"
    return WATCH_OUTPUT / slug


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


# One JSON line per run, appended to watch-output/watch-log.jsonl, so a later pass can parse what went wrong.
LOG_FILE = Path(os.environ.get("WATCH_LOG_FILE") or WATCH_OUTPUT.parent / "watch-log.jsonl").expanduser()
RUN: dict = {"events": []}


def log_event(kind: str, message: str, level: str = "warn") -> None:
    RUN["events"].append({"kind": kind, "level": level, "message": message})
    print(f"[watch] logged {level} {kind}: {message}", file=sys.stderr)


def choose_backend(source: str, backend_choice: str, has_gemini_key: bool) -> str:
    """Speech fallback for a source with no captions. YouTube never uploads audio on its own (it is logged);
    anything else (reels, local files) sends only its audio track to Gemini when a key exists."""
    if backend_choice != "auto":
        return backend_choice
    if gemini.is_youtube(source):
        return "none"
    return "gemini" if has_gemini_key else "auto"


def write_result_file(path: Path, exit_code) -> None:
    """Machine-readable summary of this run (the same fields as the log line), for callers such as ingest.
    Best-effort: it never changes the run's result."""
    try:
        record = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "exit_code": exit_code,
                  "event_kinds": [e["kind"] for e in RUN["events"]], **RUN}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        print(f"[watch] could not write result file: {exc}", file=sys.stderr)


def write_run_log(exit_code) -> None:
    """Best-effort: logging must never change a run's result."""
    try:
        record = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "exit_code": exit_code, **RUN}
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001
        print(f"[watch] could not write run log: {exc}", file=sys.stderr)


LOCAL_ONLY_FLAGS = (("--detail", "detail"), ("--fps", "fps"), ("--max-frames", "max_frames"),
                    ("--timestamps", "timestamps"), ("--whisper", "whisper"), ("--sub-lang", "sub_lang"),
                    ("--testing-offsets", "testing_offsets"))


def run_gemini(args, config, key, start_sec, end_sec, auth) -> int:
    """Google watches the video. No captions, frames, or Whisper; no fallback on failure."""
    ignored = [flag for flag, name in LOCAL_ONLY_FLAGS if getattr(args, name) is not None]
    ignored += [flag for flag, on in (("--no-whisper", args.no_whisper), ("--no-dedup", args.no_dedup)) if on]
    clip = (start_sec, end_sec) if start_sec is not None or end_sec is not None else None
    uploaded, warning, result, error, sent, work = None, None, None, None, "URL sent to Google", None
    try:
        if gemini.is_youtube(args.source):
            video = {"uri": args.source}
        else:
            parent = Path(args.out_dir).expanduser().resolve() if args.out_dir else None
            if parent:
                parent.mkdir(parents=True, exist_ok=True)
            sent = "not sent to Google"
            work = Path(tempfile.mkdtemp(prefix="watch-", dir=parent))
            print("[watch] downloading media…" if is_url(args.source) else "[watch] using local file…", file=sys.stderr)
            media = download(args.source, work / "download", **(auth if is_url(args.source) else {}))
            sent = "upload to Google failed"
            print("[watch] uploading to the Gemini Files API…", file=sys.stderr)
            uploaded = gemini.upload_file(Path(media["video_path"]), key)
            video = {"uri": uploaded["uri"], "mime_type": uploaded["mime_type"]}
            sent = "video uploaded to Google, deleted after the answer"
        print(f"[watch] asking {config['gemini_model']}…", file=sys.stderr)
        result = gemini.ask(video, args.question, model=config["gemini_model"], key=key,
                            clip=clip, timeout=config["gemini_timeout"])
    except SystemExit as exc:
        error = str(exc)
    finally:
        if uploaded:
            warning = gemini.delete_file(uploaded["name"], key)
        if work:  # Run-owned; holds at most a downloaded copy. A local source file lives elsewhere.
            shutil.rmtree(work, ignore_errors=True)

    RUN.update(engine="gemini-video", model=config["gemini_model"], outcome="failed" if error else "ok",
               tokens=result["total_tokens"] if result else None, clipped=bool(clip), ignored_flags=ignored)
    print()
    print("# watch: video report")
    print()
    print(f"- **Source:** {args.source} ({sent})")
    print(f"- **Engine:** {config['gemini_model']} ({result['processing'] if result else 'failed'})")
    if clip:
        print(f"- **Focus range:** {format_time(start_sec or 0)} → {format_time(end_sec) if end_sec is not None else 'end'}")
    if ignored:
        print(f"- **Ignored local options:** {', '.join(ignored)} (these only apply with --engine local)")
    if result and result["total_tokens"] is not None:
        print(f"- **Gemini tokens:** {result['total_tokens']}")
    if warning:
        print(f"- **Cleanup warning:** {warning}")
    print()
    if error:
        print("## Unavailable evidence")
        print()
        print(f"- {error}")
        log_event("gemini_video_failed", error, "error")
        return 1
    print("## Answer (from Gemini)")
    print()
    print("_These are Gemini's observations of the video, not frames you viewed yourself. "
          "Relay them as such; rerun with `--engine local` to inspect frames directly._")
    print()
    print(result["text"])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="watch",
        description="Download a video, extract auto-scaled frames, and surface the transcript.",
    )
    ap.add_argument("source", help="Video URL or local file path")
    ap.add_argument("--max-frames", type=int, default=None, help="Override frame cap")
    ap.add_argument("--resolution", type=int, default=512, help="Frame width in pixels (default 512)")
    ap.add_argument("--fps", type=float, default=None, help="Override auto-fps")
    ap.add_argument(
        "--detail",
        choices=["transcript", "efficient", "balanced", "token-burner"],
        default=None,
        help="Fidelity/speed dial: transcript (no frames), efficient (fast keyframes, cap 50), "
             "balanced (scene, cap 100), token-burner (scene, uncapped).",
    )
    ap.add_argument(
        "--timestamps",
        type=str,
        default=None,
        help="Comma-separated absolute timestamps (SS, MM:SS, HH:MM:SS) to grab a frame at, "
             "e.g. transcript-flagged 'look here' moments. Added on top of the detail frames "
             "(reserved against the cap); with --detail transcript these become the only frames.",
    )
    ap.add_argument("--start", type=str, default=None, help="Range start (SS, MM:SS, or HH:MM:SS)")
    ap.add_argument("--end", type=str, default=None, help="Range end (SS, MM:SS, or HH:MM:SS)")
    ap.add_argument("--out-dir", type=str, default=None,
                    help="Working directory (default: <repo>/watch-output/video-data/<video-id>)")
    ap.add_argument(
        "--no-whisper",
        action="store_true",
        help="Disable all local/cloud transcription fallbacks; native captions still work.",
    )
    ap.add_argument(
        "--whisper",
        choices=["groq", "openai", "whisperx", "gemini"],
        default=None,
        help="Select the fallback backend for this run; native captions still come first.",
    )
    ap.add_argument(
        "--no-dedup",
        action="store_true",
        help="Disable near-duplicate frame removal. Keeps visually identical "
             "frames (static screen recordings, held slides) instead of collapsing them.",
    )
    ap.add_argument("--result-json", default=None,
                    help="Also write this run's machine-readable result here (it is always written to <work>/result.json "
                         "for the local engine).")
    ap.add_argument("--sub-lang", default=None, help="Exact caption language preference (default auto/native)")
    cookies = ap.add_mutually_exclusive_group()
    cookies.add_argument("--cookies", default=None, help="Explicit cookie file (yt-dlp may update this jar)")
    cookies.add_argument("--cookies-from-browser", default=None, help="Explicit yt-dlp browser selector")
    ap.add_argument(
        "--testing",
        action="store_true",
        help="Training mode (local engine only): find cues in the transcript with training/word-bank.json, "
             "grab frames at several offsets around each, build one contact sheet per cue, and write a label file.",
    )
    ap.add_argument("--testing-cap", type=int, default=150, help="Total frame cap in testing mode (default 150)")
    ap.add_argument("--testing-offsets", type=str, default=None,
                    help="Comma-separated seconds around each cue (default -2,0,2,4,6)")
    ap.add_argument("--engine", choices=["auto", "gemini", "local"], default=None,
                    help="gemini: Google watches the video and answers (needs GEMINI_API_KEY). "
                         "local: frames + transcript on this machine. Default auto: gemini when a key exists.")
    ap.add_argument("--question", default=None,
                    help="The user's question. Sent to Gemini on a gemini run; unused by the local engine.")
    args = ap.parse_args()
    RUN.update(source=args.source, engine_arg=args.engine, testing=args.testing)
    if args.no_whisper and args.whisper:
        ap.error("--no-whisper conflicts with --whisper")
    if args.testing and args.engine == "gemini":
        ap.error("--testing needs frames and a transcript; it only works with the local engine")

    config = get_config(backend_override="none" if args.no_whisper else args.whisper)
    detail = args.detail or config["detail"]
    if args.testing and detail == "transcript":
        detail = "balanced"  # testing needs the video for frames
    max_frames = args.max_frames if args.max_frames is not None else frame_cap(detail)
    budget_cap = max_frames if max_frames is not None else 100
    start_sec, end_sec = parse_time(args.start), parse_time(args.end)
    validate_controls(args.resolution, max_frames, start_sec, end_sec, args.fps)
    cue_timestamps = parse_timestamps(args.timestamps)
    backend_choice = "none" if args.no_whisper else args.whisper or config["whisper_backend"]
    cookies_file = args.cookies if args.cookies is not None else (None if args.cookies_from_browser else config["cookies_file"])
    cookies_browser = args.cookies_from_browser if args.cookies_from_browser is not None else (None if args.cookies else config["cookies_from_browser"])
    auth_args(cookies_file, cookies_browser)  # Validate even before starting network work.
    auth = {"cookies_file": cookies_file, "cookies_from_browser": cookies_browser}

    gemini_key = load_gemini_key()
    if not args.testing and resolve_engine(args.engine or config["engine"], bool(gemini_key)) == "gemini":
        return run_gemini(args, config, gemini_key, start_sec, end_sec, auth)

    if args.out_dir:
        parent = Path(args.out_dir).expanduser().resolve()
        parent.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="watch-", dir=parent))
    else:
        work = default_work_dir(args.source)
        work.mkdir(parents=True, exist_ok=True)
    print(f"[watch] stored in watch-output: {work}", file=sys.stderr)
    url_source = is_url(args.source)
    dl = {"subtitle_path": None, "info": {}, "downloaded": False}
    errors = []
    all_segments = []
    track_available = False
    transcript_source = None
    video_path = None
    visual_error = None
    gaps = []

    if url_source:
        print("[watch] checking metadata/captions via yt-dlp…", file=sys.stderr)
        dl = fetch_captions(args.source, work / "download", sub_lang=args.sub_lang or config["sub_lang"], **auth)
        errors.extend(dl.get("errors", []))
        if dl.get("subtitle_path"):
            try:
                all_segments = parse_vtt(dl["subtitle_path"])
                track_available = bool(all_segments)
                track = dl.get("caption_track") or {}
                transcript_source = (f"captions ({track.get('language', 'unknown')}, "
                                     f"{track.get('kind', 'unknown')}, {track.get('provenance', 'unknown')})")
            except (OSError, ValueError) as exc:
                errors.append(f"Caption parsing failed: {exc}")
        # available | none (the video has no usable track, permanent) | fetch_failed (the request errored, e.g. a 429; retry later)
        caption_status = "available" if track_available else ("fetch_failed" if dl.get("errors") else "none")
    else:
        caption_status = "not-applicable"

    audio_only =detail == "transcript" and not cue_timestamps
    # Captions are assessed before range filtering: a quiet interval is not a missing track.
    need_media = not (audio_only and (track_available or backend_choice == "none") and url_source)
    if need_media:
        try:
            print("[watch] downloading media…" if url_source else "[watch] using local file…", file=sys.stderr)
            media = download(args.source, work / "download", audio_only=audio_only,
                             **({"context": dl, **auth} if url_source else {}))
            dl.update(media)
            video_path = dl["video_path"]
        except SystemExit as exc:
            visual_error = f"Media unavailable: {exc}"
            errors.append(visual_error)

    try:
        duration = float((dl.get("info") or {}).get("duration") or 0)
        if not math.isfinite(duration) or duration < 0:
            duration = 0.0
    except (TypeError, ValueError):
        duration = 0.0
    meta = {"duration_seconds": duration, "width": None, "height": None, "codec": None,
            "has_audio": False, "has_video": False}
    if video_path:
        try:
            meta = get_metadata(video_path)
        except SystemExit as exc:
            visual_error = f"Visuals/audio metadata unavailable: {exc}"
            errors.append(visual_error)
    full_duration = meta["duration_seconds"]
    if full_duration > 0 and start_sec is not None and start_sec >= full_duration:
        raise SystemExit(f"--start {start_sec:.1f}s is past end of video ({full_duration:.1f}s)")
    effective_start = start_sec or 0.0
    effective_end = min(end_sec, full_duration) if end_sec is not None and full_duration > 0 else end_sec or full_duration
    effective_duration = max(0.0, effective_end - effective_start)
    focused = start_sec is not None or end_sec is not None
    if focused:
        fps, target = auto_fps_focus(effective_duration, max_frames=budget_cap)
    else:
        fps, target = auto_fps(effective_duration, max_frames=budget_cap)
    if args.fps is not None:
        fps = min(args.fps, MAX_FPS)
        target = max(1, int(round(fps * effective_duration)))

    # Speech comes first (captions, else the routed fallback) so testing mode can find cues in any transcript,
    # including Gemini audio for sources with no captions.
    transcript_state = "missing"
    # Routing for a source with no captions. YouTube never uploads audio on its own (notify instead);
    # anything else (reels, local files) sends only its audio track to Gemini when a key exists.
    youtube = gemini.is_youtube(args.source)
    effective_backend = choose_backend(args.source, backend_choice, bool(gemini_key))
    if not track_available and effective_backend != "none" and video_path and meta.get("has_audio"):
        if effective_backend == "gemini":
            backend, api_key = ("gemini", gemini_key) if gemini_key else (None, None)
        else:
            backend, api_key = ("whisperx", None) if effective_backend == "whisperx" else load_api_key(None if effective_backend == "auto" else effective_backend)
        if backend:
            try:
                if backend == "gemini":
                    print(f"[watch] sending only the audio track to {config['gemini_model']}…", file=sys.stderr)
                    audio = extract_audio(video_path, work / "audio.mp3")
                    all_segments = gemini.transcribe_long_audio(
                        audio, api_key, model=config["gemini_model"], duration=meta.get("duration_seconds") or 0.0,
                        chunk_dir=work / "audio-chunks")
                    used_backend = "gemini"
                    RUN["gemini_audio_tokens"] = getattr(all_segments, "total_tokens", None)
                    covered = (all_segments[-1]["end"] / meta["duration_seconds"]) if all_segments and meta.get("duration_seconds") else None
                    RUN["transcript_coverage"] = round(covered, 2) if covered is not None else None
                    if covered is not None and covered < 0.9:
                        log_event("transcript_short", f"Gemini transcript ends at {covered:.0%} of the audio; "
                                  "it may have been cut off", "warn")
                    elif covered is not None and covered > 1.05:
                        log_event("transcript_overrun", f"Gemini transcript ends at {covered:.0%} of the audio; "
                                  "its timestamps may have drifted", "warn")
                else:
                    all_segments, used_backend = transcribe_video(video_path, work / "audio.mp3", backend=backend, api_key=api_key)
                gaps = getattr(all_segments, "gaps", [])
                if gaps:
                    spans = ", ".join(f"{format_time(g['start'])}-{format_time(g['end']) if g['end'] is not None else 'end'}" for g in gaps)
                    log_event("transcript_gaps", f"{backend} transcription failed for {spans}; the transcript is partial", "warn")
                track_available = True
                transcript_state = "no speech" if not all_segments else "available"
                if used_backend == "gemini":
                    transcript_source = f"gemini audio ({config['gemini_model']})"
                elif used_backend == "whisperx":
                    language = config["whisperx_language"] or "auto (unverified)"
                    transcript_source = f"whisper (whisperx {config['whisperx_model']}, language {language})"
                else:
                    transcript_source = f"whisper ({used_backend})"
            except SystemExit as exc:
                transcript_state = "failed"
                errors.append(f"Transcription failed: {exc}")
                log_event("transcription_failed", f"{backend}: {exc} (no retry, no other engine tried)", "error")
        else:
            transcript_state = f"unavailable: no matching API key for {effective_backend}"
    elif not track_available and effective_backend == "none" and youtube and backend_choice == "auto" and not args.no_whisper:
        transcript_state = "no captions; nothing was uploaded"
        why = ("The caption request itself failed (possibly rate limiting or a blocked network), so captions may exist: "
               "retry later before spending anything. " if dl.get("errors") else "This YouTube video has no captions. ")
        log_event("youtube_no_captions" if not dl.get("errors") else "youtube_caption_fetch_failed",
                  why + "Audio was not sent to Gemini or Whisper automatically.")
    elif not track_available and backend_choice == "none":
        transcript_state = "fallback disabled; no captions available"
    elif not track_available and video_path and not meta.get("has_audio"):
        transcript_state = "no audio stream" if not visual_error else "audio metadata unavailable"


    testing_cues: list[dict] = []
    testing_offsets: list[float] = []
    bank = None
    if args.testing:
        # Cues come from native captions, the only transcript that exists before frames are extracted.
        cue_segments = filter_range(all_segments, start_sec, end_sec) if focused else all_segments
        if not cue_segments:
            print("[watch] testing mode needs a transcript to find cues — "
                  "running with control frames only", file=sys.stderr)
        else:
            testing_offsets = parse_offsets(args.testing_offsets)
            bank = load_bank(BANK_PATH)
            max_cues = max(1, (args.testing_cap - CONTROL_FRAMES) // len(testing_offsets))
            per_round = {t["id"]: t["per_round"] for t in bank["terms"] if t.get("per_round")}
            testing_cues = select_cues(find_cues(cue_segments, bank), max_cues, per_round)
            cue_timestamps = timestamps_for(testing_cues, testing_offsets, full_duration)
            max_frames = len(cue_timestamps) + CONTROL_FRAMES
            budget_cap = max_frames
            print(f"[watch] testing mode: {len(testing_cues)} cues x {len(testing_offsets)} offsets "
                  f"= {len(cue_timestamps)} frames (+{CONTROL_FRAMES} control)", file=sys.stderr)
            fps, target = (auto_fps_focus if focused else auto_fps)(effective_duration, max_frames=budget_cap)

    frames, cue_frames = [], []
    frame_meta = {"engine": "none", "candidate_count": 0, "selected_count": 0, "fallback": False}
    cue_meta = {}
    detail_budget = max_frames
    if video_path and meta.get("has_video", bool(meta.get("width"))):
        try:
            if cue_timestamps:
                cue_frames, cue_meta = extract_at_timestamps(
                    video_path, work / "frames", cue_timestamps, resolution=args.resolution,
                    max_frames=max_frames, start_seconds=start_sec, end_seconds=effective_end or end_sec)
            detail_budget = CONTROL_FRAMES if args.testing else (None if max_frames is None else max_frames - len(cue_frames))
            if detail != "transcript" and detail_budget != 0:
                kwargs = dict(resolution=args.resolution, max_frames=detail_budget,
                              start_seconds=start_sec, end_seconds=effective_end or end_sec, dedup=not args.no_dedup)
                if detail == "efficient":
                    frames, frame_meta = extract_keyframes(video_path, work / "frames", **kwargs)
                else:
                    frames, frame_meta = extract_scene_or_uniform(video_path, work / "frames", fps=fps, target_frames=target, **kwargs)
        except SystemExit as exc:
            visual_error = f"Visual extraction unavailable: {exc}"
            errors.append(visual_error)
    elif video_path and not visual_error and (detail != "transcript" or cue_timestamps):
        visual_error = "No video stream; visual evidence is unavailable."
    testing_files: tuple[Path, Path | None] | None = None
    if cue_frames and args.testing:
        # Cue frames stay out of the frame list (the report points at contact sheets
        # instead); only the control frames are listed for Claude to Read directly.
        # Keyed by the requested time: 0.3.x stamps frames with the real (slightly shifted) timestamp.
        frame_for = {round(f.get("requested_timestamp_seconds", f["timestamp_seconds"]), 2): f["path"] for f in cue_frames}
        build_sheets(testing_cues, frame_for, work / "sheets", testing_offsets, full_duration)
        info_ = dl.get("info") or {}
        testing_files = write_outputs(
            video_id=work.name, source=args.source, work=work, labels_dir=LABELS_DIR,
            cues=testing_cues, offsets=testing_offsets, frame_for=frame_for,
            duration=full_duration, control=frames,
            proposals=propose_terms(cue_segments, bank),
            creator=info_.get("uploader"), title=info_.get("title"), upload_date=info_.get("upload_date"),
        )
    elif cue_frames:
        frames = merge_frames(frames, cue_frames)

    transcript_segments = filter_range(all_segments, start_sec, end_sec) if focused else all_segments
    transcript_text = format_transcript(transcript_segments)
    if transcript_text:
        # Kept beside the frames so a summary can be written later even after downloads are cleared.
        (work / "transcript.txt").write_text(transcript_text, encoding="utf-8")
    if track_available:
        transcript_state = "available" if transcript_segments else ("no speech in selected range" if focused and all_segments else "no speech")
    for error in errors:
        print(f"[watch] {error}", file=sys.stderr)

    info = dl.get("info") or {}

    print()
    print("# watch: video report")
    print()
    print(f"- **Source:** {args.source}")
    print(f"- **Stored in watch-output:** `{display_path(work)}`")
    if video_path:
        print(f"- **Local media:** `{video_path}`")
    if visual_error:
        print(f"- **Visual status:** {visual_error}")
    if errors:
        print("- **Result:** partial evidence" if frames or transcript_segments else "- **Result:** unavailable evidence")
    if info.get("title"):
        print(f"- **Title:** {info['title']}")
    if info.get("uploader"):
        print(f"- **Uploader:** {info['uploader']}")
    print(f"- **Duration:** {format_time(full_duration)} ({full_duration:.1f}s)")
    if focused:
        print(
            f"- **Focus range:** {format_time(effective_start)} → {format_time(effective_end)} "
            f"({effective_duration:.1f}s)"
        )
    if meta.get("width") and meta.get("height"):
        print(f"- **Resolution:** {meta['width']}x{meta['height']} ({meta.get('codec') or 'unknown codec'})")
    range_mode = "focused" if focused else "full"
    print(f"- **Detail:** {detail}")
    detail_count = frame_meta.get("selected_count", 0)
    if detail != "transcript":
        cap_label = "unlimited" if detail_budget is None else str(detail_budget)
        engine = frame_meta.get("engine", "scene")
        fallback = " fallback" if frame_meta.get("fallback") else ""
        deduped = frame_meta.get("deduped_count", 0)
        dedup_note = f", {deduped} near-duplicate{'s' if deduped != 1 else ''} dropped" if deduped else ""
        print(
            f"- **Frames:** {detail_count} selected from {frame_meta.get('candidate_count', detail_count)} "
            f"candidates ({engine}{fallback}{dedup_note}, {range_mode} range, budget {target}, cap {cap_label})"
        )
    elif not cue_frames:
        print("- **Frames:** skipped (transcript detail)")
    if cue_frames:
        dropped = cue_meta.get("dropped_out_of_window", 0)
        drop_note = f", {dropped} dropped outside range" if dropped else ""
        print(
            f"- **Cue frames:** {len(cue_frames)} at transcript-flagged timestamps "
            f"(transcript-cue{drop_note})"
        )
    if frames:
        print(f"- **Frame size:** max {args.resolution}px wide, max 1998px tall")
    if transcript_segments:
        in_range = " in range" if focused else ""
        print(
            f"- **Transcript:** {len(transcript_segments)} segments{in_range} "
            f"(via {transcript_source or 'captions'})"
        )
    else:
        print(f"- **Transcript:** {transcript_state}")
    if gaps:
        print("- **Transcript status:** partial; missing intervals:")
        for gap in gaps:
            end = gap["end"] if gap["end"] is not None else full_duration
            print(f"  - {format_time(gap['start'])} → {format_time(end)}")

    if detail == "token-burner" and len(frames) > 250:
        print()
        print(
            f"> **Warning:** token-burner detail selected {len(frames)} frames. "
            "This may use a large number of image tokens."
        )

    if not focused and full_duration > 600 and detail not in ("transcript", "token-burner"):
        mins = int(full_duration // 60)
        print()
        print(
            f"> **Warning:** This is a {mins}-minute video. Frame coverage is sparse at this length "
            f"under `{detail}` detail — its cap spreads thin across the full clip. For better results, "
            "re-run with `--start HH:MM:SS --end HH:MM:SS` to zoom into a section, or use "
            "`--detail token-burner` to keep every scene-change frame across the whole video."
        )

    if RUN["events"]:
        print()
        print("## Run log")
        print()
        for event in RUN["events"]:
            print(f"- {event['level']} `{event['kind']}`: {event['message']}")
        print(f"_Recorded in `{display_path(LOG_FILE)}`._")

    if testing_files:
        testing_json, label_path = testing_files
        print()
        print("## Testing mode")
        print()
        print(f"{len(testing_cues)} cues x {len(testing_offsets)} offsets "
              f"({', '.join(f'{o:+g}s' for o in testing_offsets)}), one contact sheet per cue — "
              "offsets run left to right. **Read each sheet, then record a verdict per offset "
              "in the label file** (verdicts: new-info | useful | redundant | blank | wrong).")
        print()
        print(f"- Stored in watch-output: `{display_path(work)}` (cue data: `{display_path(testing_json)}`)")
        print(f"- Label file: `{display_path(label_path) if label_path else 'already exists, kept'}`")
        print()
        for cue in testing_cues:
            if cue.get("sheet"):
                print(f"- `{cue['sheet']}` ({cue['cue_id']}, t={format_time(cue['t'])}, "
                      f"{cue['category']}/{cue['term']}: \"{cue['matched']}\")")
        props = propose_terms(cue_segments, bank)
        if props["tickers"] or props["phrases"]:
            print()
            print("Proposed new terms (not added automatically): "
                  + "; ".join(f"{t['ticker']} x{t['mentions']}" for t in props["tickers"][:8])
                  + (" | " if props["tickers"] and props["phrases"] else "")
                  + "; ".join(f"\"{p['phrase']}\" x{p['count']}" for p in props["phrases"][:6]))

    print()
    print("## Frames")
    print()
    if frames:
        print(f"Frames live at: `{work / 'frames'}`")
        print()
        print(
            "**Read each frame path below with the Read tool to view the image.** "
            "Frames are in chronological order; `t=MM:SS` is the absolute timestamp in the source video."
        )
        print()
        for frame in frames:
            print(
                f"- `{frame['path']}` "
                f"(t={format_time(frame['timestamp_seconds'])}, reason={frame.get('reason', 'selected')})"
            )
    else:
        print("_No frames extracted._")

    print()
    print("## Transcript")
    print()
    if transcript_text:
        label = transcript_source or "captions"
        if focused:
            print(f"_Source: {label}. Filtered to {format_time(effective_start)} → {format_time(effective_end)}:_")
        else:
            print(f"_Source: {label}._")
        print()
        print("```")
        print(transcript_text)
        print("```")
    else:
        print(f"_{transcript_state.capitalize()}._")
        if detail == "transcript" and not track_available:
            print("_Re-run with `--detail balanced` for visual evidence, or configure a transcription backend with setup.py._")
    if errors:
        print()
        print("## Unavailable evidence")
        for error in errors:
            print(f"- {error}")

    print()
    print("---")
    print(f"_Stored in watch-output: `{display_path(work)}` — clear with `uv run agent-skills clean`. "
          f"Machine-readable result: `{display_path(work / 'result.json')}`._")

    code = 1 if errors and not frames and not transcript_segments and not track_available else 0
    source_kind = ("gemini-audio" if (transcript_source or "").startswith("gemini audio") else
                   "whisper" if (transcript_source or "").startswith("whisper") else
                   "captions" if transcript_source else "none")
    RUN.update(engine="local", route="youtube" if youtube else "other", detail=detail, work=display_path(work),
               video_id=work.name, duration_s=round(full_duration, 1), frames=len(frames),
               transcript_state=transcript_state, transcript_source=transcript_source, transcript_kind=source_kind,
               caption_status=caption_status, errors=list(errors), testing=bool(args.testing))
    write_result_file(work / "result.json", code)
    if args.result_json:
        write_result_file(Path(args.result_json).expanduser(), code)
    return code


if __name__ == "__main__":
    configure_stdio()
    try:
        code = main()
    except (ConfigError, OSError) as exc:
        RUN.setdefault("events", []).append({"kind": "crash", "level": "error", "message": str(exc)})
        write_run_log(1)
        raise SystemExit(str(exc)) from None
    except SystemExit as exc:
        if exc.code not in (0, None):
            RUN["events"].append({"kind": "exit", "level": "error", "message": str(exc.code)[:500]})
        write_run_log(exc.code)
        raise
    write_run_log(code)
    raise SystemExit(code)

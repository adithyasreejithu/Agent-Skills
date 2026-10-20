"""Testing (training) mode for /watch.

Finds cue moments in the transcript using training/word-bank.json, grabs a
frame at several offsets around each cue, stitches each cue's offsets into one
contact sheet, and writes a label skeleton so frame usefulness can be recorded
and scored (see `agent-skills train report`).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

DEFAULT_OFFSETS = [-2.0, 0.0, 2.0, 4.0, 6.0]
CONTROL_FRAMES = 12          # scene/keyframe frames kept as a baseline to compare cue frames against
MAX_PER_TERM = 3             # stop one chatty term ("chart") from eating the whole cap
SAME_TERM_GAP = 10.0         # seconds; collapses rolling-caption repeats of the same cue
SHEET_TILE_WIDTH = 480

STOPWORDS = set(
    "the a an and or but of to in on at for with is are was were be been it this that these those i you we they "
    "so just like um uh okay right then than not no yes if as by from up out about into over very more some any "
    "my your our their its can could would should will do does did have has had get got going gonna kind of".split()
)


def load_bank(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_offsets(value: str | None) -> list[float]:
    if not value:
        return list(DEFAULT_OFFSETS)
    return [float(tok) for tok in value.split(",") if tok.strip()]


def find_cues(segments: list[dict], bank: dict) -> list[dict]:
    """Return one cue per (term, moment), de-duplicated and capped per term."""
    stop = set(bank.get("stoplist_tickers", []))
    found: list[dict] = []
    for term in bank["terms"]:
        flags = 0 if term.get("case_sensitive") else re.IGNORECASE
        rx = re.compile(term["pattern"], flags)
        limit = term.get("max_per_term", MAX_PER_TERM)
        distinct = term.get("distinct", False)  # one cue per distinct matched value (e.g. per ticker)
        last_t = -1e9
        seen: set[str] = set()
        count = 0
        for seg in segments:
            if count >= limit:
                break
            matches = [m.group(0) for m in rx.finditer(seg["text"])]
            if term.get("use_stoplist"):
                matches = [m for m in matches if m not in stop]
            if distinct:
                matches = [m for m in matches if m not in seen]
                if not matches:
                    continue
                seen.update(matches)
            elif not matches or seg["start"] - last_t < SAME_TERM_GAP:
                continue
            found.append({
                "term": term["id"],
                "category": term["category"],
                "matched": ", ".join(dict.fromkeys(matches)),
                "t": float(seg["start"]),
                "text": seg["text"],
            })
            last_t = seg["start"]
            count += 1
    found.sort(key=lambda c: c["t"])
    return found


def select_cues(cues: list[dict], max_cues: int, per_round: dict[str, int] | None = None) -> list[dict]:
    """Fill the cap round-robin by term: every term gets its first cue(s) before any
    term gets more, so no category is crowded out. `per_round` lets a term take more
    slots per round (tickers do). Result is in time order."""
    per_round = per_round or {}
    by_term: dict[str, list[dict]] = {}
    for cue in cues:
        by_term.setdefault(cue["term"], []).append(cue)
    picked: list[dict] = []
    rounds = max((-(-len(v) // per_round.get(k, 1)) for k, v in by_term.items()), default=0)
    for r in range(rounds):
        for term_id, group in by_term.items():
            n = per_round.get(term_id, 1)
            for cue in group[r * n:(r + 1) * n]:
                if len(picked) < max_cues:
                    picked.append(cue)
    picked.sort(key=lambda c: c["t"])
    for i, cue in enumerate(picked, 1):
        cue["cue_id"] = f"c{i:02d}"
    return picked


def timestamps_for(cues: list[dict], offsets: list[float], duration: float) -> list[float]:
    hi = max(0.0, duration - 0.5) if duration else float("inf")
    ts: set[float] = set()
    for cue in cues:
        for off in offsets:
            ts.add(round(min(max(cue["t"] + off, 0.0), hi), 2))
    return sorted(ts)


def propose_terms(segments: list[dict], bank: dict) -> dict:
    """Suggest terms to add to the bank. Proposals only; nothing is auto-added."""
    stop = set(bank.get("stoplist_tickers", []))
    text = " ".join(s["text"] for s in segments)
    tickers = Counter(t for t in re.findall(r"\b[A-Z]{2,5}\b", text) if t not in stop)
    words = [w for w in re.findall(r"[a-z']+", text.lower())]
    grams = Counter(
        " ".join(words[i:i + 3]) for i in range(len(words) - 2)
        if not all(w in STOPWORDS for w in words[i:i + 3])
        and words[i] not in STOPWORDS and words[i + 2] not in STOPWORDS
    )
    return {
        "tickers": [{"ticker": t, "mentions": n} for t, n in tickers.most_common(15) if n >= 2],
        "phrases": [{"phrase": p, "count": n} for p, n in grams.most_common(15) if n >= 3],
    }


def build_sheets(cues: list[dict], frame_for: dict[float, str], sheets_dir: Path,
                 offsets: list[float], duration: float) -> None:
    """One contact sheet per cue: offsets laid out left to right, in order."""
    if shutil.which("ffmpeg") is None:
        return
    sheets_dir.mkdir(parents=True, exist_ok=True)
    for old in sheets_dir.glob("c*.jpg"):
        old.unlink()
    hi = max(0.0, duration - 0.5) if duration else float("inf")
    for cue in cues:
        paths = []
        for off in offsets:
            key = round(min(max(cue["t"] + off, 0.0), hi), 2)
            p = frame_for.get(key)
            if p:
                paths.append(p)
        if not paths:
            continue
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
        for p in paths:
            cmd += ["-i", p]
        scaled = "".join(f"[{i}:v]scale={SHEET_TILE_WIDTH}:-1[s{i}];" for i in range(len(paths)))
        stack = "".join(f"[s{i}]" for i in range(len(paths)))
        cmd += ["-filter_complex", f"{scaled}{stack}hstack=inputs={len(paths)}",
                "-frames:v", "1", "-q:v", "4", str(sheets_dir / f"{cue['cue_id']}.jpg")]
        if subprocess.run(cmd, capture_output=True, text=True).returncode == 0:
            cue["sheet"] = str(sheets_dir / f"{cue['cue_id']}.jpg")


def write_outputs(*, video_id: str, source: str, work: Path, labels_dir: Path, cues: list[dict],
                  offsets: list[float], frame_for: dict[float, str], duration: float,
                  control: list[dict], proposals: dict, creator: str | None = None,
                  title: str | None = None, upload_date: str | None = None) -> tuple[Path, Path | None]:
    hi = max(0.0, duration - 0.5) if duration else float("inf")
    for cue in cues:
        cue["frames"] = {}
        for off in offsets:
            key = round(min(max(cue["t"] + off, 0.0), hi), 2)
            cue["frames"][f"{off:+g}"] = {"t": key, "path": frame_for.get(key)}

    record = {
        "video_id": video_id, "source": source, "creator": creator, "offsets": offsets,
        "cues": cues, "control": control, "proposed_terms": proposals,
    }
    testing_json = work / "testing.json"
    testing_json.write_text(json.dumps(record, indent=2), encoding="utf-8")

    labels_dir.mkdir(parents=True, exist_ok=True)
    label_path = labels_dir / f"{video_id}.json"
    if label_path.exists():
        return testing_json, None  # never clobber verdicts that were already recorded
    skeleton = {
        "video_id": video_id,
        "creator": creator,
        "title": title,
        "upload_date": upload_date,
        "duration_seconds": round(duration, 1) if duration else None,
        "source": source,
        "verdicts": "new-info | useful | redundant | blank | wrong  (see plan/watch-skill-testing-mode/PLAN.md)",
        "cues": [
            {
                "cue_id": c["cue_id"], "term": c["term"], "category": c["category"], "t": c["t"],
                "heard": c["text"],
                "offsets": {f"{o:+g}": None for o in offsets},
                "best_offset": None,
                "notes": "",
            }
            for c in cues
        ],
        "control": [{"t": f["timestamp_seconds"], "reason": f.get("reason"), "verdict": None} for f in control],
    }
    label_path.write_text(json.dumps(skeleton, indent=2), encoding="utf-8")
    return testing_json, label_path

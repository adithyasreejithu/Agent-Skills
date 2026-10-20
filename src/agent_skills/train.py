"""Testing-mode tooling for /watch: apply labels from a spec file and score terms and offsets."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from agent_skills.gc import REPO_ROOT

LABELS_DIR = REPO_ROOT / "training" / "labels"
GOOD = {"new-info", "useful"}
VERDICTS = {"new-info", "useful", "redundant", "blank", "wrong"}
CODES = {"B": "blank", "W": "wrong", "U": "useful", "R": "redundant", "N": "new-info"}
OFFSETS = ["-2", "+0", "+2", "+4", "+6"]
MIN_SAMPLES_TO_PRUNE = 5
DUP_GAP_SECONDS = 1.5


def _load() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(LABELS_DIR.glob("*.json"))]


def _pct(n: int, d: int) -> str:
    return f"{100 * n / d:.0f}%" if d else "-"


LOG_PATH = REPO_ROOT / "training" / "training-log.md"
SUMMARIES_DIR = REPO_ROOT / "summaries"


def _video_stats(v: dict) -> dict:
    frames = [x for c in v.get("cues", []) for x in c["offsets"].values() if x in VERDICTS]
    ctrl = [c["verdict"] for c in v.get("control", []) if c.get("verdict") in VERDICTS]
    terms: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for c in v.get("cues", []):
        verdicts = [x for x in c["offsets"].values() if x in VERDICTS]
        if verdicts:
            terms[c["term"]][0] += 1
            terms[c["term"]][1] += any(x in GOOD for x in verdicts)
    best: dict[str, int] = defaultdict(int)
    for c in v.get("cues", []):
        if c.get("best_offset"):
            best[c["best_offset"]] += 1
    ranked = sorted(((t, g / n, n) for t, (n, g) in terms.items() if n >= 2), key=lambda x: (-x[1], -x[2]))
    return {
        "cue_frames": len(frames),
        "cue_good": sum(x in GOOD for x in frames),
        "cue_info": sum(x == "new-info" for x in frames),
        "ctrl": len(ctrl),
        "ctrl_good": sum(x in GOOD for x in ctrl),
        "ctrl_info": sum(x == "new-info" for x in ctrl),
        "best": dict(sorted(best.items(), key=lambda kv: float(kv[0]))),
        "top": ranked[:3],
        "bottom": [r for r in ranked[::-1][:3] if r[1] < 0.6],
    }


def write_log() -> Path:
    """Rebuild training/training-log.md from every label file (newest first)."""
    videos = sorted(_load(), key=lambda v: (v.get("trained_at") or "", v.get("upload_date") or ""), reverse=True)
    lines = [
        "# Training log",
        "",
        "One entry per training video, rebuilt from `training/labels/*.json` every time `agent-skills train label` runs.",
        "Do not edit by hand. Scores are per frame (useful or new-info = good); control is the scene-detection baseline.",
        "",
    ]
    for v in videos:
        s = _video_stats(v)
        if not s["cue_frames"]:
            continue
        dur = v.get("duration_seconds")
        dur_txt = f"{int(dur // 60)}:{int(dur % 60):02d}" if dur else "unknown length"
        summ = sorted(SUMMARIES_DIR.glob(f"{v['video_id']}-*.md")) if SUMMARIES_DIR.is_dir() else []
        offsets = ", ".join(f"{o}s" for o in (v["cues"][0]["offsets"].keys() if v.get("cues") else []))
        lines += [
            f"## {v.get('trained_at', 'undated')} | {v['video_id']} | {v.get('title') or 'untitled'}",
            "",
            f"- Creator: {v.get('creator') or 'unknown'}",
            f"- Source: {v.get('source', '')} ({dur_txt})",
            f"- Run: {len(v['cues'])} cues, offsets {offsets}",
            f"- Cue frames: {_pct(s['cue_good'], s['cue_frames'])} good, {_pct(s['cue_info'], s['cue_frames'])} new-info "
            f"({s['cue_frames']} frames)",
            f"- Control: {_pct(s['ctrl_good'], s['ctrl'])} good, {_pct(s['ctrl_info'], s['ctrl'])} new-info ({s['ctrl']} frames)"
            if s["ctrl"] else "- Control: not labeled",
            f"- Best offsets picked: {', '.join(f'{k}s x{n}' for k, n in s['best'].items()) or 'none'}",
            "- Strongest terms: " + (", ".join(f"{t} ({_pct(round(r * n), n)} of {n})" for t, r, n in s["top"]) or "n/a"),
            "- Weakest terms: " + (", ".join(f"{t} ({_pct(round(r * n), n)} of {n})" for t, r, n in s["bottom"]) or "none under 60%"),
            f"- Summary: {summ[0].relative_to(REPO_ROOT).as_posix() if summ else 'not written yet'}",
            "",
        ]
    LOG_PATH.write_text("\n".join(lines), encoding="utf-8")
    return LOG_PATH


def apply_labels(spec_path: str) -> int:
    """Write verdicts from a spec file into training/labels/<video>.json.

    Spec: {"video": id, "auto_dup": bool, "note": str,
           "cues": {"c01": ["BUUUU", best_offset_or_null, "note"], ...},
           "control": "BUNR...", "control_note": str}
    Codes: B blank, W wrong, U useful, R redundant, N new-info. One letter per offset.
    """
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    path = LABELS_DIR / f"{spec['video']}.json"
    data = json.loads(path.read_text(encoding="utf-8"))

    missing = {c["cue_id"] for c in data["cues"]} - set(spec["cues"])
    if missing:
        raise SystemExit(f"spec is missing cues: {sorted(missing)}")
    offsets = list(data["cues"][0]["offsets"].keys()) if data["cues"] else OFFSETS
    for cue in data["cues"]:
        codes, best, note = spec["cues"][cue["cue_id"]]
        if len(codes) != len(offsets):
            raise SystemExit(f"{cue['cue_id']}: expected {len(offsets)} codes, got {len(codes)}")
        cue["offsets"] = {o: CODES[k] for o, k in zip(offsets, codes)}
        cue["best_offset"] = best
        cue["notes"] = note

    if spec.get("auto_dup"):
        prev = None
        for cue in data["cues"]:
            if prev is not None and cue["t"] - prev["t"] <= DUP_GAP_SECONDS:
                cue["offsets"] = {o: ("redundant" if x in GOOD else x) for o, x in cue["offsets"].items()}
                cue["best_offset"] = None
                cue["notes"] = f"{cue['notes']} [auto: within {DUP_GAP_SECONDS}s of {prev['cue_id']}, marked redundant]".strip()
            prev = cue

    if spec.get("control"):
        if len(spec["control"]) != len(data["control"]):
            raise SystemExit(f"control: expected {len(data['control'])} codes, got {len(spec['control'])}")
        for item, k in zip(data["control"], spec["control"]):
            item["verdict"] = CODES[k]
        data["control_notes"] = spec.get("control_note", "")

    data["labeling_notes"] = spec.get("note", data.get("labeling_notes", ""))
    data.setdefault("trained_at", date.today().isoformat())
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"{spec['video']}: labeled {len(data['cues'])} cues"
          + (f" and {len(data['control'])} control frames" if spec.get("control") else ""))
    print(f"training log updated: {write_log().relative_to(REPO_ROOT).as_posix()}")
    return 0


def report(creator: str | None = None) -> int:
    videos = _load()
    if creator:
        videos = [v for v in videos if (v.get("creator") or "").lower() == creator.lower()]
        if not videos:
            raise SystemExit(f"no labeled videos for creator: {creator}")

    term = defaultdict(lambda: {"cues": 0, "good": 0, "info": 0, "cat": ""})
    by_creator = defaultdict(lambda: defaultdict(lambda: {"cues": 0, "good": 0, "info": 0}))
    offset = defaultdict(lambda: {"labeled": 0, "good": 0, "best": 0})
    control = {"labeled": 0, "good": 0}
    labeled_videos = 0
    creators: dict[str, int] = defaultdict(int)

    for v in videos:
        any_labeled = False
        who = v.get("creator") or "unknown"
        for cue in v.get("cues", []):
            verdicts = {o: x for o, x in cue["offsets"].items() if x in VERDICTS}
            if not verdicts:
                continue
            any_labeled = True
            good = any(x in GOOD for x in verdicts.values())
            info = any(x == "new-info" for x in verdicts.values())
            for bucket in (term[cue["term"]], by_creator[cue["term"]][who]):
                bucket["cues"] += 1
                bucket["good"] += good
                bucket["info"] += info
            term[cue["term"]]["cat"] = cue["category"]
            for o, x in verdicts.items():
                offset[o]["labeled"] += 1
                offset[o]["good"] += x in GOOD
            if cue.get("best_offset") in cue["offsets"]:
                offset[cue["best_offset"]]["best"] += 1
        for c in v.get("control", []):
            if c.get("verdict") in VERDICTS:
                any_labeled = True
                control["labeled"] += 1
                control["good"] += c["verdict"] in GOOD
        if any_labeled:
            labeled_videos += 1
            creators[who] += 1

    scope = f" for creator '{creator}'" if creator else ""
    print(f"{labeled_videos} labeled video(s){scope} in {LABELS_DIR}")
    print("creators: " + ", ".join(f"{k} ({n})" for k, n in sorted(creators.items())) + "\n")
    if not labeled_videos:
        print("No verdicts recorded yet. Fill in training/labels/<video-id>.json first.")
        return 0

    print("TERMS (hit = at least one offset useful; info = at least one offset showed new info)")
    print(f"  {'term':<22}{'category':<12}{'cues':>5}{'hit':>6}{'info':>6}")
    for name, t in sorted(term.items(), key=lambda kv: (-kv[1]["good"] / kv[1]["cues"], -kv[1]["cues"])):
        flag = "  <- prune?" if t["cues"] >= MIN_SAMPLES_TO_PRUNE and t["good"] / t["cues"] < 0.3 else ""
        print(f"  {name:<22}{t['cat']:<12}{t['cues']:>5}{_pct(t['good'], t['cues']):>6}{_pct(t['info'], t['cues']):>6}{flag}")

    if not creator and len(creators) > 1:
        names = sorted(creators)
        print("\nTERMS BY CREATOR (cues, hit%) — terms with 3+ cues overall")
        print(f"  {'term':<22}" + "".join(f"{n[:22]:>26}" for n in names))
        for name, t in sorted(term.items(), key=lambda kv: -kv[1]["cues"]):
            if t["cues"] < 3:
                continue
            cells = []
            for n in names:
                b = by_creator[name].get(n)
                cells.append(f"{b['cues']} cues, {_pct(b['good'], b['cues'])}" if b else "-")
            print(f"  {name:<22}" + "".join(f"{c:>26}" for c in cells))

    print("\nOFFSETS (good = useful or new-info; best = picked as the best offset for its cue)")
    print(f"  {'offset':<8}{'frames':>7}{'good':>7}{'best':>6}")
    for o in sorted(offset, key=float):
        s = offset[o]
        print(f"  {o + 's':<8}{s['labeled']:>7}{_pct(s['good'], s['labeled']):>7}{s['best']:>6}")

    print(f"\nCONTROL (scene/keyframe baseline): {_pct(control['good'], control['labeled'])} good "
          f"of {control['labeled']} frames")
    return 0

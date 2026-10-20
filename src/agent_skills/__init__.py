import argparse

from agent_skills.gc import clean
from agent_skills.train import apply_labels, report, write_log


def main() -> int:
    ap = argparse.ArgumentParser(prog="agent-skills")
    sub = ap.add_subparsers(dest="command", required=True)

    c = sub.add_parser("clean", help="Clear frames/downloads from watch-output (no flags = show sizes only)")
    c.add_argument("--frames", action="store_true", help="remove extracted frames, cue frames and contact sheets")
    c.add_argument("--downloads", action="store_true", help="remove downloaded video, audio, captions")
    c.add_argument("--all", action="store_true", help="--frames and --downloads")
    c.add_argument("--video", help="limit to one video folder (the id under watch-output/)")
    c.add_argument("--temp", action="store_true", help="also remove legacy watch-* folders in system temp")
    c.add_argument("--dry-run", action="store_true", help="list what would be removed, delete nothing")

    t = sub.add_parser("train", help="Testing-mode tooling")
    t_sub = t.add_subparsers(dest="train_command", required=True)
    r = t_sub.add_parser("report", help="Score terms and offsets from training/labels/*.json")
    r.add_argument("--creator", help="only count videos from this creator (training only)")
    t_sub.add_parser("log", help="Rebuild training/training-log.md from the label files")
    lb = t_sub.add_parser("label", help="Apply verdicts from a spec file (e.g. training/specs/<video-id>.json)")
    lb.add_argument("spec", help="path to the spec JSON")

    args = ap.parse_args()
    if args.command == "train":
        if args.train_command == "label":
            return apply_labels(args.spec)
        if args.train_command == "log":
            print(write_log())
            return 0
        return report(args.creator)
    return clean(
        frames=args.frames or args.all,
        downloads=args.downloads or args.all,
        video=args.video,
        temp=args.temp,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())

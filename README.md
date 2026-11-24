# Agent-Skills

**An autonomous research pipeline built from Claude Code skills.** It watches finance YouTube channels and Instagram reels on a schedule, turns each video into a validated, source-linked note, and writes a daily brief that compares what every creator said today with what they said last time.

No database, no web framework, no babysitting. Just folders, small Python modules, and AI agents with their outputs checked by code.

> Built to answer a real question: *"I can't watch 15 hours of market commentary a day, so how do I keep up without trusting a summary I can't verify?"*

---

## What it does

```
 YouTube channels ──► RSS poll ──► filters ──► queue ──► watch skill ──► Claude agent ──► note
 Instagram reels ──► headless browser ─────────┘          (frames +       (claude -p)       │
 Links you paste ──► priority lane ────────────┘           transcript)                      ▼
                                                                         daily brief ◄── validation
                                                                                             │
                                                                      method & tool registry ┘
```

1. **Discover.** Polls creators' feeds, drops what doesn't match, and queues the rest. Links you paste in jump the queue.
2. **Watch.** Downloads each video, pulls captions (or transcribes audio with Gemini as a fallback), and extracts frames at the moments that matter.
3. **Write.** A headless Claude agent (`claude -p`) produces a structured note: calls, levels, timestamps and evidence, with every claim traceable to the video.
4. **Brief.** Each morning, a short read (under 180 words) and a long read, comparing every creator to their own previous video.
5. **Learn.** An analysis stage extracts the *methods* and *tools* creators use into a growing registry of generated reference pages.

The result is a repo that fills itself: [`research/summaries/`](research/summaries) (per-video notes), [`research/briefs/`](research/briefs) (daily briefs), and [`research/analysis/`](research/analysis) (methods and tools registry plus backtests).

---

## What makes it interesting (engineering highlights)

| Problem | How it's solved |
|---|---|
| **LLM output you can't trust** | Every brief is validated by plain code: bullet count, word limit, required sections, and a check that *every number in the short read appears in a source note*. A failing draft is retried once with the specific problems listed, and then falls back to a mechanical brief rather than shipping bad output. |
| **Choosing the right model for each job** | Code does bookkeeping, Gemini does audio transcription, and Claude does reading and writing. Each stage declares who does the work, and the split is documented in [`docs/ingest-pipeline.md`](docs/ingest-pipeline.md). |
| **Reliability without infrastructure** | A folder-based queue (`pending → processing → done/failed`) with locking, retry on transient errors, permanent-failure handling, time budgets (`--budget-min`) and priority ordering. It is inspectable with `ls` and recoverable by moving a file. |
| **Cost control** | Token use and dollar cost are logged per brief to `_cost.jsonl`. Reels are summarized in batches (about $0.024 a reel in the first measured run), and `--dry-run` prints the exact prompt without spending anything. |
| **Teaching the system to see** | A *testing mode* labels extracted frames useful, redundant or blank, then scores which transcript cues predict a good frame and at what time offset. It prunes weak cues automatically. See [`training/`](training). |
| **Scraping politely** | The Instagram collector paces itself, never stores credentials (the login is done by hand in a persistent browser profile), and stops with a 48-hour cooldown at the first challenge page, 429 or "try again later". |
| **Testing AI claims against data** | Chart-reading claims from creators are backtested against price history with no lookahead (indicators only ever see bars up to the as-of date). Results are reported as found, including the unflattering ones. |
| **Planning before building** | Each major feature has a written plan with status, findings and what live testing changed. See [`plan/`](plan). |

---

## Tech stack

**Python 3.12** · **uv** · **Claude Code skills** and headless agents (`claude -p`) · **Gemini API** (audio transcription) · **yt-dlp** · **ffmpeg** · **Playwright** · **Mermaid** (architecture docs) · standard-library-first code (the backtester has zero third-party dependencies)

About 9,000 lines of Python and 190 test functions covering the queue, config, feed parsing, polling, processing, scheduling, briefs, analysis, reels and the watch skill's transcript and routing logic.

---

## The two skills

### `/watch`, the evidence gatherer
Downloads a video, extracts auto-scaled frames, and gets a timestamped transcript from captions first, with local WhisperX, cloud Whisper or Gemini audio as fallbacks. Routing is privacy-aware: a YouTube video without captions never uploads audio unless you allow it. Every run writes a structured `result.json` and a JSONL run log so callers read data instead of scraping a report.

> Based on the open-source [`claude-video`](https://github.com/bradautomates/claude-video) skill (MIT). Everything I changed or added is tracked in [`PATCHES.md`](.agents/skills/watch/PATCHES.md), so the next upstream upgrade is a checklist rather than a merge fight.

### `/ingest`, the pipeline
The orchestrator: sources, queue, processing, briefs, analysis and Instagram reels. One entry point:

```bash
python .agents/skills/ingest/scripts/run.py <command>
```

| Command | What it does |
|---|---|
| `source add @handle` | Follow a channel |
| `poll` | Find new videos and queue them (first poll skips the backlog) |
| `add URL --now` | Queue a link yourself, ahead of everything else |
| `process --budget-min 30` | Watch and write notes, best first, within a time budget |
| `brief` | Build the day's morning brief |
| `tick` | A scheduled run: poll, then process, then brief |
| `reels ...` | The Instagram reels pipeline |

---

## A look at the output

A real short read from the daily brief:

> - **Mood:** Ryan is bullish. He thinks a Christmas rally has started ahead of the Anthropic IPO, but with VXN at 27, still in his "fear zone", he is hedging and raising cash.
> - **Buying:** He added TQQQ on yesterday's dip (average ~52). He opened a QQQ 620/550 bear put spread as a hedge, ~65 days out, for ~$3,300.
> - **Levels:** QQQ ~690, resistance at 700, possible dip to 680-675. 10Y ~5%, VIX in the 17s, VXN 27.

Full example: [`research/briefs/2026-11-12.md`](research/briefs/2026-11-12.md). Browse the generated registry in [`research/analysis/methods.md`](research/analysis/methods.md).

---

## Run it yourself

**Requirements:** Python 3.12+, [uv](https://docs.astral.sh/uv/), `ffmpeg`, the [Claude Code](https://claude.com/claude-code) CLI, and a free [Gemini API key](https://aistudio.google.com/apikey).

```bash
git clone https://github.com/adithyasreejithu/Agent-Skills.git
cd Agent-Skills
uv sync

# first-run check for binaries and keys (put your Gemini key in ~/.config/watch/.env)
python .agents/skills/watch/scripts/setup.py --json

# create the queue, follow a channel, and do a dry run that prints the prompt without calling anything
python .agents/skills/ingest/scripts/run.py init
python .agents/skills/ingest/scripts/run.py source add @somechannel
python .agents/skills/ingest/scripts/run.py poll --dry-run
python .agents/skills/ingest/scripts/run.py process --dry-run

# run the tests
python -m unittest discover -s tests/ingest -p "test_*.py"
python -m unittest discover -s tests/watch -p "test_*.py"
```

Paths and behavior are configured in [`ingest.env`](ingest.env). No secrets live in the repo.

---

## Repository map

```
.agents/skills/watch/    evidence gatherer: download, captions, frames, transcription
.agents/skills/ingest/   queue, polling, processing, briefs, analysis, Instagram reels
src/agent_skills/        CLI: training scorer and watch-output garbage collector
tests/                   unit tests for both skills
plan/                    design docs: goals, status, findings, what changed after live testing
docs/                    architecture diagrams (who does what: Claude, Google or plain code)
training/                frame labels and the learned cue word bank
research/                generated notes, briefs, method registry and backtests
queue/                   channel list (runtime state is gitignored)
```

---

## Things I'd point to in an interview

- **Treating the LLM as an untrusted component.** Output goes through validators, retries carry the specific failures, and there is a deterministic fallback.
- **Measuring instead of guessing.** Frame-selection cues are scored against human labels, and chart-reading claims are backtested.
- **Honest write-ups.** The plans record what failed. For example, logged-out Instagram only exposes 12 reels per profile, which broke the planned 30-day backfill and changed the design.
- **Boring, durable infrastructure.** Folders, locks and JSON files that a human can inspect and repair.
- **Scoped permissions.** The agent's allowed commands are an explicit allowlist in [`.claude/settings.json`](.claude/settings.json).

---

## Disclaimer

This is an engineering and research project. The notes and briefs are machine-generated summaries of other people's public videos, may contain errors, and are **not financial advice**. Creators' views belong to them; follow the terms of any platform you point this at.

## License

The `watch` skill derives from an MIT-licensed upstream project. See its `SKILL.md` for details.

## Author

**Adithya Sreejithu**: [github.com/adithyasreejithu](https://github.com/adithyasreejithu)

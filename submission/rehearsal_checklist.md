# Rehearsal Checklist

Complete this checklist before the classroom presentation.

## Before rehearsal

- [ ] Run `python -m pytest -q`.
- [ ] Run success command:
  `python agent/qq_demo_bridge.py --message "/hypothesis inputs/papers/success_demo.pdf"`
- [ ] Run boundary command:
  `python agent/qq_demo_bridge.py --message "/hypothesis inputs/papers/boundary_demo.pdf --bad"`
- [ ] Confirm each run prints a run directory and Green/Yellow/Red counts.
- [ ] Confirm the latest run contains all nine core artifacts.
- [ ] Confirm prepared canonical evidence exists under `submission/evidence/`.
- [ ] Run `python scripts/live_pdf_preflight.py inputs/papers/success_demo.pdf`.
- [ ] Run one teacher-style command with `--live-demo`.
- [ ] Stop the old `qqbot-agent` Python bot if it is running.
- [ ] Start real QQ bot: `python qqbot\main.py --debug --port 3002`.
- [ ] Confirm NapCat reverse WebSocket connects to `ws://127.0.0.1:3002`.
- [ ] Send `/hypothesis inputs/papers/success_demo.pdf` in QQ and receive a run summary.
- [ ] Open `submission/poster/poster_120x80.pdf`.

## Evidence to capture

- [ ] Real QQ/WeChat screenshot showing the command.
- [ ] Real QQ/WeChat screenshot showing the result summary.
- [ ] Screen recording showing the interaction and generated artifact folder.
- [ ] Screenshot of `citation_verification.csv` for success case.
- [ ] Screenshot of `citation_verification.csv` for boundary case.
- [ ] Screenshot of `tool_calls.jsonl`.
- [ ] Screenshot of `retrieved_literature.jsonl`.

Store real screenshots in `submission/screenshots/`.
Store real recordings in `submission/recordings/`.

## Rehearsal record

- Rehearsal date:
- Success run directory:
- Boundary run directory:
- Green/Yellow/Red counts for success:
- Green/Yellow/Red counts for boundary:
- Live API issues observed:
- Backup files verified:
- Total demo time:

## No-fabrication rule

Do not fill `screenshots/` or `recordings/` with mocked chat images. If real
QQ/WeChat capture is unavailable, present the terminal QQ command adapter
honestly and rely on logs, reproducibility, and screen recording of the local
adapter.

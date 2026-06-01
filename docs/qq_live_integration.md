# QQ Live Integration

This project now includes a real NapCat/OneBot QQ bot entrypoint, modeled after
`C:\Users\99303\git\qqbot-agent`, but scoped to the hypothesis citation agent.

## What it does

The QQ bot listens for OneBot v11 reverse WebSocket events from NapCat and
responds to these commands:

```text
/help
/preflight inputs/papers/teacher_live.pdf
/hypothesis inputs/papers/success_demo.pdf
/hypothesis inputs/papers/boundary_demo.pdf --bad
/hypothesis inputs/papers/teacher_live.pdf --live
```

It runs the local workflow and replies with:

- run directory;
- Green / Yellow / Red counts;
- paths to `tool_calls.jsonl`, `retrieved_literature.jsonl`,
  `citation_verification.csv`, `evidence_chain.csv`, and `final_report.md`;
- a short report excerpt.

It does not require a DeepSeek or OpenAI API key.

## Start the bot

From the project root:

```powershell
cd C:\Users\99303\git\llm_hypothesis_citation_agent
pip install -r requirements.txt
python qqbot\main.py --debug --port 3002
```

Or use:

```powershell
start_qqbot.bat
```

`start_qqbot.bat` starts this bot and tries to start NapCat from:

```text
C:\Users\99303\git\qqbot-agent\napcat\napcat_app
```

If that path is unavailable, start NapCat manually from `qqbot-agent`.

## Configure NapCat

In NapCat WebUI, add or enable a OneBot v11 reverse WebSocket connection:

```text
ws://127.0.0.1:3002
```

This matches the already configured `qqbot-agent` NapCat files:

```text
C:\Users\99303\git\qqbot-agent\napcat\napcat_app\napcat\config\onebot11_993030293.json
C:\Users\99303\git\qqbot-agent\napcat\napcat_app\napcat\config\onebot11_3170522680.json
```

Do not run the old `qqbot-agent` Python bot and this project bot at the same
time, because both would try to listen on port `3002`. Keep NapCat running, but
close the old bot process before starting this one.

## QQ demo commands

Send these from another QQ account to the bot account.

Success case:

```text
/hypothesis inputs/papers/success_demo.pdf
```

Boundary case:

```text
/hypothesis inputs/papers/boundary_demo.pdf --bad
```

Teacher-supplied PDF:

```text
/preflight inputs/papers/teacher_live.pdf
/hypothesis inputs/papers/teacher_live.pdf --live
```

If the teacher sends a PDF file through QQ, the bot will try a best-effort
preflight if NapCat exposes a local file path. The more reliable live-demo
procedure is still to save the PDF under `inputs/papers/` and send its path.

## Evidence to capture

For grading, capture real screenshots or screen recordings showing:

- QQ command sent by the user;
- bot reply with run directory and Green / Yellow / Red counts;
- generated run directory on disk;
- `tool_calls.jsonl`;
- `retrieved_literature.jsonl`;
- `citation_verification.csv`;
- `evidence_chain.csv`;
- `final_report.md`.

Store them under:

```text
submission/screenshots/
submission/recordings/
```

Do not fabricate chat screenshots or logs.

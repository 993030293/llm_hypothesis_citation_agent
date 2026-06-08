# LLM Hypothesis Citation Agent

This workspace is for the updated LLM course Project A direction.

## Goal

Add a verifiable citation evidence-chain audit module to the official
DeepScientist research agent. DeepScientist/Claude Code produces research
ideas and citation-backed claims; this repository verifies whether those
citations exist, match public metadata, and support the generated claims.

## Chosen Project-A framing

This repository now uses the **official DeepScientist repository as the base
research-agent system** and attaches this project as a citation evidence-chain
audit extension. The base research-agent pattern is:

```text
read papers -> find research gaps -> generate hypotheses -> write a report
```

The added course module is the **Citation Evidence Chain Tracking Module**. It
is inserted after hypothesis generation and before final report writing:

```text
Official DeepScientist hypothesis generation
-> citation-backed claims
-> citation evidence-chain audit
-> Green / Yellow / Red audit table
```

See `docs/official_deepscientist_extension_plan.md` and
`docs/deepscientist_integration.md` for the module boundary and adapter.

## Required output behavior

- Green: the cited literature exists and supports the claim.
- Yellow: the cited literature exists but support is uncertain or only partial.
- Red: the citation is wrong, missing, or does not support the claim.

## Submission Guide

For the course submission mapping of source code, configuration, startup
commands, test data, logs, presentation assets, and DeepScientist modifications,
see `submission/github_submission_readme.md`.

## Planned structure

- `agent/`: PDF parsing, literature search, hypothesis generation, citation
  verification, DeepScientist adapter, and report writing code.
- `inputs/papers/`: local PDFs used for testing and classroom demonstration.
- `outputs/`: generated run directories, evidence tables, reports, and logs.
- `docs/`: design notes, presentation runbook, and grading alignment.
- `tests/`: smoke tests and citation-checking test cases.
- `submission/`: final course report, evidence PDF, screenshots, and zip package.

## Relationship to finalproj

The existing `finalproj` repository remains useful as a source of evidence-chain
tracking patterns. This new workspace focuses on the revised requirement:
article PDF input, literature lookup, hypothesis generation, and citation
verification with red/yellow/green labels.

## Path 2 Quick Start: Official DeepScientist + Claude Code

This is the primary project route. The local deterministic workflow is retained
only as legacy fallback; classroom demonstration and teammate reproduction
should use this official DeepScientist path.

Prerequisites:

- Claude Code is installed and logged in on the local machine.
- Node.js and npm are available.

Prepare the path-2 environment:

```powershell
python scripts/setup_path2_claude.py --force-skill
```

This script:

- checks `claude --version`;
- verifies Claude Code headless mode with a `HELLO` prompt;
- installs `@researai/deepscientist` globally if `ds` is missing;
- patches the local DeepScientist Claude startup probe for Windows-compatible
  `--tools=` handling when needed;
- installs this repository's DeepScientist skills:
  `citation-hypothesis-claims` for PDF -> idea -> claims generation, and
  `citation-evidence-audit` for the downstream audit contract;
- runs `ds doctor --runner claude`.

Start official DeepScientist with Claude Code for the live system:

```powershell
ds --runner claude
```

Run a path-2 smoke test:

```powershell
python scripts/path2_smoke_test.py
```

The smoke test creates an official DeepScientist quest directory under
`~/DeepScientist/quests/`, uses Claude Code to produce
`citation_audit_claims.json`, then runs:

```powershell
python scripts/audit_deepscientist_output.py --quest-root "<quest_root>"
```

Expected audit outputs:

- `citation_verification.csv`
- `evidence_chain.csv`
- `evidence_chain.md`
- `deepscientist_audit_summary.md`
- `tool_calls.jsonl`
- `evidence_items.jsonl`

For the current official DeepScientist workflow, run the automated case runner.
It creates or reuses a quest, asks DeepScientist/Claude to generate research
ideas and `citation_audit_claims.json`, then runs the deterministic audit:

```powershell
python scripts/run_official_ds_case.py `
  --case-id ai_rag_demo `
  --pdf-path-or-url https://arxiv.org/pdf/2005.11401
```

## DeepSeek LLM Agent WorkFlow (主推路线)

该路线实现了完全由 LLM (DeepSeek) 驱动的 Function Calling 代理。模型主动阅读 PDF，利用工具搜索文献，生成假说并强制附带 Evidence ID 证据链，最终给出绿/黄/红分析。这完美契合 Project A 的高分要求（自主工具调用、证据链溯源、非 Prompt 限定）。

**准备环境：**
```powershell
pip install -r requirements.txt
$env:DEEPSEEK_API_KEY="你的_DeepSeek_API_Key"
```

运行基础测试流程并审计引文证据：

```powershell
python agent/workflow.py --pdf inputs/papers/success_demo.pdf --task "Generate a new research hypothesis and verify citations"
```

如果想要看到边界测试（幻觉/错误引用被拦截变红）：

```powershell
python agent/workflow.py --pdf inputs/papers/success_demo.pdf --inject-bad-citation
```

系统将主动调用 `agent/literature_search.py` 接口查询真实 DOI 并输出验证表格及 Markdown 报告，展示 `Evidence-ID` 锚点和绿/黄/红分级结论。

The default live-demo providers are Crossref and OpenAlex. Optional providers
can be enabled with `--providers "crossref,openalex,semantic_scholar,arxiv"`.
The workflow now performs two-stage retrieval by default: initial PDF-derived
queries, then follow-up method/application/limitation/review queries derived
from the first retrieval pass. Use `--disable-followup` for a minimal run.

Each run writes a complete artifact set to `outputs/runs/<timestamp>/`:

- `input_task.md`
- `paper_summary.json`
- `search_queries.json`
- `retrieved_literature.jsonl`
- `generated_hypothesis.md`
- `citation_verification.csv`
- `evidence_chain.csv`
- `evidence_chain.md`
- `final_report.md`
- `tool_calls.jsonl`
- `evidence_items.jsonl`

For a boundary demonstration with one explicitly invalid citation:

```powershell
python agent/workflow.py --pdf inputs/papers/boundary_demo.pdf --task "Generate a boundary-case hypothesis and verify citations" --inject-bad-citation
```

## QQ/WeChat 交互演示 (QQ Bot)

启动 QQ 机器人，接收科研任务：

```powershell
python qqbot/main.py
```

在 QQ 群内发送指令：
`/hypothesis inputs/papers/success_demo.pdf`
`/hypothesis inputs/papers/success_demo.pdf --bad`

机器人将实时拉取 DeepSeek ，完成工具检索和事实核查，发送详细包含“标红/标黄/标绿”以及 Evidence ID 表格的科研审计报告，直观展示证据链溯源前后的体验对比。

### 关于“三色判定”设计
- 🟢 **绿色**：已有材料明确支持的结论
- 🟡 **黄色**：由模型合理推断但未被直接证明的内容
- 🔴 **红色**：证据不足、幻觉、或引用错误的边界案例

DeepScientist module adapter:

```powershell
python agent/deepscientist_adapter.py --claims outputs/runs/<run_id>/generated_claims.json
```

This audits an existing DeepScientist-style or official DeepScientist `generated_claims.json` file and
writes standalone module output under `outputs/deepscientist_audits/<timestamp>/`.

Official DeepScientist extension workflow:

```powershell
python scripts/install_deepscientist_extension.py --deepscientist-root C:\Users\99303\git\DeepScientist-official
python scripts/audit_deepscientist_output.py --claims outputs/runs/<run_id>/generated_claims.json
```

For a real official DeepScientist quest, place `citation_audit_claims.json` in
the quest directory and run:

```powershell
python scripts/audit_deepscientist_output.py --quest-root "C:\path\to\deepscientist\quest"
```

## Real QQ / NapCat interaction

The project also includes a NapCat/OneBot QQ bot entrypoint:

```powershell
python qqbot\main.py --debug --port 3002
```

Configure NapCat reverse WebSocket to:

```text
ws://127.0.0.1:3002
```

This reuses the already configured NapCat setup in
`C:\Users\99303\git\qqbot-agent`. Do not run the old `qqbot-agent` Python bot
at the same time, because it also listens on port `3002`.

Then send QQ messages such as:

```text
/hypothesis inputs/papers/success_demo.pdf
/hypothesis inputs/papers/boundary_demo.pdf --bad
/preflight inputs/papers/teacher_live.pdf
/hypothesis inputs/papers/teacher_live.pdf --live
```

See `docs/qq_live_integration.md` for the full setup and screenshot checklist.

## Stress audit

Generate stress-test PDF cases:

```powershell
python scripts/create_stress_cases.py
```

Run the non-lightweight batch audit with independent online citation review:

```powershell
python scripts/stress_audit.py --case-dir inputs/stress_cases --providers "crossref,openalex,semantic_scholar,arxiv"
```

Outputs are written to `outputs/stress_audits/<timestamp>/` and copied to
`submission/stress_audit/` by default. See `docs/stress_audit.md`.

## Teacher-supplied live PDF

If the teacher provides a new PDF during the presentation, preflight it before
running the full workflow:

```powershell
python scripts/live_pdf_preflight.py "C:\path\to\teacher.pdf"
```

If the preflight says `ready` or `usable_with_caution`, run the time-bounded
live mode:

```powershell
python agent/workflow.py --pdf "C:\path\to\teacher.pdf" --task "Teacher-supplied live PDF: generate a research hypothesis and verify citations" --live-demo
```

The QQ-style adapter also supports live mode:

```powershell
python agent/qq_demo_bridge.py --message "/hypothesis C:\path\to\teacher.pdf --live"
```

If the preflight says `risky`, explain that the PDF is likely scanned or has too
little extractable text, then show the prepared logs in `submission/evidence/`.
The full two-stage retrieval workflow remains available for prepared demo runs;
`--live-demo` intentionally prioritizes speed and predictable classroom timing.

## Submission package

Course-facing evidence is organized under `submission/`:

- `submission/evidence/success_case/`: canonical successful run artifacts.
- `submission/evidence/boundary_case/`: canonical boundary run artifacts.
- `submission/reproducibility.md`: commands and validation steps.
- `submission/grading_checklist.md`: rubric-to-evidence mapping.
- `submission/demo_script.md`: 10-minute demo flow and backup plan.
- `submission/poster/poster_120x80.pdf`: printable 120 cm x 80 cm poster.
- `docs/official_deepscientist_extension_plan.md`: official DeepScientist
  integration plan and commands.
- `docs/qq_live_integration.md`: real NapCat/OneBot QQ setup.
- `docs/stress_audit.md`: non-lightweight stress audit and online review guide.

Real QQ/WeChat screenshots and recordings must be captured before final
presentation and stored in `submission/screenshots/` and
`submission/recordings/`. Do not fabricate chat evidence or retrieval logs.

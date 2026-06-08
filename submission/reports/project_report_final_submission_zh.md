# DeepScientist Citation Audit Agent 项目报告

课程：《大语言模型：从原理到应用》期末 Project
方向：Project A，科研智能体功能扩展
基础系统：Official DeepScientist + Claude Code
小组成员：郭耀远、齐佳男、刘炎男

## 摘要

本项目选择 Project A 中的“科研智能体功能扩展”方向，以 official DeepScientist 作为基础科研 Agent。DeepScientist 负责从输入 PDF 中理解论文内容、查找相关文献并生成 research idea / hypothesis。本项目在 hypothesis 生成之后、最终报告写作之前，增加一个可验证的 Citation Evidence Chain Tracking Module，用于检查生成 idea 所参考的文献是否存在错误，并输出 Green / Yellow / Red 引用核查表。

系统的核心目标不是替代 DeepScientist 生成想法，而是解决科研 Agent 常见的 citation hallucination 问题：引用看似真实但 DOI 不存在，文献信息与真实记录不一致，或者文献存在但并不能支持 claim。为满足课程评分中“不能只靠 prompt”和“必须有工具调用”的要求，本项目实现了自写 DeepScientist skill、自写 citation verifier、自写 evidence chain tracer、公开学术 API 检索、工具调用日志、QQ 现场交互与可复现输出目录。

## 1. 项目题目与选择方向

项目题目为 **DeepScientist Citation Audit Agent**。选择方向为 Project A：为科研 Agent 增加“证据链追踪模块”。

老师补充要求中强调，输入应为来自不同学科的文章 PDF，Agent 需要像人类科研一样查找相关文献并形成新的 research idea / hypothesis，随后检查这个 idea 所参考的文献是否存在错误。如果文献和 claim 的支持关系正确，标 Green；如果不确定，标 Yellow；如果确定错误，标 Red。

因此，本项目的任务可以概括为：

```text
PDF paper input
-> Official DeepScientist generates hypothesis and citation-backed claims
-> Self-written citation audit module verifies cited literature
-> Green / Yellow / Red evidence-chain report
```

其中，DeepScientist 是基础科研 Agent，本项目新增的是 citation audit 和 evidence-chain tracking 模块。

## 2. 选择的基础系统

本项目选择 official DeepScientist 作为基础系统，并使用 Claude Code 作为 DeepScientist runner。DeepScientist 提供科研 Agent 的基本流程：

```text
read papers
-> identify research gaps
-> generate hypotheses
-> prepare research report
```

本项目新增模块插入在 hypothesis generation 之后、final report writing 之前：

```text
Official DeepScientist quest
-> citation_audit_claims.json
-> citation evidence-chain audit
-> citation_verification.csv
-> evidence_chain.csv
-> final audit report
```

为了让 official DeepScientist 能够稳定接入本项目，我们实现了两个主线 skill：

1. `citation-hypothesis-claims`
   负责让 DeepScientist 从 PDF 生成 idea cards 和 citation-backed claims，并写出 `citation_audit_claims.json`。

2. `citation-evidence-audit`
   负责将 `citation_audit_claims.json` 交给本地 deterministic verifier，输出 Green / Yellow / Red 审计结果和 evidence chain。

需要强调的是：DeepScientist 负责生成科研想法，本项目负责审查引用是否可靠。Green / Yellow / Red 不是由 LLM 直接决定，而是由本地规则、公开学术 API 和 evidence chain 共同决定。

## 3. 问题定义

科研 Agent 在生成研究假说或论文分析时，常常会引用一些看似专业的文献。但这些引用可能存在以下问题：

- 文献不存在，DOI 或标题是编造的；
- 文献存在，但作者、年份、标题、DOI 与真实记录不一致；
- 文献存在且元数据正确，但摘要或检索片段不能支持 claim；
- claim 过强，例如把“可能相关”写成“已证明”；
- 版本不一致，例如 arXiv preprint 和正式发表版本年份不同；
- API 查询失败或摘要缺失，导致支持关系无法确认。

如果只靠大模型自己判断，很容易变成“用幻觉审查幻觉”。因此，本项目将引用审查拆成三个可解释层次：

1. Existence check：文献是否存在；
2. Metadata check：标题、作者、年份、DOI 是否匹配；
3. Support check：文献摘要、snippet 或 supporting sentence 是否支持 claim。

最终颜色规则为：

- Green：文献存在，元数据匹配，并且有具体支持句；
- Yellow：文献存在但支持关系不确定、摘要不足、只部分相关或需要人工复查；
- Red：文献不存在、元数据明显错误或证据明确不支持 claim。

## 4. 系统设计

系统由五个主要部分组成。

### 4.1 Official DeepScientist 接入

系统通过 `scripts/run_official_ds_case.py` 和 campaign runner 创建或复用 DeepScientist quest，向 DeepScientist 提供固定 prompt，要求其生成 `citation_audit_claims.json`。该 JSON 文件是官方 DeepScientist 与本项目审计模块之间的边界。

### 4.2 Citation Audit 工具链

本地 citation audit 工具链读取 `citation_audit_claims.json`，对每条 claim 的 cited work 执行公开 API 检索和规则化核查。主要使用的 provider 包括：

- Crossref；
- OpenAlex；
- Semantic Scholar；
- arXiv。

每次 provider 查询都会写入 `tool_calls.jsonl`，不会静默跳过失败。API 失败、timeout 或 429 会被记录，并通常导致 Yellow，而不是伪造成 Green。

### 4.3 Evidence Chain Tracing

系统为每条 claim、每次工具调用、每条检索证据分配 evidence id 或 tool call id。最终报告中可以追踪：

```text
claim
-> cited work
-> provider lookup result
-> metadata/support status
-> evidence id
-> Green / Yellow / Red label
```

这使得老师可以直接打开 `citation_verification.csv`、`evidence_chain.csv`、`tool_calls.jsonl` 和 `evidence_items.jsonl` 检查系统行为。

### 4.4 QQ Bot 交互

为了满足现场展示要求，系统提供 QQ Bot 交互入口。主要命令包括：

```text
/official "C:\path\paper.pdf"
/local "C:\path\paper.pdf"
/help
```

`/official` 会启动 official DeepScientist workflow，并在生成 claims 后进入 citation audit。QQ 交互会返回任务进度、run directory、Green / Yellow / Red 数量、multi-reviewer 决策和关键 artifact 路径。

### 4.5 Multi-reviewer 与 Memory

Multi-reviewer 模块由郭耀远负责，Memory 模块由齐佳男负责。它们位于 citation audit 后续的质量控制层：multi-reviewer 对 idea 质量和展示风险进行评分，memory 记录历史 citation、provider、failure 和 reviewer 决策。需要说明的是，multi-reviewer 和 memory 不直接覆盖 Green / Yellow / Red 标签，最终标签仍由 deterministic verifier 决定。

## 5. 测试样例与结果

本项目进行了多轮本地 workflow、official DeepScientist campaign 和 QQ 现场交互测试。统计范围包括：

```text
outputs/runs/
outputs/deepscientist_15x_campaigns/
outputs/deepscientist_20x_campaigns/
```

截至当前统计，共包含：

| 指标 | 数值 |
|---|---:|
| citation audit CSV 文件 | 33 |
| checked claims | 201 |
| Green | 61 |
| Yellow | 138 |
| Red | 2 |
| tool call rows | 1408 |
| evidence items | 985 |
| multi-review reports | 24 |

这些数字说明系统不是只跑单个 demo，而是保留了多次真实运行的 evidence artifacts。Yellow 数量较多是预期现象，因为系统采用保守审计策略：只要不能确认具体支持，就不会强行标 Green。

### 5.1 成功案例：CLIP

成功案例选择 `qq_pdf_ai_clip_transfer`，运行目录位于：

```text
outputs/deepscientist_20x_campaigns/
qq_official_20260605_011710/
cases/qq_pdf_ai_clip_transfer/
```

该案例审计结果为：

```text
Green = 5
Yellow = 1
Red = 0
```

代表性 Green claim 是：视觉模型通常训练为预测固定类别。系统引用 CLIP 原论文 `Learning Transferable Visual Models From Natural Language Supervision`，并找到支持句：

```text
State-of-the-art computer vision systems are trained to predict a fixed set of predetermined object categories.
```

该引用满足 Green 条件：文献存在、元数据匹配、supporting sentence 直接支持 claim。

### 5.2 医学案例：CheXNet

QQ 现场交互案例选择医学方向的 CheXNet PDF。该案例用于展示系统可以通过 QQ 命令接收 PDF 路径，启动 official DeepScientist workflow，持续返回 progress heartbeat，并最终生成审计结果。该流程中，系统会输出 run directory、Green / Yellow / Red 数量、multi-reviewer score 以及关键 artifact 路径。

### 5.3 多领域测试

项目中还测试了 AI、医学、物理、优化、教育、金融等多个领域的公开论文，包括 Transformer、RAG、CheXNet、CLIP、Adam optimizer、GW150914 等案例。这些案例用于验证系统面对不同学科 PDF 和不同 citation metadata 完整度时的泛化能力。

## 6. 失败案例与边界案例

边界案例选择 `qq_pdf_physics_gravitational_waves`，运行目录位于：

```text
outputs/deepscientist_20x_campaigns/
qq_official_20260605_035133/
cases/qq_pdf_physics_gravitational_waves/
```

该案例结果为：

```text
Green = 3
Yellow = 2
Red = 1
```

这个案例不是最简单的“假 DOI”错误，而是更接近真实 citation audit 中会出现的问题：文献可能存在，但引用元数据或支持关系存在风险。系统发现其中一条引用存在 author metadata mismatch 或 support mismatch，因此将其标为 Red 或需要严格复查。

失败和边界情况主要包括：

- official DeepScientist 生成 `citation_audit_claims.json` 时间较长；
- Semantic Scholar 或 arXiv 可能出现 429、timeout；
- 文献存在但没有可用 abstract；
- arXiv 和 journal version 年份不同；
- claim 太强，但 public snippet 只能部分支持；
- 多 provider 返回结果不一致。

系统处理策略是：API 失败不伪造成成功；摘要不足不强行 Green；版本或年份不确定时标 Yellow；metadata 明显冲突或支持关系明确错误时标 Red。

## 7. 局限性与未来改进

当前系统仍有以下局限：

1. 主要依赖公开 API 的 metadata、abstract 和 snippet，不保证能读取所有 cited paper 的全文；
2. 跨学科 claim 的支持关系有时很难仅凭摘要判断；
3. official DeepScientist 运行耗时不稳定，有时需要较长时间生成 claims；
4. Semantic Scholar、arXiv 等 API 可能限流；
5. PDF 文本抽取对扫描件、双栏错序和复杂排版仍不稳定；
6. Yellow 数量偏多，说明系统保守但也需要进一步提高自动支持判断能力。

未来可以从以下方向改进：

- 增加 cited paper 全文下载和段落级 supporting sentence；
- 对 arXiv preprint 和 journal version 做更强的版本合并；
- 增加更细粒度错误类型，例如 invalid DOI、author mismatch、claim too strong、provider disagreement；
- 引入更稳定的缓存机制，减少重复 API 查询；
- 改进 PDF layout parsing；
- 将 QQ 展示中的 artifact 打包成更易读的 HTML summary。

## 8. 小组贡献说明

本项目分工如下：

| 成员 | 主要分工 |
|---|---|
| 郭耀远 | Multi-reviewer 模块、本地 workflow 测试、reviewer 输出与评分逻辑调试 |
| 齐佳男 | Memory 模块、历史 citation/provider/reviewer/failure 记录与查询 |
| 刘炎男 | Official DeepScientist 接入、self-written skill、citation verifier、tool-use 工具链、QQ Bot、测试样例整理、报告、海报、PPT 和提交材料 |

整体来看，DeepScientist 负责生成科研 hypothesis，本项目新增模块负责对 hypothesis 中的 citation-backed claims 做证据链追踪和 Green / Yellow / Red 审计。该系统能够展示工具调用日志、文献检索结果、引用核查表、证据链文件、QQ 交互过程和成功/边界案例，符合 Project A 对可验证科研 Agent 扩展的要求。

## 9. 复现与提交材料

项目可从仓库根目录运行。典型命令为：

```powershell
python scripts/run_official_ds_case.py `
  --case-id qq_pdf_demo `
  --pdf "C:\path\paper.pdf" `
  --run-id qq_official_demo
```

QQ 演示命令为：

```text
/official "C:\path\paper.pdf"
```

每次成功运行后，重点检查以下文件：

```text
citation_audit_claims.json
citation_verification.csv
evidence_chain.csv
tool_calls.jsonl
evidence_items.jsonl
deepscientist_audit_summary.md
multi_review_report.md
final_case_report.md
```

这些文件共同构成可复现的 citation evidence chain。即使现场网络或 API 失败，也可以通过提前保存的 run directory、CSV、日志和报告解释系统行为。
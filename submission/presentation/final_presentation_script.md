# DeepScientist Citation Audit Agent 展示文字稿

展示时间建议：10 分钟展示 + 5 分钟问答。
展示重点：方向选择、QQ 交互、成功案例、边界案例、结果解释和可复现证据。

---

## 第 1 页：项目选择与问题定义

### 屏幕正文

**DeepScientist Citation Audit Agent**

- 方向：Project A 科研智能体功能扩展
- 基础系统：official DeepScientist
- 输入：不同学科论文 PDF
- 任务：生成 research idea / hypothesis 后，审计其引用可靠性
- 输出：Green / Yellow / Red citation audit report

### 讲稿

我们选择的是 Project A，也就是给科研智能体增加一个可验证的功能扩展。
基础 Agent 使用 official DeepScientist，它负责读取论文 PDF、检索相关文献，并生成新的 research idea 或 hypothesis。
我们新增的部分不是另一个聊天模块，而是在 DeepScientist 生成引用支撑的 claim 之后，对这些引用进行独立审计。
最终系统输出 Green、Yellow、Red 三类标签，帮助判断文献是否真实、元数据是否正确，以及文献内容是否真的支持生成的 idea。

---

## 第 2 页：为什么需要这个系统

### 屏幕正文

**Citation Hallucination Is Hard To See**

- LLM 生成科研 idea 时常附带看似真实的引用
- 风险：假 DOI、年份错误、作者不匹配、版本混淆
- 更隐蔽的问题：文献存在，但不支持 claim
- 人工逐条查引用成本高
- 目标：把每条 citation-backed claim 变成可审查对象

### 讲稿

老师的补充要求强调，核心是查找生成 idea 所参考文献中的幻觉，并做颜色标注。
这类问题不能只靠肉眼看引用格式，因为很多引用看起来非常专业，甚至 DOI 也可能能解析。
真正的问题在于：它引用的论文是否确实存在，作者、年份、标题是否匹配，以及摘要或证据句是否支持 claim。
所以我们把引用核查拆成三层：existence check、metadata check 和 support check。这样可以避免用一个大模型去“凭感觉”审查另一个大模型。

---

## 第 3 页：系统总流程

### 屏幕正文

**Pipeline**

`PDF -> DeepScientist / local skill -> claims -> citation audit -> R/Y/G report`

- DeepScientist：生成 hypothesis 和 citation-backed claims
- Self-written skill：生成/整理 claim，调用检索与审计工具
- Citation verifier：决定 Green / Yellow / Red
- Evidence chain：记录 evidence id、tool call id、support sentence
- Reviewer + Memory：辅助解释、评分和复查提示

### 讲稿

系统可以走两条路径。
第一条是 official DeepScientist 路径：DeepScientist 生成 idea 和 claim，我们接收 `citation_audit_claims.json` 后进行审计。
第二条是本地路径：当官方 DeepScientist 运行不稳定时，本地 skill 会读取 PDF、生成 query、检索文献并生成 claim。
无论走哪条路径，后面的 citation audit 都是同一套自实现工具链。
最终每条 claim 都会关联 evidence id、工具调用日志和颜色标签。

---

## 第 4 页：自实现工具链

### 屏幕正文

**Self-Written Tools**

- PDF reader / claim generator
- Literature search: Crossref, OpenAlex, Semantic Scholar, arXiv
- Citation verifier: existence + metadata + support
- Evidence chain tracer
- Tool-call logger
- QQ command bridge

### 讲稿

这一页主要回应评分标准。
如果只是写 prompt 让 Agent 直接回答，最高只能到 C+；如果只是调用开源工具而没有自己的工具链，也会被限制。
我们这里实现了自己的工具链：PDF 解析、query 生成、文献检索、引用核查、证据链追踪、工具日志和 QQ 命令桥接。
每一步都会写入可检查的文件，例如 `tool_calls.jsonl`、`evidence_items.jsonl`、`citation_verification.csv` 和 `evidence_chain.csv`。
所以展示时可以直接打开后台文件，而不是只展示 QQ 聊天结果。

---

## 第 5 页：Green / Yellow / Red 判定标准

### 屏幕正文

**Deterministic Citation Scoring**

- Green：文献存在，元数据匹配，有具体 supporting sentence
- Yellow：文献存在，但支持关系弱、摘要不足、版本/年份需复查
- Red：文献不存在、DOI/作者/标题明显错误，或 claim 与证据冲突
- 规则：宁可 Yellow，也不强行 Green
- LLM reviewer 不能覆盖最终 R/Y/G 标签

### 讲稿

Green 的门槛最高，不是说找到一篇主题相关的文献就能 Green。
必须满足文献存在、元数据匹配、并且能找到具体 supporting sentence。
Yellow 用来处理不确定情况，比如文献存在但摘要不够、只部分支持、版本不清楚或者需要人工看全文。
Red 用于确定错误，比如找不到文献、DOI 指向不同论文、作者明显不匹配，或者证据与 claim 冲突。
我们的原则是保守审计：不确定就 Yellow，不能为了结果好看强行标 Green。

---

## 第 6 页：QQ / WeChat 现场交互

### 屏幕正文

**Live Interaction**

- `/local "C:\path\paper.pdf"`：本地完整 workflow
- `/official "C:\path\paper.pdf"`：official DeepScientist + citation audit
- QQ 返回：进度、run directory、G/Y/R 数量、artifact 路径
- 现场投屏展示完整交互过程
- 关键文件：tool logs、audit CSV、evidence chain、final report

### 讲稿

这一页只做简单说明，现场展示时我会直接投屏 QQ 或 WeChat 交互。
展示重点不是“机器人回复了一句话”，而是它能接收 PDF 路径，启动 workflow，持续返回进度，并在完成后给出 run directory 和 Green / Yellow / Red 数量。
然后我会打开对应目录里的 `tool_calls.jsonl`、`citation_verification.csv`、`evidence_chain.csv` 和 `final_report.md`。
这样可以证明系统真的调用了工具，并且产生了可复现的审计材料。

---

## 第 7 页：成功案例

### 屏幕正文

**Success Case: CLIP / Visual-Language Transfer**

- Case：`qq_pdf_ai_clip_transfer`
- Run：`qq_official_20260605_011710`
- Result：Green = 5, Yellow = 1, Red = 0
- Representative Green:
  - Claim：视觉模型通常训练为预测固定类别
  - Citation：*Learning Transferable Visual Models From Natural Language Supervision*
  - Evidence：State-of-the-art computer vision systems are trained to predict a fixed set of predetermined object categories.

### 讲稿

成功案例选择 CLIP 相关论文，因为它的审计结果比较清楚：6 条 claim 里有 5 条 Green、1 条 Yellow，没有 Red。
代表性 Green 的 claim 是：state-of-the-art computer vision systems are trained to predict a fixed set of predetermined object categories。
系统找到的 cited work 是 CLIP 原论文，arXiv id 和标题都能匹配，并且 supporting sentence 几乎逐字覆盖 claim。
因此这个案例可以展示 Green 的定义：不是只找到论文，而是找到具体支持句。

---

## 第 8 页：失败 / 边界案例

### 屏幕正文

**Boundary Case: GW150914**

- Case：`qq_pdf_physics_gravitational_waves`
- Run：`qq_official_20260605_035133`
- Result：Green = 3, Yellow = 2, Red = 1
- Red reason:
  - cited paper exists
  - supporting sentence is partially related
  - author metadata mismatch
  - system label：`author_mismatch`

### 讲稿

这个案例是边界案例，不是最简单的假 DOI。
文献 `Tests of general relativity with GW150914` 是存在的，而且 supporting sentence 里确实提到了 graviton Compton wavelength 和 10 的 13 次方 km。
但是系统检测到 author metadata overlap 不足，同时 claim 的部分关键内容没有被证据完整覆盖。
所以这个例子说明：文献存在并不等于引用正确。
它展示了系统对“真实文献但引用可靠性不足”的细粒度审计能力。

---

## 第 9 页：汇总结果

### 屏幕正文

**Reproducible Audit Scale**

统计范围：`deepscientist_15x_campaigns`、`deepscientist_20x_campaigns`、`outputs/runs`

- citation audit CSV：29 个
- checked claims：178 条
- Green / Yellow / Red：57 / 119 / 2
- tool calls：1219 条
- evidence items：797 条
- multi-review reports：22 个

### 讲稿

这些数字来自当前三个输出目录的真实文件统计，不是人工编造的展示数字。
总共有 29 个 citation audit CSV、178 条被审查 claim、1219 条工具调用记录和 797 条证据记录。
Green / Yellow / Red 的分布是 57 / 119 / 2。
Yellow 数量明显最多，这说明系统的策略是保守的：只要公开 API 或证据句不能直接支持 claim，就标 Yellow，留给人工复查。
这比把不确定结果都标 Green 更符合科研场景。

---

## 第 10 页：总结与答辩要点

### 屏幕正文

**Takeaway**

- 基础系统：official DeepScientist
- 核心扩展：citation evidence-chain audit module
- 判断依据：public scholarly APIs + deterministic rules
- 可复现证据：tool logs、evidence IDs、CSV、final report
- 展示材料：QQ 交互、成功案例、边界案例、统计报告
- 局限：摘要不足、API 覆盖有限、全文支持判断仍需增强

### 讲稿

最后总结一下，本项目的核心贡献是给 DeepScientist 增加了一个 evidence-control layer。
DeepScientist 负责生成科研 idea，我们的系统负责让 idea 中的引用变得可见、可查、可复现。
我们不是用大模型单独决定引用是否正确，而是用 Crossref、OpenAlex、Semantic Scholar、arXiv 等公开学术 API，加上确定性规则做分层核查。
同时通过 QQ 交互、工具日志、证据链表和多评审报告，满足现场展示和复现要求。
目前的局限是：很多开放 API 只提供摘要，全文证据不足时仍需要人工复查；后续可以增强全文 PDF 检索和段落级 evidence。
const pptxgen = require('pptxgenjs');
const fs = require('fs');
const path = require('path');

const outDir = __dirname;
const pptx = new pptxgen();
pptx.layout = 'LAYOUT_WIDE';
pptx.author = 'LLM Hypothesis Citation Agent Team';
pptx.subject = 'DeepScientist citation hallucination audit';
pptx.title = 'DeepScientist Citation Audit Agent';
pptx.company = 'SUSTech';
pptx.lang = 'zh-CN';
pptx.theme = {
  headFontFace: 'Microsoft YaHei',
  bodyFontFace: 'Microsoft YaHei',
  lang: 'zh-CN',
};
pptx.defineLayout({ name: 'CUSTOM_WIDE', width: 13.333, height: 7.5 });
pptx.layout = 'CUSTOM_WIDE';
pptx.margin = 0;

const C = {
  navy: '0B3B75',
  blue: '145AA0',
  lightBlue: 'EAF3FF',
  paleBlue: 'F6FAFF',
  orange: 'F27618',
  green: '168A4F',
  yellow: 'F2A900',
  red: 'D62828',
  purple: '7C3AED',
  gray: '5B6574',
  text: '132033',
  white: 'FFFFFF',
  line: 'B8CCE8',
};

const slides = [
  {
    no: '01',
    title: '项目选择与问题定义',
    headline: 'DeepScientist Citation Audit Agent',
    bullets: [
      ['方向', 'Project A 科研智能体功能扩展'],
      ['基础系统', 'official DeepScientist'],
      ['输入', '不同学科论文 PDF'],
      ['任务', '生成 hypothesis 后审计引用可靠性'],
      ['输出', 'Green / Yellow / Red citation audit report'],
    ],
    callout: '把生成 idea 中的每条引用变成可检查证据对象。',
    notes: `我们选择的是 Project A，也就是给科研智能体增加一个可验证的功能扩展。
基础 Agent 使用 official DeepScientist，它负责读取论文 PDF、检索相关文献，并生成新的 research idea 或 hypothesis。
我们新增的部分不是另一个聊天模块，而是在 DeepScientist 生成引用支撑的 claim 之后，对这些引用进行独立审计。
最终系统输出 Green、Yellow、Red 三类标签，帮助判断文献是否真实、元数据是否正确，以及文献内容是否真的支持生成的 idea。`,
  },
  {
    no: '02',
    title: '为什么需要这个系统',
    headline: 'Citation Hallucination Is Hard To See',
    bullets: [
      ['表面问题', 'LLM 会给科研 idea 附带看似真实的引用'],
      ['明显风险', '假 DOI、年份错误、作者不匹配、版本混淆'],
      ['隐蔽风险', '文献存在，但不支持 claim'],
      ['人工成本', '逐条查引用耗时且难以复现'],
      ['目标', '把 citation-backed claim 变成可审查对象'],
    ],
    callout: '不是“用幻觉审核幻觉”，而是用工具和公开 API 做分层核查。',
    notes: `老师的补充要求强调，核心是查找生成 idea 所参考文献中的幻觉，并做颜色标注。
这类问题不能只靠肉眼看引用格式，因为很多引用看起来非常专业，甚至 DOI 也可能能解析。
真正的问题在于：它引用的论文是否确实存在，作者、年份、标题是否匹配，以及摘要或证据句是否支持 claim。
所以我们把引用核查拆成三层：existence check、metadata check 和 support check。这样可以避免用一个大模型去“凭感觉”审查另一个大模型。`,
  },
  {
    no: '03',
    title: '系统总流程',
    headline: 'PDF -> Claims -> Citation Audit -> R/Y/G Report',
    flow: ['PDF', 'DeepScientist / Local Skill', 'Claims', 'Citation Audit', 'R/Y/G Report'],
    bullets: [
      ['DeepScientist', '生成 hypothesis 和 citation-backed claims'],
      ['Self-written skill', '生成/整理 claim，调用检索与审计工具'],
      ['Citation verifier', '决定 Green / Yellow / Red'],
      ['Evidence chain', '记录 evidence id、tool call id、support sentence'],
      ['Reviewer + Memory', '辅助解释、评分和复查提示'],
    ],
    notes: `系统可以走两条路径。
第一条是 official DeepScientist 路径：DeepScientist 生成 idea 和 claim，我们接收 citation_audit_claims.json 后进行审计。
第二条是本地路径：当官方 DeepScientist 运行不稳定时，本地 skill 会读取 PDF、生成 query、检索文献并生成 claim。
无论走哪条路径，后面的 citation audit 都是同一套自实现工具链。
最终每条 claim 都会关联 evidence id、工具调用日志和颜色标签。`,
  },
  {
    no: '04',
    title: '自实现工具链',
    headline: 'Self-Written Tools, Not Prompt-Only',
    bullets: [
      ['PDF / Claim', 'PDF reader 与 claim generator'],
      ['Retrieval', 'Crossref、OpenAlex、Semantic Scholar、arXiv'],
      ['Verifier', 'existence + metadata + support'],
      ['Evidence', 'evidence chain tracer'],
      ['Logging', 'tool-call logger'],
      ['Demo', 'QQ command bridge'],
    ],
    artifacts: ['tool_calls.jsonl', 'evidence_items.jsonl', 'citation_verification.csv', 'evidence_chain.csv'],
    callout: '评分关键：展示工具调用日志、检索结果、核查表，而不是只展示聊天回答。',
    notes: `这一页主要回应评分标准。
如果只是写 prompt 让 Agent 直接回答，最高只能到 C+；如果只是调用开源工具而没有自己的工具链，也会被限制。
我们这里实现了自己的工具链：PDF 解析、query 生成、文献检索、引用核查、证据链追踪、工具日志和 QQ 命令桥接。
每一步都会写入可检查的文件，例如 tool_calls.jsonl、evidence_items.jsonl、citation_verification.csv 和 evidence_chain.csv。
所以展示时可以直接打开后台文件，而不是只展示 QQ 聊天结果。`,
  },
  {
    no: '05',
    title: '判定标准',
    headline: 'Deterministic Citation Scoring',
    rules: [
      ['Green', '文献存在 + 元数据匹配 + 具体 supporting sentence', C.green],
      ['Yellow', '文献存在但支持弱、摘要不足、版本/年份需复查', C.yellow],
      ['Red', '文献不存在、元数据明显错、或 claim 与证据冲突', C.red],
    ],
    bullets: [
      ['保守原则', '宁可 Yellow，也不强行 Green'],
      ['边界', 'LLM reviewer 不能覆盖最终 R/Y/G 标签'],
      ['证据要求', 'Green 必须有可引用的具体支持句'],
    ],
    notes: `Green 的门槛最高，不是说找到一篇主题相关的文献就能 Green。
必须满足文献存在、元数据匹配、并且能找到具体 supporting sentence。
Yellow 用来处理不确定情况，比如文献存在但摘要不够、只部分支持、版本不清楚或者需要人工看全文。
Red 用于确定错误，比如找不到文献、DOI 指向不同论文、作者明显不匹配，或者证据与 claim 冲突。
我们的原则是保守审计：不确定就 Yellow，不能为了结果好看强行标 Green。`,
  },
  {
    no: '06',
    title: 'QQ / WeChat 现场交互',
    headline: 'Live Interaction Layer',
    commands: [
      ['/local "C:\\\\path\\\\paper.pdf"', '本地完整 workflow'],
      ['/official "C:\\\\path\\\\paper.pdf"', 'official DeepScientist + citation audit'],
    ],
    bullets: [
      ['QQ 返回', '进度、run directory、G/Y/R 数量、artifact 路径'],
      ['现场展示', '投屏完整交互过程'],
      ['关键文件', 'tool logs、audit CSV、evidence chain、final report'],
    ],
    callout: '现场重点：不是聊天结果，而是后台生成的可审计文件。',
    notes: `这一页只做简单说明，现场展示时我会直接投屏 QQ 或 WeChat 交互。
展示重点不是“机器人回复了一句话”，而是它能接收 PDF 路径，启动 workflow，持续返回进度，并在完成后给出 run directory 和 Green / Yellow / Red 数量。
然后我会打开对应目录里的 tool_calls.jsonl、citation_verification.csv、evidence_chain.csv 和 final_report.md。
这样可以证明系统真的调用了工具，并且产生了可复现的审计材料。`,
  },
  {
    no: '07',
    title: '成功案例',
    headline: 'Success Case: CLIP / Visual-Language Transfer',
    metrics: [
      ['Green', '5', C.green],
      ['Yellow', '1', C.yellow],
      ['Red', '0', C.red],
    ],
    bullets: [
      ['Case', 'qq_pdf_ai_clip_transfer'],
      ['Run', 'qq_official_20260605_011710'],
      ['Claim', '视觉模型通常训练为预测固定类别'],
      ['Citation', 'Learning Transferable Visual Models From Natural Language Supervision'],
      ['Evidence', 'State-of-the-art computer vision systems are trained to predict a fixed set of predetermined object categories.'],
    ],
    notes: `成功案例选择 CLIP 相关论文，因为它的审计结果比较清楚：6 条 claim 里有 5 条 Green、1 条 Yellow，没有 Red。
代表性 Green 的 claim 是：state-of-the-art computer vision systems are trained to predict a fixed set of predetermined object categories。
系统找到的 cited work 是 CLIP 原论文，arXiv id 和标题都能匹配，并且 supporting sentence 几乎逐字覆盖 claim。
因此这个案例可以展示 Green 的定义：不是只找到论文，而是找到具体支持句。`,
  },
  {
    no: '08',
    title: '失败 / 边界案例',
    headline: 'Boundary Case: GW150914',
    metrics: [
      ['Green', '3', C.green],
      ['Yellow', '2', C.yellow],
      ['Red', '1', C.red],
    ],
    bullets: [
      ['Case', 'qq_pdf_physics_gravitational_waves'],
      ['Run', 'qq_official_20260605_035133'],
      ['现象', 'cited paper exists, but citation reliability is risky'],
      ['Red reason', 'author metadata mismatch'],
      ['Why boundary', 'supporting sentence partially related, but metadata/support not enough for Green'],
    ],
    notes: `这个案例是边界案例，不是最简单的假 DOI。
文献 Tests of general relativity with GW150914 是存在的，而且 supporting sentence 里确实提到了 graviton Compton wavelength 和 10 的 13 次方 km。
但是系统检测到 author metadata overlap 不足，同时 claim 的部分关键内容没有被证据完整覆盖。
所以这个例子说明：文献存在并不等于引用正确。
它展示了系统对“真实文献但引用可靠性不足”的细粒度审计能力。`,
  },
  {
    no: '09',
    title: '汇总结果',
    headline: 'Reproducible Audit Scale',
    stats: [
      ['citation audit CSV', '29'],
      ['checked claims', '178'],
      ['Green / Yellow / Red', '57 / 119 / 2'],
      ['tool calls', '1219'],
      ['evidence items', '797'],
      ['multi-review reports', '22'],
    ],
    bullets: [
      ['统计范围', 'deepscientist_15x_campaigns, deepscientist_20x_campaigns, outputs/runs'],
      ['观察', 'Yellow 数量最多，说明审计策略保守'],
      ['意义', '系统不是只跑一个 demo，而是保留了可复现 evidence package'],
    ],
    notes: `这些数字来自当前三个输出目录的真实文件统计，不是人工编造的展示数字。
总共有 29 个 citation audit CSV、178 条被审查 claim、1219 条工具调用记录和 797 条证据记录。
Green / Yellow / Red 的分布是 57 / 119 / 2。
Yellow 数量明显最多，这说明系统的策略是保守的：只要公开 API 或证据句不能直接支持 claim，就标 Yellow，留给人工复查。
这比把不确定结果都标 Green 更符合科研场景。`,
  },
  {
    no: '10',
    title: '总结与答辩要点',
    headline: 'Takeaway: Evidence-Control Layer for DeepScientist',
    bullets: [
      ['基础系统', 'official DeepScientist'],
      ['核心扩展', 'citation evidence-chain audit module'],
      ['判断依据', 'public scholarly APIs + deterministic rules'],
      ['可复现证据', 'tool logs、evidence IDs、CSV、final report'],
      ['展示材料', 'QQ 交互、成功案例、边界案例、统计报告'],
      ['局限', '摘要不足、API 覆盖有限、全文支持判断仍需增强'],
    ],
    callout: 'Citation-backed scientific ideas become visible, checkable, and reproducible.',
    notes: `最后总结一下，本项目的核心贡献是给 DeepScientist 增加了一个 evidence-control layer。
DeepScientist 负责生成科研 idea，我们的系统负责让 idea 中的引用变得可见、可查、可复现。
我们不是用大模型单独决定引用是否正确，而是用 Crossref、OpenAlex、Semantic Scholar、arXiv 等公开学术 API，加上确定性规则做分层核查。
同时通过 QQ 交互、工具日志、证据链表和多评审报告，满足现场展示和复现要求。
目前的局限是：很多开放 API 只提供摘要，全文证据不足时仍需要人工复查；后续可以增强全文 PDF 检索和段落级 evidence。`,
  },
];

function addHeader(slide, item) {
  slide.background = { color: C.white };
  slide.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: 13.333, h: 0.62, fill: { color: C.navy }, line: { color: C.navy } });
  slide.addText(item.no, { x: 0.35, y: 0.14, w: 0.55, h: 0.25, fontFace: 'Aptos Display', fontSize: 11, bold: true, color: C.white, margin: 0 });
  slide.addText(item.title, { x: 0.95, y: 0.11, w: 6.2, h: 0.32, fontFace: 'Microsoft YaHei', fontSize: 17, bold: true, color: C.white, margin: 0 });
  slide.addText('LLM Course Project A · DeepScientist Citation Audit', { x: 8.1, y: 0.17, w: 4.75, h: 0.22, fontFace: 'Aptos', fontSize: 9, color: 'DCEBFF', align: 'right', margin: 0 });
}

function addTitle(slide, headline) {
  slide.addText(headline, { x: 0.5, y: 0.92, w: 12.2, h: 0.45, fontFace: 'Microsoft YaHei', fontSize: 27, bold: true, color: C.text, margin: 0 });
  slide.addShape(pptx.ShapeType.line, { x: 0.5, y: 1.45, w: 12.2, h: 0, line: { color: C.line, width: 1.4 } });
}

function addBullets(slide, bullets, x, y, w, opts = {}) {
  const rowH = opts.rowH || 0.55;
  const labelW = opts.labelW || 1.4;
  bullets.forEach((b, idx) => {
    const yy = y + idx * rowH;
    slide.addShape(pptx.ShapeType.roundRect, { x, y: yy + 0.04, w: labelW, h: 0.34, rectRadius: 0.06, fill: { color: opts.labelColor || C.lightBlue }, line: { color: opts.labelLine || C.line, width: 0.8 } });
    slide.addText(b[0], { x: x + 0.1, y: yy + 0.105, w: labelW - 0.2, h: 0.18, fontSize: opts.labelSize || 9.2, bold: true, color: opts.labelText || C.blue, align: 'center', margin: 0 });
    slide.addText(b[1], { x: x + labelW + 0.18, y: yy + 0.02, w: w - labelW - 0.2, h: 0.42, fontFace: 'Microsoft YaHei', fontSize: opts.bodySize || 13, color: C.text, fit: 'shrink', breakLine: false, margin: 0.02 });
  });
}

function addCallout(slide, text, y, color = C.orange) {
  slide.addShape(pptx.ShapeType.roundRect, { x: 0.6, y, w: 12.1, h: 0.52, rectRadius: 0.08, fill: { color: 'FFF7ED' }, line: { color, width: 1.1 } });
  slide.addText(text, { x: 0.85, y: y + 0.13, w: 11.6, h: 0.23, fontSize: 14, bold: true, color, align: 'center', margin: 0 });
}

function addArtifactBar(slide, items, y) {
  const n = items.length;
  const gap = 0.18;
  const totalW = 12.0;
  const cardW = (totalW - gap * (n - 1)) / n;
  items.forEach((it, i) => {
    const x = 0.65 + i * (cardW + gap);
    slide.addShape(pptx.ShapeType.roundRect, { x, y, w: cardW, h: 0.45, rectRadius: 0.06, fill: { color: C.navy }, line: { color: C.navy } });
    slide.addText(it, { x: x + 0.05, y: y + 0.13, w: cardW - 0.1, h: 0.18, fontSize: 8.5, bold: true, color: C.white, align: 'center', margin: 0, fit: 'shrink' });
  });
}

function addFlow(slide, items, y) {
  const cardW = 2.15;
  const gap = 0.38;
  items.forEach((it, i) => {
    const x = 0.55 + i * (cardW + gap);
    slide.addShape(pptx.ShapeType.roundRect, { x, y, w: cardW, h: 0.72, rectRadius: 0.08, fill: { color: i === 3 ? 'FFF7ED' : C.lightBlue }, line: { color: i === 3 ? C.orange : C.blue, width: 1.4 } });
    slide.addText(it, { x: x + 0.1, y: y + 0.23, w: cardW - 0.2, h: 0.22, fontSize: 12.5, bold: true, color: i === 3 ? C.orange : C.blue, align: 'center', margin: 0, fit: 'shrink' });
    if (i < items.length - 1) {
      slide.addShape(pptx.ShapeType.chevron, { x: x + cardW + 0.07, y: y + 0.25, w: 0.24, h: 0.22, fill: { color: C.blue }, line: { color: C.blue } });
    }
  });
}

function addMetrics(slide, metrics, x, y, w) {
  const gap = 0.2;
  const cardW = (w - gap * (metrics.length - 1)) / metrics.length;
  metrics.forEach((m, i) => {
    const xx = x + i * (cardW + gap);
    slide.addShape(pptx.ShapeType.roundRect, { x: xx, y, w: cardW, h: 1.0, rectRadius: 0.08, fill: { color: C.white }, line: { color: m[2], width: 1.5 } });
    slide.addText(m[1], { x: xx, y: y + 0.12, w: cardW, h: 0.34, fontSize: 24, bold: true, color: m[2], align: 'center', margin: 0 });
    slide.addText(m[0], { x: xx, y: y + 0.58, w: cardW, h: 0.2, fontSize: 11, bold: true, color: C.text, align: 'center', margin: 0 });
  });
}

function addFooter(slide) {
  slide.addShape(pptx.ShapeType.rect, { x: 0, y: 7.18, w: 13.333, h: 0.32, fill: { color: C.paleBlue }, line: { color: C.line, transparency: 35 } });
  slide.addText('Artifacts: tool_calls.jsonl · citation_verification.csv · evidence_chain.csv · final_report.md', { x: 0.45, y: 7.26, w: 8.5, h: 0.1, fontSize: 7.4, color: C.gray, margin: 0 });
  slide.addText('DeepScientist Citation Audit Agent', { x: 9.2, y: 7.26, w: 3.7, h: 0.1, fontSize: 7.4, color: C.gray, align: 'right', margin: 0 });
}

function addSpeakerNotes(slide, notes) {
  if (typeof slide.addNotes === 'function') {
    slide.addNotes(notes.split('\n').filter(Boolean));
  } else {
    slide.addNotes = undefined;
  }
}

slides.forEach((item, idx) => {
  const slide = pptx.addSlide();
  addHeader(slide, item);
  addTitle(slide, item.headline);

  if (item.flow) {
    addFlow(slide, item.flow, 1.86);
    addBullets(slide, item.bullets, 0.75, 3.0, 11.8, { rowH: 0.58, labelW: 1.7, bodySize: 13.2 });
  } else if (item.rules) {
    item.rules.forEach((r, i) => {
      const y = 1.82 + i * 0.88;
      slide.addShape(pptx.ShapeType.roundRect, { x: 0.75, y, w: 11.8, h: 0.64, rectRadius: 0.08, fill: { color: i === 0 ? 'EAF8F0' : i === 1 ? 'FFF7D6' : 'FDECEC' }, line: { color: r[2], width: 1.3 } });
      slide.addText(r[0], { x: 1.0, y: y + 0.16, w: 1.05, h: 0.22, fontSize: 16, bold: true, color: r[2], margin: 0 });
      slide.addText(r[1], { x: 2.2, y: y + 0.16, w: 9.8, h: 0.23, fontSize: 14.2, color: C.text, margin: 0, fit: 'shrink' });
    });
    addBullets(slide, item.bullets, 1.0, 4.75, 11.0, { rowH: 0.52, labelW: 1.5, bodySize: 12.5 });
  } else if (item.commands) {
    slide.addShape(pptx.ShapeType.roundRect, { x: 0.85, y: 1.75, w: 11.6, h: 1.3, rectRadius: 0.08, fill: { color: '111827' }, line: { color: '111827' } });
    item.commands.forEach((c, i) => {
      slide.addText(c[0], { x: 1.25, y: 2.05 + i * 0.45, w: 4.0, h: 0.25, fontFace: 'Consolas', fontSize: 15, bold: true, color: i === 0 ? '93C5FD' : 'BBF7D0', margin: 0 });
      slide.addText(c[1], { x: 5.5, y: 2.06 + i * 0.45, w: 5.4, h: 0.22, fontSize: 13.5, color: C.white, margin: 0 });
    });
    addBullets(slide, item.bullets, 1.0, 3.55, 11.4, { rowH: 0.58, labelW: 1.55, bodySize: 13.2 });
    addCallout(slide, item.callout, 6.2, C.blue);
  } else if (item.metrics && item.no === '09') {
    const statRows = item.stats;
    const cols = [
      [0.85, 1.82, 3.65, 0.7], [4.85, 1.82, 3.65, 0.7], [8.85, 1.82, 3.65, 0.7],
      [0.85, 2.78, 3.65, 0.7], [4.85, 2.78, 3.65, 0.7], [8.85, 2.78, 3.65, 0.7],
    ];
    statRows.forEach((s, i) => {
      const [x, y, w, h] = cols[i];
      slide.addShape(pptx.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.08, fill: { color: C.white }, line: { color: C.line, width: 1.2 } });
      slide.addText(s[1], { x: x + 0.16, y: y + 0.1, w: 1.15, h: 0.35, fontSize: 22, bold: true, color: i === 2 ? C.orange : C.blue, margin: 0 });
      slide.addText(s[0], { x: x + 1.35, y: y + 0.18, w: w - 1.5, h: 0.23, fontSize: 12, bold: true, color: C.text, fit: 'shrink', margin: 0 });
    });
    addBullets(slide, item.bullets, 0.9, 4.25, 11.7, { rowH: 0.58, labelW: 1.55, bodySize: 13 });
  } else if (item.metrics) {
    addMetrics(slide, item.metrics, 0.85, 1.78, 4.0);
    addBullets(slide, item.bullets, 0.95, 3.05, 11.6, { rowH: 0.54, labelW: 1.45, bodySize: item.no === '07' ? 11.8 : 12.4 });
  } else if (item.artifacts) {
    addBullets(slide, item.bullets, 0.85, 1.72, 11.8, { rowH: 0.52, labelW: 1.45, bodySize: 12.8 });
    addArtifactBar(slide, item.artifacts, 5.55);
    addCallout(slide, item.callout, 6.25, C.orange);
  } else {
    addBullets(slide, item.bullets, 0.95, 1.82, 11.8, { rowH: 0.58, labelW: 1.45, bodySize: 13.2 });
    if (item.callout) addCallout(slide, item.callout, 6.25, idx === 9 ? C.green : C.orange);
  }

  addFooter(slide);
  if (item.notes && typeof slide.addNotes === 'function') {
    slide.addNotes(item.notes.split('\n').map(s => s.trim()).filter(Boolean));
  }
});

const outPath = path.join(outDir, 'DeepScientist_Citation_Audit_Agent_final_presentation.pptx');
pptx.writeFile({ fileName: outPath });
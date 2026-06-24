# DeepAlpha 报告追问 V2 设计

## 目标

把当前一次性报告问答升级为可靠的“单报告研究会话”：

- 问答按匿名用户 ID 与报告任务 `task_id` 隔离并持久化。
- 每次回答使用最近 6 轮对话，但原报告始终是事实底座。
- 回答提供可验证的章节级引用，前端可跳转并高亮原文。
- 时效问题自动联网补充，同时区分报告证据与新增网络信息。
- 使用确定性路由选择报告问答、联网补充和策略重点；本阶段不启动多 Agent 编排。

该迭代完成后，再把确定性路由器替换或扩展为 Agent 路由器。

## 范围与非目标

本迭代包含：

1. 问答持久化与历史读取。
2. 最近 6 轮上下文。
3. 报告章节解析、引用校验、前端跳转和高亮。
4. 时效意图识别与自动联网。
5. `auto`、`report_only`、`web` 三种检索模式。
6. 确定性策略路由与路由元数据。
7. 搜索失败降级、数据冲突提示、延迟与 Token 可观测字段。

本迭代不包含：

- 多 Agent 并行分析或辩论。
- 服务端自由规划工具调用。
- 自动交易、仓位或买卖指令。
- 跨报告记忆。
- 对用户上传的任意 Markdown 建立持久会话；直接 Markdown 模式继续保持一次性兼容。

## 身份与数据隔离

继续使用前端已有的 `X-DeepAlpha-User-Id` 匿名用户 ID。服务端通过现有访问校验函数取得规范化后的用户 ID。

持久化会话以 `(user_id, task_id)` 为唯一边界：

- 同一用户对同一报告只有一个会话。
- 不同用户即使使用相同 `task_id`，问答历史也完全隔离。
- 历史读取和删除都必须带当前用户 ID。
- `DEEPALPHA_ACCESS_CODE` 启用时，历史接口与问答接口都必须通过访问码验证。

直接提交 `markdown_report` 的兼容模式不持久化，也不读取历史；需要持久多轮时必须使用成功完成的 `task_id`。

## 数据模型

新增 SQLite 表 `report_chat_sessions`：

- `session_id`
- `user_id`
- `task_id`
- `company_name`
- `created_at`
- `updated_at`
- 唯一约束：`user_id, task_id`

新增 SQLite 表 `report_chat_messages`：

- `message_id`
- `session_id`
- `role`：`user` 或 `assistant`
- `strategy`
- `search_mode`
- `content_json`
- `route_json`
- `created_at`

用户问题与助手结构化回答分别保存为一条消息。一次成功回答后再以事务方式写入用户消息和助手消息，避免 LLM 失败留下半轮历史。

默认永久保留，直到用户主动删除。删除会话时级联删除消息。

## API

### POST `/chat/report`

在现有请求上增加：

```json
{
  "company_name": "Tesla",
  "question": "今天是否有新的风险事件？",
  "task_id": "completed-task-id",
  "strategy": "risk",
  "search_mode": "auto"
}
```

`search_mode`：

- `auto`：默认。识别到时效意图时联网，否则仅使用报告。
- `report_only`：强制仅使用报告与最近 6 轮。
- `web`：强制联网补充。

响应保留现有字段并增加：

```json
{
  "answer": "回答",
  "key_points": [],
  "risks": [],
  "cited_sources": [],
  "data_quality_warning": "",
  "message_id": "uuid",
  "route": {
    "mode": "report_web_qa",
    "strategy": "risk",
    "temporal_intent": true,
    "web_status": "success",
    "reason": "Question asks about today."
  },
  "report_citations": [
    {
      "section_id": "section-12-risk",
      "section_title": "12. 风控审查",
      "excerpt": "原报告中的连续原文摘录",
      "url": "https://example.com/source"
    }
  ],
  "web_citations": [
    {
      "title": "新增网络来源",
      "url": "https://example.com/news",
      "published_at": "2026-06-24",
      "snippet": "与回答直接相关的搜索摘要"
    }
  ],
  "freshness": {
    "report_generated_at": "2026-06-24T04:00:00Z",
    "web_retrieved_at": "2026-06-24T06:00:00Z",
    "answer_cutoff": "2026-06-24T06:00:00Z"
  }
}
```

### GET `/chat/report/{task_id}/history`

返回当前用户在该报告下的完整持久化历史，按时间正序排列。前端刷新后调用此接口恢复会话。

### DELETE `/chat/report/{task_id}/history`

删除当前用户在该报告下的会话与消息，其他用户不受影响。

## 最近 6 轮上下文

一轮等于一个用户问题与对应助手回答。每次生成只读取最近 6 个完整问答轮次：

- 用户问题保留全文。
- 助手历史只注入 `answer`、`key_points`、`risks` 和引用 ID，不重复注入完整来源正文。
- 原始报告章节、结构化画像和来源质量每次单独注入，不依赖历史消息传递事实。
- 若历史消息与原报告冲突，以原报告和本次联网证据为准，并在回答中指出冲突。

服务端不接受客户端提交的历史记录，防止篡改上下文。

## 报告章节解析与引用

新增独立的报告章节解析器，把 Markdown 按标题切分为稳定结构：

```json
{
  "section_id": "section-12-risk",
  "title": "12. 风控审查",
  "content": "章节原文",
  "urls": ["https://example.com/source"]
}
```

`section_id` 由章节顺序与规范化标题组成。前端 Markdown 渲染使用相同算法生成 DOM `id`，保证引用可以定位。

模型只能返回章节 ID 与连续原文摘录。服务端执行二次校验：

- `section_id` 必须存在。
- `excerpt` 规范化空白后必须是对应章节原文的连续子串。
- URL 必须已存在于该章节、报告来源列表或 `source_quality`。
- 校验失败的引用直接移除，不把模型伪造内容展示为证据。

前端点击引用后：

1. 滚动到对应章节。
2. 临时高亮章节。
3. 在引用卡片显示章节标题、摘录和来源链接。

## 时效意图识别

采用确定性规则，不额外调用一次 LLM。

中文触发词包括：

- 最新、今天、今日、现在、当前、刚刚、近期、最近
- 本周、本月、盘前、盘后、截至目前、有没有新消息

英文触发词包括：

- latest、today、now、current、recent、this week、this month
- premarket、after hours、since the report、new update

同时识别明确日期、日期区间和“报告之后”等表达。命中时：

- `search_mode=auto` 路由到联网补充。
- 回答必须显示报告生成时间和联网检索时间。
- 不允许把报告生成后的信息描述为原报告结论。

规则和命中原因通过 `route.reason` 返回，便于后续评测和替换为模型路由。

## 联网补充

联网继续复用现有真实搜索 provider，不创建新的 Agent。

搜索查询由以下内容组成：

- 公司名称与证券代码。
- 用户当前问题。
- 策略关键词。
- 必要时加入当前日期或时间范围。

结果限制为少量高相关来源，按 URL 去重并保留标题、摘要、发布时间、provider 和抓取时间。网络正文不无限抓取，避免延迟和提示词膨胀。

回答提示词明确分区：

1. 原报告章节。
2. 行情、财务与来源质量画像。
3. 最近 6 轮对话。
4. 本次新增网络证据。

输出必须区分“报告原有判断”和“联网新增信息”。

## 联网失败与证据冲突

联网失败不伪造、不返回成功搜索结果，也不因为搜索失败直接让整个问答失败：

- 降级到报告 + 最近 6 轮回答。
- `route.web_status` 标记为 `failed` 或 `no_results`。
- `data_quality_warning` 明确说明无法确认最新情况。
- 若 LLM 本身失败，继续返回明确 HTTP 503。

当网络信息与报告冲突时：

- 不自动覆盖报告结论。
- 回答列出冲突双方、各自时间和来源。
- 在 `risks` 或数据质量提醒中说明需要人工复核。
- 来源不明、无 URL 或发布时间不可确认的网络结果不能用于形成“最新事实”。

## 确定性路由

新增纯函数路由器，输入为问题、`strategy`、`search_mode`，输出：

```json
{
  "mode": "report_qa | report_web_qa",
  "strategy": "general | risk | valuation | technical | news",
  "temporal_intent": true,
  "reason": "规则命中说明"
}
```

路由规则：

1. `report_only` 永不联网。
2. `web` 始终联网。
3. `auto` 且命中时效意图时联网。
4. 其他情况仅使用报告。
5. `strategy` 只改变分析重点，不决定是否联网。

这层接口保持稳定。后续 Agent 路由阶段可以增加：

- 模型意图分类。
- 财务、估值、技术、新闻工具路由。
- 并行专家 Agent。
- 证据审查 Agent。

但调用方继续消费同一 `route` 结构。

## 前端

报告页追问区域增加：

- “自动 / 仅报告 / 联网补充”模式选择。
- 历史恢复和“清空对话”。
- 最近会话按时间展示。
- 报告引用卡片，可跳转、高亮章节。
- 网络引用使用不同视觉标签。
- 报告生成时间、联网检索时间和数据截止时间。
- 联网中、联网失败降级、LLM 失败三种独立状态。

生成新报告时切换到新的 `(user_id, task_id)` 会话，不把旧报告历史带入。

## 可观测性

每次问答记录：

- `task_id`、匿名 `user_id` 的不可逆摘要。
- 路由模式与命中原因。
- 策略和检索模式。
- 历史轮数。
- 搜索结果数与搜索状态。
- 报告引用数、网络引用数、被过滤引用数。
- 搜索耗时、LLM 耗时和总耗时。
- 若 provider 返回 usage，记录输入与输出 Token；不记录密钥。

日志不记录完整报告、完整问题、访问码或用户原始标识。

## 测试与验收

后端测试覆盖：

1. 同一用户同一任务恢复历史。
2. 不同用户同一任务历史隔离。
3. 成功回答以事务写入完整一轮。
4. LLM 失败不保存半轮。
5. 第 7 轮请求只注入最近 6 轮。
6. 直接 Markdown 模式保持无状态。
7. 章节解析与稳定 ID。
8. 合法摘录保留，伪造章节、摘录和 URL 被过滤。
9. 中英文时效问题在 `auto` 模式触发联网。
10. `report_only` 禁止联网，`web` 强制联网。
11. 搜索失败降级并返回明确警告。
12. LLM 失败继续返回 HTTP 503。
13. 历史读取与删除只影响当前用户。

前端验收覆盖：

1. 刷新页面后恢复历史。
2. 新报告不会混入旧历史。
3. 点击引用滚动并高亮对应章节。
4. 报告引用与网络引用视觉区分。
5. 搜索、降级和 LLM 错误状态可区分。
6. 生产构建通过。

## 分阶段交付

### 本迭代：可靠多轮与时效联网

- 持久化。
- 最近 6 轮。
- 章节级引用。
- 时效识别。
- 自动联网与手动模式。
- 确定性路由。

### 下一迭代：Agent 路由

- 使用评测数据判断何时需要估值、技术、新闻或风险专家。
- 在确定性路由接口后增加模型分类或 Planner。
- 对高风险问题增加证据审查 Agent。
- 保持单报告事实边界、引用校验和失败显式化。

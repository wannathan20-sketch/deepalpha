# DeepAlpha 报告追问 / 策略问股 MVP 设计

## 目标

在现有投研报告生成流程之后增加一次性、围绕当前报告的可靠问答能力。该 MVP 不维护服务端多轮会话，不启动新的多 Agent 工作流，也不主动补抓外部数据。

用户可以通过已完成的报告任务 `task_id`，或直接提交 `markdown_report`，向当前配置的 LLM 提问。回答必须保持结构化，并明确披露上下文和数据质量限制。

## API 契约

新增 `POST /chat/report`。

请求体：

```json
{
  "company_name": "Tesla",
  "question": "当前最需要警惕的风险是什么？",
  "task_id": "optional-completed-report-task-id",
  "markdown_report": "optional-report-markdown",
  "strategy": "risk"
}
```

约束：

- `company_name` 与 `question` 必填且去除首尾空白后不能为空。
- `strategy` 默认为 `general`，只允许 `general`、`risk`、`valuation`、`technical`、`news`。
- `task_id` 和 `markdown_report` 至少提供一个。
- 两者同时提供时优先使用 `task_id`，避免客户端 Markdown 与服务端已保存报告不一致。
- `task_id` 不存在返回 HTTP 404。
- 任务未成功完成或结果中没有报告返回 HTTP 400。
- 仅传 `markdown_report` 时，不主动查询行情、财务或新闻；缺失信息会反映在 `data_quality_warning` 中。

响应体：

```json
{
  "answer": "核心回答文本",
  "key_points": ["要点一"],
  "risks": ["风险一"],
  "cited_sources": [
    {
      "title": "来源标题",
      "url": "https://example.com/source"
    }
  ],
  "data_quality_warning": "数据质量或时效限制说明"
}
```

`cited_sources` 只允许返回当前报告或 `source_quality` 中已有的来源，不允许模型生成上下文之外的链接。没有可靠来源时返回空数组。

## 后端结构

新增 `app/services/report_chat.py`，职责保持单一：

1. 从完成的报告任务或直接 Markdown 建立问答上下文。
2. 提取并限制报告、`market_profile`、`financial_profile`、`source_quality` 的输入规模。
3. 根据 `strategy` 选择轻量提示词侧重点。
4. 调用现有 `app.llm.client.generate_text`。
5. 解析、校验并规范化模型的 JSON 输出。
6. 对引用来源做白名单过滤，只保留报告上下文中真实存在的 URL。

`app/main.py` 只负责请求校验、访问控制、任务读取和调用服务，不加入问答业务细节。

为了让 `task_id` 模式拿到结构化上下文，现有报告任务成功结果会在兼容原字段的基础上增加：

- `market_profile`
- `financial_profile`

`source_quality` 已存在，前端现有消费方式不变。

## 策略行为

策略不改变数据源，也不创建不同 Agent，只调整回答重点：

- `general`：综合结论、证据、反例与边界。
- `risk`：下行风险、触发条件、数据缺口和需跟踪指标。
- `valuation`：估值假设、关键变量、情景敏感性；缺乏估值数据时必须直说。
- `technical`：趋势、均线、波动与价格区间；不得在无行情数据时虚构技术指标。
- `news`：报告中已有事件、时效性与潜在影响；不得声称掌握报告生成后的新闻。

系统提示词要求模型仅依据提供的上下文回答，不构成投资建议，不输出交易指令，并严格返回 JSON 对象。

## 错误处理与生产可靠性

- `generate_text` 抛出的 `LLMProviderError` 不捕获为业务成功，由现有全局异常处理器返回 HTTP 503。
- 生产环境继续禁止 mock 兜底。
- 模型返回空内容、非 JSON 或不满足结构时，转换为 `LLMProviderError`，因此接口返回 HTTP 503，而不是伪造答案。
- 开发环境可以沿用当前 mock LLM 配置，但问答服务不会为不可解析的 mock 文本构造虚假回答；测试通过替换 LLM 调用验证业务行为。
- 报告上下文缺失属于客户端请求错误，不调用 LLM。

## 前端

在报告展示区域的 Markdown 报告下方增加“继续追问”区块：

- 策略下拉框。
- 单行或简洁多行输入框。
- 提交按钮。
- 本次报告页面内的问答历史列表。
- 独立的 loading 和 error 状态。

每条历史记录展示问题、策略、回答、关键要点、风险、引用来源和数据质量提醒。

生成新报告时清空旧问答历史，防止跨报告污染。前端优先提交当前 `reportTask.task_id`；若任务标识不可用，则提交当前 `reportResult.markdown_report`。

本 MVP 不把问答历史写入数据库，刷新页面后历史消失。

## 测试

后端至少覆盖：

1. 正常问答：完成的 `task_id` 能组装报告、行情、财务和来源质量上下文，并返回规范结构。
2. 无报告上下文：既无 `task_id` 又无 `markdown_report` 时返回校验错误；不存在或未完成任务返回明确错误。
3. LLM 失败：`LLMProviderError` 经 API 返回 HTTP 503，不产生 mock 回答。
4. 策略参数：五种合法策略可用，非法值返回 HTTP 422，且策略重点进入提示词。
5. 引用过滤：模型给出的未知 URL 被移除。

前端通过生产构建验证 JSX 与状态流；现有前端没有组件测试框架，本 MVP 不为单个区块引入新的测试依赖。

## README

README 增加：

- `POST /chat/report` 路由说明。
- `task_id` 与 `markdown_report` 两种调用示例。
- 策略枚举与响应字段说明。
- 数据时效、单报告上下文和生产环境 503 行为说明。

## 非目标

- 服务端多轮记忆。
- 自动联网补充新闻或行情。
- 多 Agent 辩论或策略路由图。
- 交易执行、仓位建议或买卖指令。
- 问答历史持久化。

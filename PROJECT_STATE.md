# DeepAlpha 项目状态

## 1. 项目目标

DeepAlpha，中文名“深研 Alpha”，目标是构建一个面向公司研究场景的多智能体虚拟投研团队。

系统围绕用户输入的公司名称，自动完成公司名称到股票代码的匹配、行情 K 线展示、研究计划制定、RAG 检索、多 Agent 分析、风险审查、综合决策、引用检查、Trace 追踪、历史记忆沉淀和投研报告生成。

当前定位是“研究辅助与投研工作流原型”，不是交易系统，也不提供投资建议、交易指令或收益承诺。客户侧使用时需要保留风险提示，并要求用户结合公司公告、交易所披露、财报和专业判断复核。

## 2. 当前架构

当前系统由以下部分组成：

- FastAPI 后端：负责 API、异步报告任务、Memory、限流、缓存、日志和前端数据接口。
- LangGraph 工作流：负责多 Agent 编排和 thread-level short-term memory。
- Agent 层：Planner、Industry、Fundamental、Financial、Valuation、Technical、News、Sentiment、Bull、Bear、Trader、Risk、Source Quality、Report Editor、Committee。
- RAG 层：Tavily/mock 搜索结果进入 Chroma，本地 hash embedding 支撑最小可运行检索。
- Market Data 层：公司名称解析、本地股票主表、Yahoo 行情摘要兜底、TradingView 前端图表、6 个月行情摘要、MA20/MA60、趋势和波动率计算。
- Financial Data 层：美股 SEC EDGAR companyfacts MVP，支持 ticker -> CIK -> 最新 10-K/10-Q/20-F metadata -> US GAAP/IFRS 核心 XBRL 财务字段提取。
- Memory 层：SQLite 保存历史报告和 Watchlist，预留 tenant/user 字段。
- React/Vite 前端：三栏投研工作台、公司搜索、候选股票、K 线 provider、报告结果、历史记录、PDF 导出。
- Streamlit 旧前端：`frontend.py` 保留为轻量调试入口。

核心流程：

```text
用户输入公司名称
↓
前端自动解析股票代码与候选股票
↓
前端展示 TradingView K 线，并提供 TradingView 搜索/图表跳转
↓
POST /report/tasks 创建异步报告任务
↓
FastAPI 拉取行情摘要并启动 LangGraph
↓
Planner
↓
RAG Retriever
↓
Industry Analyst
↓
Fundamental Analyst
↓
Financial Analyst
↓
Valuation Analyst
↓
Technical Analyst
↓
News Analyst
↓
Sentiment Analyst
↓
Bull Analyst
↓
Bear Analyst
↓
Trader Agent
↓
Risk Manager
↓
Source Quality Agent
↓
Committee Agent
↓
Report Editor Agent
↓
Markdown Report Generator
↓
Citation Checker
↓
前端轮询任务状态并展示报告
↓
用户可导出 PDF
```

主要 API：

- `GET /health`：健康检查。
- `GET /config`：运行配置诊断，不返回真实 API Key。
- `GET /debug/architecture`：架构诊断，受 `ENABLE_DEBUG_ROUTES` 控制。
- `GET /debug/rag`：RAG/Chroma 检索诊断，受 `ENABLE_DEBUG_ROUTES` 控制。
- `GET /symbol/lookup`：公司名到股票代码自动解析。
- `GET /market/chart`：Yahoo/auto 行情摘要数据；前端主要使用 TradingView 图表。
- `GET /financials/latest`：SEC companyfacts 最新财报摘要，覆盖美股本土公司和部分 ADR/外国发行人。
- `POST /analyze`：开发调试用完整分析接口。
- `POST /report`：同步报告接口。
- `POST /report/tasks`：异步报告任务创建。
- `GET /report/tasks/{task_id}`：异步报告任务状态查询。
- `GET /memory/history`：历史报告记录。
- `POST /memory/watchlist`：添加 Watchlist。
- `GET /memory/watchlist`：获取 Watchlist。

## 3. 已完成内容

后端基础：

- FastAPI 项目骨架。
- Pydantic schemas。
- CORS 配置，支持生产环境正则限制。
- `/config` 运行模式诊断。
- debug 路由可通过 `ENABLE_DEBUG_ROUTES=false` 关闭。
- Dockerfile、`.dockerignore`、`.gitignore`。
- pytest API 测试，目前 `27 passed, 1 warning`。

多 Agent 与 LangGraph：

- 已迁移到 `StateGraph`。
- `DeepAlphaState` 统一承载工作流状态。
- `InMemorySaver` 支持 thread-level short-term memory。
- `safe_run_agent` 提供 Agent 失败降级。
- Trace step 记录每个节点执行状态。
- 关键 Agent 已开始结构化输出，新增 `verdict`、`claims`、`risks`、`watch_items`、`data_quality` 字段。
- `Fundamental / Financial / Valuation / Technical / News / Risk / Source Quality / Report Editor / Committee` 已接入结构化输出协议。

RAG 与检索：

- Tavily/mock Search Tool。
- Chroma Vector Store。
- 本地 hash embedding，避免额外下载模型。
- Chroma 不可用时回退到内存关键词检索。
- `/debug/rag` 可查看 query、chunks、sources 和 vector store 状态。

LLM：

- 支持 `LLM_PROVIDER=mock`。
- 支持 OpenAI。
- 支持 DeepSeek OpenAI-compatible 模式。
- LLM 调用失败时自动 fallback 到 mock，不中断主流程。

行情与股票代码：

- `/symbol/lookup` 支持公司名、中文别名、英文名和股票代码自动解析股票代码。
- 本地 `STOCK_MASTER` 股票主表覆盖常见美股、港股、A 股名称，并已补充美光、MRVL、诺基亚等演示标的；诺基亚同时提供 `NYSE:NOK` ADR 和 `OMXHEX:NOKIA` 赫尔辛基主上市候选。
- Yahoo Finance search 仅作为补充扩大自动匹配范围；由于线上可能被限流，核心体验不依赖 Yahoo。
- `/market/chart` 支持 `auto`、`yahoo` provider。
- 前端 K 线保留 `Auto` / `TradingView` 切换，并提供 TradingView 外部链接；没有匹配到股票时可跳转 TradingView 搜索。
- 后端报告生成前会基于请求中的 symbol/yahoo_symbol/provider 构建 6 个月行情摘要。
- Technical Agent 和报告正文已接入 latest close、6M return、high/low、MA20/MA60、trend、volatility。

SEC 财报数据：

- 新增 `app/tools/sec_filings.py`，支持 SEC company ticker mapping、companyfacts 和 latest submissions metadata。
- 新增 `app/services/financials.py`，从 companyfacts 中提取 Revenue、Gross Profit、Operating Income、Net Income、EPS、Operating Cash Flow、CapEx、Cash、Debt、Assets、Liabilities、Equity，并计算毛利率、营业利润率、净利率、FCF 和可比期变化。
- SEC 财报抽取已支持 `10-K`、`10-Q`、`20-F` 和 `40-F`；外资发行人/ADR 可读取 `ifrs-full` taxonomy，并保留财报币种，避免把 ADR 交易币种和报表币种混淆。
- 新增 `GET /financials/latest`，返回最新 SEC 财报摘要并加入缓存、限流和结构化日志。
- 报告生成前会构建 `financial_profile` 并注入 LangGraph context。
- Financial Analyst 和 Valuation Analyst 已优先使用 SEC 财务事实作为财务分析和估值约束。
- Committee Agent 已接入 SEC `financial_profile`，最终综合判断会把财务事实作为约束条件。
- SEC companyfacts 字段抽取已增加 latest filing/report date 锚点；资产负债表类 instant metric 只接受贴近最新财报日的字段，避免把多年以前的债务、现金等字段混入最新财报摘要。
- Markdown 报告新增“财报数据摘要”，Executive Summary 新增“财报锚点”。
- React 工作台中间列新增“最新财报”区块，展示财报类型、财报期、报表币种、收入、净利润、毛利率、营业利润率、经营现金流、EPS、现金、债务和 SEC 来源链接。

Memory：

- 历史报告和 Watchlist 已从 JSON 文件迁移到 SQLite。
- 默认数据库路径：`data/deepalpha.sqlite3`。
- 可通过 `DEEPALPHA_DB_PATH` 配置。
- 表结构已预留 `tenant_id` 和 `user_id`。
- 再次分析同一公司时会读取最近历史记录作为 memory context。

缓存、限流与日志：

- Symbol lookup 增加 TTL cache。
- Market chart 增加 TTL cache。
- SEC financials 增加 TTL cache。
- Symbol lookup、Market chart 和 SEC financials 增加基础 rate limit。
- 报告任务、行情、symbol lookup、SEC financials 输出 JSON 结构化日志。

前端：

- React/Vite 正式前端。
- Tailwind CSS + Lucide Icons。
- 保持左/中/右三栏工作台：
  - 左侧：推荐标的与 Watchlist。
  - 中间：公司搜索、候选股票、行情 provider、K 线、报告生成。
  - 右侧：报告结果、历史报告记录、PDF 导出。
- 公司名称输入后自动解析股票代码，并展示候选股票。
- 单一高置信候选会自动选中，避免 K 线 symbol 为空。
- K 线区域支持 TradingView Advanced Chart 嵌入，并提供 TradingView 搜索/图表跳转。
- 已移除 Thread ID 输入和 Analyze Debug 主界面按钮。
- 技术说明入口放在右上角，并受 `ENABLE_DEBUG_ROUTES` 控制。
- 前端 API 地址支持 `VITE_API_BASE`。
- 客户首次访问显示风险确认弹窗。
- 报告区域保留非投资建议提示。
- 报告 Markdown 渲染已支持标题、列表、粗体、链接。
- 来源链接会渲染为可点击超链接。
- 支持浏览器打印导出 PDF。
- PDF 打印样式单独处理，隐藏工作台，只输出报告。

文档与部署：

- README 已包含本地运行、React 前端、生产环境变量、CORS、debug 开关、SQLite、缓存、限流、异步报告任务说明。
- `frontend/.env.example` 已提供 `VITE_API_BASE`。
- `.dockerignore` 排除本地缓存、数据库、前端依赖和构建产物。
- 前端已部署到 Vercel，并绑定 `https://deepalpha.best`。
- 后端已部署到 Zeabur，健康检查路径为 `https://deepalpha.zeabur.app/health`。
- 2026-06-03 已完成 SEC financials MVP 上线：上线提交为 `3348b103fe1806c5234a1fb037991c80d1be14ab`，前端 Vercel 生产部署已切到新 bundle，后端 Zeabur 已部署新接口。
- 线上验收已通过：`GET /health` 返回 200，`GET /financials/latest?symbol=TSLA&exchange=NASDAQ` 返回 200，生产前端“最新财报”区块可展示 SEC 财务指标。
- 前端生产依赖 `npm audit --omit=dev` 为 0 个漏洞。
- GitHub 上传安全检查已完成：当前仓库为 public；未发现真实 `.env`、数据库、Chroma、`.vercel`、构建产物、真实 DeepSeek/Tavily/OpenAI key 被提交；远端 `origin/main` 与本地 HEAD 一致。
- 已新增 GitHub Actions CI：push/PR 时分别运行后端 `pytest -q` 和前端 `npm ci && npm run build`。
- `requirements.txt` 已固定为当前验证过的 Python 依赖版本，降低部署时上游包升级造成的不确定性。

## 4. 未完成内容

投研专业度：

- Financial Analyst 已接入工作流并读取 SEC 结构化财报摘要；HKEX/A 股公告、分业务数据和管理层指引仍需后续数据源补充。
- Valuation Analyst 已接入工作流，但 PE、PS、EV/EBITDA、可比公司估值、Bull/Base/Bear 目标区间仍依赖更权威的财务和市值数据源。
- Source Quality Agent 已接入工作流，当前以启发式来源分级为主，仍需要更严格的来源时效、公告优先级和逐条证据评分。
- Report Editor Agent 已接入工作流，当前可做最终报告整理，但仍可继续强化去重、去口语化、Markdown 清理和标题层级统一。
- Committee 仍缺少强约束评分模型和估值约束。
- 报告仍可能出现来源时效混乱，需要数据 freshness 校验。

数据源：

- SEC companyfacts 已完成 MVP；SEC 原文风险条款、管理层指引、电话会纪要、HKEX/A 股公告尚未正式接入。
- 新闻正文抓取、网页正文抽取和高质量行业数据库尚未接入。
- Yahoo 行情只作为公开行情摘要的补充兜底，线上可能被限流，不应作为核心依赖。
- TradingView 当前作为前端 K 线展示和外部跳转入口，不作为后端 OHLC 数据源。
- K 线 provider 目前不含富途、致富证券、同花顺等需授权或非公开接口的 provider。

RAG：

- 当前 hash embedding 只适合最小闭环，不适合高质量语义检索。
- 缺少 chunking、去重、metadata schema、rerank。
- Citation Checker 仍偏粗粒度，尚未逐句校验。

工程化：

- GitHub 仓库当前为 public；后续如果加入客户资料、内部 Prompt、真实数据样例或商业敏感逻辑，建议改为 private。
- Zeabur 生产环境变量曾由 CLI 回显过，虽然未进入 GitHub，但建议轮换 DeepSeek Key、Tavily Key 和 `DEEPALPHA_ACCESS_CODE`。
- `DEEPALPHA_ACCESS_CODE` 需要使用更强随机字符串，不应使用短数字或弱口令。
- `requirements.txt` 已 pin 顶层依赖版本，但尚未生成完整传递依赖 lock/constraints 文件。
- 前端已有 `package-lock.json`，后端仍可进一步补充 `requirements.lock.txt` 或 constraints 文件。
- 异步报告任务状态仍在进程内内存中，不适合多进程/多实例部署。
- 尚未接 Redis、队列系统或后台任务框架。
- 尚未接登录、租户隔离、权限控制。
- 尚未接生产级监控、告警和错误追踪。
- 已有基础 CI，尚未接入生产部署前强制检查、分支保护和自动回滚。
- 缺少前端端到端测试。
- 缺少 LangGraph 节点级测试和 Agent 输出 schema 单元测试。

产品化：

- 历史报告详情仍可继续增强。
- Watchlist 缺少分组、标签、提醒、最近结论变化。
- 报告已有 Executive Summary 雏形，但仍需强化评级、核心矛盾、关键催化、关键风险和后续跟踪指标的一页式表达。
- PDF 导出依赖浏览器打印，尚未提供后端服务端 PDF 渲染。
- 移动端体验尚未系统优化。

## 5. 文件结构

主要结构如下，已省略 `__pycache__`、`node_modules` 和构建缓存：

```text
.
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── schemas.py
│   ├── graph.py
│   ├── config.py
│   ├── trace.py
│   ├── utils.py
│   ├── report_generator.py
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── planner.py
│   │   ├── industry_analyst.py
│   │   ├── fundamental_analyst.py
│   │   ├── financial_analyst.py
│   │   ├── valuation_analyst.py
│   │   ├── technical_analyst.py
│   │   ├── news_analyst.py
│   │   ├── sentiment_analyst.py
│   │   ├── bull_analyst.py
│   │   ├── bear_analyst.py
│   │   ├── trader.py
│   │   ├── risk_manager.py
│   │   ├── source_quality.py
│   │   ├── report_editor.py
│   │   ├── committee.py
│   │   ├── citation_checker.py
│   │   └── llm_helpers.py
│   ├── llm/
│   │   ├── __init__.py
│   │   └── client.py
│   ├── memory/
│   │   ├── __init__.py
│   │   └── store.py
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── loader.py
│   │   ├── retriever.py
│   │   └── vector_store.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── cache.py
│   │   ├── citation_checker.py
│   │   ├── financials.py
│   │   ├── logging.py
│   │   ├── market_summary.py
│   │   └── rate_limit.py
│   └── tools/
│       ├── __init__.py
│       ├── sec_filings.py
│       ├── search.py
│       ├── symbol_lookup.py
│       └── market_data.py
├── data/
│   ├── deepalpha.sqlite3
│   └── chroma/
├── frontend/
│   ├── .env.example
│   ├── index.html
│   ├── package.json
│   ├── package-lock.json
│   ├── postcss.config.js
│   ├── tailwind.config.js
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       └── styles.css
├── tests/
│   └── test_api.py
├── frontend.py
├── Dockerfile
├── requirements.txt
├── README.md
├── .env.example
├── .env.zeabur.example
├── .gitignore
├── .dockerignore
├── render.yaml
└── PROJECT_STATE.md
```

关键文件职责：

- `app/main.py`：FastAPI API 层、任务接口、Memory API、行情与 symbol API。
- `app/graph.py`：LangGraph 工作流编排。
- `app/report_generator.py`：Markdown 报告生成。
- `app/agents/llm_helpers.py`：Agent 文本清洗、结构化输出 helpers。
- `app/tools/symbol_lookup.py`：公司名到股票代码匹配。
- `app/tools/market_data.py`：Yahoo/auto 行情摘要 provider；TradingView 由前端嵌入展示。
- `app/tools/sec_filings.py`：SEC ticker -> CIK、companyfacts 和 latest filing metadata 工具。
- `app/services/market_summary.py`：行情摘要指标计算。
- `app/services/financials.py`：SEC companyfacts 财务字段抽取、指标计算和 `financial_profile` 生成。
- `app/memory/store.py`：SQLite 历史记录和 Watchlist。
- `frontend/src/App.jsx`：React 工作台主界面。
- `frontend/src/styles.css`：Tailwind 入口、报告链接、打印 PDF 样式。
- `tests/test_api.py`：后端 API 回归测试。

## 6. 关键设计决策

LangGraph 作为主编排层：

- 多 Agent 流程不写死在 API 层。
- `main.py` 只负责请求、响应、任务状态和外围服务。
- `graph.py` 负责工作流节点和状态传递。
- Agent 保持独立文件，便于替换、测试和增删。

保留 mock/fallback：

- 没有 API Key 时系统仍可运行。
- OpenAI、DeepSeek、Tavily 调用失败不会让 `/analyze` 或 `/report` 崩溃。
- 这让项目适合演示、教学和本地开发，但真实交付需要配置可信数据源。

API 分层：

- `/analyze` 面向开发调试，返回完整状态。
- `/report` 面向同步报告生成。
- `/report/tasks` 面向前端和客户体验，避免长请求超时。
- `/debug/*` 面向技术诊断，生产环境可关闭。

Memory 使用 SQLite：

- SQLite 比 JSON 更适合历史报告和 Watchlist 的增量演进。
- 当前仍是单机方案，但已预留 `tenant_id` 和 `user_id`。
- 后续可迁移到 Postgres。

行情 provider 保持可替换：

- 后端当前实现 Yahoo/auto，用于尽力构建行情摘要；Yahoo 不稳定时前端仍可展示 TradingView 图表。
- 前端保留 Auto/TradingView 切换，并提供 TradingView 搜索/图表跳转。
- TradingView 作为前端图表源，不作为后端数据源。
- 富途、致富证券、同花顺等需要授权、网关或官方接口后再接入。

Agent 输出逐步结构化：

- 不一次性重写所有 Agent，先保持 `summary/key_points/sources` 兼容。
- 新增 `claims/risks/watch_items/data_quality`，让报告生成器逐步从“拼文本”转向“拼结构”。
- 已补充 Financial、Valuation、Source Quality 和 Report Editor，下一步重点是接入权威财报数据、估值数据和 schema 校验。

客户侧合规优先：

- 首页一次性风险确认。
- 报告区域保留非投资建议提示。
- PDF 中保留风险提示。
- 生产环境默认建议关闭 debug 路由并限制 CORS。

前端坚持工作台而不是营销页：

- 首页直接进入可用投研工作台。
- 保持左/中/右三栏布局，适合重复搜索、比较和生成报告。
- 技术说明放在右上角，不占用主页核心投研区域。

## 7. 下一步开发计划

第一优先级：接入最新财报并提升报告专业度

- 继续强化 SEC companyfacts 字段 fallback、周期选择和同比/环比口径。
- 在 Committee 中形成更强约束评分模型，而不是仅将财务事实放入提示词。
- 新增 SEC 原文 10-K/10-Q 风险条款、管理层讨论和管理层指引摘要。
- 强化一页式 Executive Summary：评级、核心矛盾、关键催化、关键风险、后续跟踪指标。
- 将报告生成器进一步改为结构化模板，减少 Agent 原文直出。

第二优先级：强化投研核心模块

- 强化 `Financial Analyst`：接入财务报表、分业务收入、利润率、现金流和趋势判断。
- 强化 `Valuation Analyst`：接入估值倍数、可比公司、Bull/Base/Bear 情景。
- 强化 `Source Quality Agent`：来源分级、时效判断、低质量来源警告。
- Committee Agent 接入财务和估值结果后再输出最终评级。

第三优先级：数据源升级

- 接入公司公告、交易所披露、HKEX 年报/季报和电话会纪要。
- 接入更强网页正文抽取和新闻正文抓取。
- 替换 hash embedding 为真实 embedding。
- RAG 增加 chunk metadata、去重和 rerank。
- Citation Checker 升级为逐段或逐句引用校验。

第四优先级：生产化架构

- 轮换生产 DeepSeek Key、Tavily Key 和 `DEEPALPHA_ACCESS_CODE`，并把访问码改成 24 位以上随机字符串。
- 为 GitHub `main` 增加分支保护，禁止未验证直接推送到生产分支。
- 将 GitHub Actions 设为必需检查，并接入生产部署前 gate。
- 生成完整 Python 传递依赖 lock，例如 `requirements.lock.txt` 或 constraints 文件。
- 根据项目商业敏感度决定是否将 GitHub 仓库改为 private。
- 将 `REPORT_TASKS` 从进程内内存迁移到 Redis/Postgres。
- 增加后台任务队列。
- 增加认证、用户体系和多租户隔离。
- 增加生产日志、错误监控、告警和审计日志。
- 增加 Docker Compose，统一启动后端、前端、数据目录和可选 Redis/Postgres。

第五优先级：测试与质量

- 增加 Agent 输出 schema 单元测试。
- 增加 LangGraph 节点级测试。
- 增加前端端到端测试，覆盖公司搜索、候选股票、provider 切换、报告生成、PDF 导出。
- 增加 CI，自动运行 pytest 和 `npm run build`。

第六优先级：产品体验

- Watchlist 增加分组、标签、最近结论变化和提醒。
- 历史报告增加详情页和对比功能。
- 报告 PDF 增加封面、目录和页眉页脚。
- 移动端布局专项优化。

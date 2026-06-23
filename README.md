# DeepAlpha

![CI](https://github.com/wannathan20-sketch/deepalpha/actions/workflows/ci.yml/badge.svg)

DeepAlpha 是一个面向 A 股、港股和美股的多智能体投研系统。用户输入公司或证券代码后，系统会拉取行情、财务、新闻与行业检索数据，交给一组专业分析 Agent 协作，最终生成带来源、数据质量说明和风险提示的 Markdown 投研报告。

当前项目定位是“研究辅助工具”和“投研工作流原型”。它可以帮助整理公开信息、形成分析框架、暴露数据缺口，但不提供投资建议、交易指令或收益承诺。

## 核心能力

- 多市场支持：A 股、港股、美股的证券识别、行情路由和图表展示。
- 多 Agent 工作流：规划、行业、基本面、财务、估值、技术、新闻、情绪、多空辩论、交易观点、风险审查、来源质量和委员会总结。
- 多源检索：支持 Brave Search、BlockBeats、Tavily；生产环境搜索失败时标记数据缺失，不用 mock 伪造来源。
- 财务数据：美股接入 SEC EDGAR companyfacts；A 股和港股接入 AkShare 可用财务摘要与公告接口，按字段稳定性标记数据质量。
- 数据质量层：用 `AnalysisContextPack` 标记 `available`、`fallback`、`partial`、`missing`、`not_supported`、`fetch_failed` 等状态。
- 报告可靠性：引用覆盖检查、来源质量评估、Agent trace、Markdown 报告编辑和风险提示。
- 生产约束：`APP_ENV=production` 下禁止 mock LLM 和 mock 搜索；LLM 失败返回明确错误，搜索失败记录为缺失数据。
- 前端工作台：React/Vite 三栏界面，支持公司搜索、候选证券、K 线图、报告生成、历史记录和 Watchlist。

## 适用场景

- 个人或小团队做公开市场研究辅助。
- 验证多 Agent 投研流程、RAG 检索和数据质量治理。
- 搭建内部演示版的股票研究工作台。

不适合作为自动交易系统、投资顾问系统或不经人工复核的生产决策引擎。

## 系统流程

```mermaid
flowchart LR
    A["用户输入公司 / 证券代码"] --> B["证券识别与市场判断"]
    B --> C["行情、财务、新闻与行业检索"]
    C --> D["AnalysisContext 数据质量层"]
    D --> E["Planner"]
    E --> F["专业分析 Agent"]
    F --> G["Bull / Bear Debate"]
    G --> H["Trader / Risk Manager"]
    H --> I["Source Quality / Committee"]
    I --> J["Citation Check / Report Editor"]
    J --> K["Markdown 投研报告"]
```

## 技术栈

| 模块 | 技术 |
| --- | --- |
| 后端 | Python、FastAPI、Pydantic |
| Agent 编排 | LangGraph |
| LLM | DeepSeek、OpenAI、开发测试 mock |
| 检索 | Brave Search、BlockBeats、Tavily、Chroma |
| 行情 | AkShare、Yahoo Finance、Finnhub、Efinance、Baostock |
| 财务 | SEC EDGAR companyfacts、AkShare |
| 存储 | SQLite、Chroma |
| 前端 | React、Vite、Tailwind CSS、Lucide Icons |
| 测试 / CI | pytest、GitHub Actions、Vite build |

## 数据源与覆盖范围

### 行情数据

`data_provider=auto` 时，系统会按市场选择 provider 链。每次尝试都会记录在 `provider_attempts` 中，方便判断数据是主来源、降级来源还是失败。

| 市场 | 默认顺序 | 说明 |
| --- | --- | --- |
| A 股 | AkShare -> Efinance -> Baostock -> Yahoo | AkShare 是核心来源；Efinance、Baostock 为可选增强 |
| 港股 | Yahoo -> AkShare | Yahoo 优先，失败后尝试 AkShare |
| 美股 | Yahoo -> Finnhub | Finnhub 需要 `FINNHUB_API_KEY` |

显式指定 provider 时不会自动切换到其他来源。

### 财务、新闻与检索

| 数据类型 | 来源 | 当前边界 |
| --- | --- | --- |
| 美股财务 | SEC EDGAR companyfacts | 覆盖美国上市公司和部分提交 20-F 的外国发行人；SEC 元数据失败时保留结构化事实并标记 `partial` |
| A 股财务与公告 | AkShare 东方财富/新浪可用接口 | 提取最近财务摘要中的收入、净利润、毛利率、净利率、ROE、资产负债率、经营现金流等可映射字段，并附最近财报公告链接；字段缺失标记 `partial`，接口无记录标记 `missing`，调用失败标记 `fetch_failed` |
| 港股财务与公告 | AkShare 东方财富港股财务与公告接口 | 优先返回公告/财报链接和可稳定映射的基础摘要；结构化字段不稳定时只返回真实可得字段，并在 `missing_fields` 中标明缺口，不用估算或 mock 补数 |
| 通用网页搜索 | Brave Search、Tavily | 需要 API Key |
| 垂直资讯 | BlockBeats | 适合 Web3、加密市场相关信息，需要 API Key |
| 本地开发 | mock provider | 仅限开发和自动化测试 |

## 快速开始

### 后端

建议使用 Python 3.11 或 3.12。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

默认 `.env.example` 使用开发模式，可在没有真实 LLM 和搜索 API Key 的情况下启动。

服务地址：

- API: `http://127.0.0.1:8000`
- OpenAPI: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/health`

### 前端

```bash
cd frontend
npm install
npm run dev
```

默认连接本地后端 `http://127.0.0.1:8000`。连接远程后端时，在 `frontend/.env` 中设置：

```env
VITE_API_BASE=https://api.example.com
```

## 环境变量

完整示例见 [`.env.example`](.env.example) 和 [`.env.zeabur.example`](.env.zeabur.example)。不要提交真实 `.env`、API Key 或访问码。

### LLM

推荐生产环境使用 DeepSeek：

```env
APP_ENV=production
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

也可以使用 OpenAI：

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-5
```

生产环境规则：

- `LLM_PROVIDER` 必须是 `deepseek` 或 `openai`。
- 对应 API Key 必须存在。
- LLM 调用失败时报告接口返回 HTTP 503。
- mock LLM 只允许在开发和测试环境使用。

### 搜索

```env
SEARCH_PROVIDER=multi
SEARCH_PROVIDERS=brave,blockbeats,tavily
SEARCH_MAX_WORKERS=4
BRAVE_SEARCH_API_KEY=your_brave_search_api_key
BLOCKBEATS_API_KEY=your_blockbeats_api_key
TAVILY_API_KEY=your_tavily_api_key
```

生产环境至少需要配置一个可用搜索 Key。全部真实搜索来源失败时，RAG 上下文会标记为 `fetch_failed`，报告不会用 mock 来源补位。

### RAG 与存储

```env
RAG_EMBEDDING_PROVIDER=hash
RAG_FETCH_FULL_TEXT=false
RAG_CHUNK_SIZE=900
RAG_CHUNK_OVERLAP=120
DEEPALPHA_DB_PATH=data/deepalpha.sqlite3
CHROMA_DB_PATH=data/chroma
```

默认 hash embedding 可离线运行。SQLite 适合单实例演示；多实例生产部署建议改为外部数据库，并把任务状态和限流迁移到 Redis 或数据库。

### 访问控制与限流

```env
DEEPALPHA_ACCESS_CODE=change-this-value
REPORT_USER_DAILY_LIMIT=3
REPORT_CREATE_RATE_LIMIT_PER_HOUR=5
REPORT_CREATE_RATE_LIMIT_PER_DAY=10
REPORT_GLOBAL_DAILY_LIMIT=50
```

访问码和限流适合受控公测，不等同于完整用户系统。公开上线时建议配合登录、审计和更严格的额度管理。

### 生产安全

```env
ENABLE_DEBUG_ROUTES=false
CORS_ALLOW_ORIGIN_REGEX=https://your-frontend-domain.com
SEC_USER_AGENT=DeepAlpha production contact@example.com
```

`/config` 不返回真实 Key。`/debug/*` 路由受 `ENABLE_DEBUG_ROUTES` 控制，生产环境应关闭。

## API 概览

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/health` | 健康检查 |
| `GET` | `/config` | 查看运行配置，不返回密钥 |
| `GET` | `/symbol/lookup` | 根据公司名或代码查询候选证券 |
| `GET` | `/market/chart` | 获取行情和 provider 降级信息 |
| `GET` | `/financials/latest` | 获取 SEC 财务摘要 |
| `POST` | `/analyze` | 返回完整 Agent 输出、上下文、引用和 trace |
| `POST` | `/report` | 返回前端展示用报告 |
| `POST` | `/report/tasks` | 创建后台报告任务 |
| `GET` | `/report/tasks/{task_id}` | 查询后台任务状态 |
| `GET` | `/memory/history` | 查询研究历史 |
| `GET` / `POST` | `/memory/watchlist` | 查询或新增关注标的 |

生成报告示例：

```bash
curl -X POST http://127.0.0.1:8000/report \
  -H "Content-Type: application/json" \
  -d '{
    "company_name": "Tesla",
    "symbol": "NASDAQ:TSLA",
    "yahoo_symbol": "TSLA",
    "exchange": "NASDAQ",
    "data_provider": "auto"
  }'
```

异步任务示例：

```bash
curl -X POST http://127.0.0.1:8000/report/tasks \
  -H "Content-Type: application/json" \
  -d '{"company_name":"Tesla","symbol":"NASDAQ:TSLA","data_provider":"auto"}'

curl http://127.0.0.1:8000/report/tasks/{task_id}
```

## 项目结构

```text
app/
  agents/          # 分析角色、委员会、风控与报告编辑
  llm/             # OpenAI-compatible LLM 客户端
  memory/          # SQLite 研究历史与 Watchlist
  rag/             # 文档加载、向量存储与检索
  services/        # 上下文、缓存、财务、日志和限流
  tools/           # 行情、证券代码、搜索和 SEC 工具
  graph.py         # LangGraph 工作流
  main.py          # FastAPI 路由
frontend/          # React/Vite 前端
tests/             # API、行情路由、生产可靠性和上下文测试
```

## 测试与构建

后端：

```bash
pytest -q
```

前端：

```bash
cd frontend
npm run build
```

GitHub Actions 会在 push 和 pull request 时运行后端测试与前端构建。

## 部署

仓库包含以下部署文件：

- `Dockerfile`: 后端容器构建。
- `render.yaml`: Render 后端部署示例。
- `.env.zeabur.example`: Zeabur 后端环境变量示例。
- `frontend/vercel.json`: Vercel 前端配置。

常见部署组合：

- 后端：Zeabur、Render、Docker 主机或其他支持 Python/FastAPI 的平台。
- 前端：Vercel 或其他静态站点平台。
- 持久化：为 `DEEPALPHA_DB_PATH` 和 `CHROMA_DB_PATH` 挂载持久化目录。

Docker 本地运行：

```bash
docker build -t deepalpha .
docker run --env-file .env -p 8000:8000 deepalpha
```

## 安全与仓库规范

- `.env`、数据库、Chroma 数据目录、前端构建产物和本地过程文档不应提交到 Git。
- README 和 env 示例只保留占位值，真实 API Key 应配置在部署平台的环境变量中。
- 生产环境请设置 `APP_ENV=production`，并关闭 `ENABLE_DEBUG_ROUTES`。
- 公开体验版建议启用 `DEEPALPHA_ACCESS_CODE` 和报告限流，避免 LLM 与搜索 API 被滥用。

## 已知限制

- A 股和港股的交易所公告、分业务财务和管理层指引尚未接入。
- 免费或低成本行情、搜索 provider 可能限流，字段完整度也可能变化。
- 当前异步任务状态保存在进程内，多 worker 或多实例部署需要外部任务存储。
- 访问码和基础限流适合受控演示，不是完整鉴权体系。
- LLM 输出必须人工复核，引用覆盖检查不能替代专业判断。

## 免责声明

DeepAlpha 仅用于技术研究和信息整理。任何输出均不构成投资建议、交易指令、收益承诺或风险保证。使用者应独立核验数据和结论，并自行承担决策风险。

# 深研 Alpha / DeepAlpha

## 项目定位

多智能体虚拟投研团队。

DeepAlpha 是一个基于 FastAPI 的后端项目，用于模拟虚拟投研团队围绕公司进行结构化研究、风险审查、综合决策、引用检查和 Markdown 报告生成。

## 核心能力

- Planner Agent
- Fundamental Analyst
- Technical Analyst
- News Analyst
- Sentiment Analyst
- Bull Analyst
- Bear Analyst
- Trader Agent
- Risk Manager
- Committee Agent
- Citation Checker
- Agent Trace
- Failure Fallback

## 系统流程

```text
用户输入公司名
↓
Planner 制定研究计划
↓
多个分析师 Agent 分析
↓
Risk Manager 风控审查
↓
Committee 综合汇总
↓
生成 Markdown 投研报告
```

## 本地运行

安装依赖：

```bash
pip install -r requirements.txt
```

复制环境变量示例：

```bash
cp .env.example .env
```

默认使用 mock 搜索和 mock LLM：

```env
SEARCH_PROVIDER=mock
TAVILY_API_KEY=
LLM_PROVIDER=mock
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
ENABLE_DEBUG_ROUTES=true
CORS_ALLOW_ORIGIN_REGEX=http://(127\.0\.0\.1|localhost):\d+
DEEPALPHA_ACCESS_CODE=
DEEPALPHA_DB_PATH=data/deepalpha.sqlite3
SYMBOL_CACHE_TTL_SECONDS=86400
MARKET_CACHE_TTL_SECONDS=300
SYMBOL_LOOKUP_RATE_LIMIT=60
MARKET_CHART_RATE_LIMIT=120
REPORT_USER_DAILY_LIMIT=3
REPORT_CREATE_RATE_LIMIT_PER_HOUR=5
REPORT_CREATE_RATE_LIMIT_PER_DAY=10
REPORT_GLOBAL_DAILY_LIMIT=50
```

启动服务：

```bash
uvicorn app.main:app --reload
```

启动极简 Streamlit 前端：

```bash
streamlit run frontend.py
```

前端会调用：

```text
POST http://127.0.0.1:8000/report
```

启动 React/Vite 前端：

```bash
cd frontend
npm install
npm run dev
```

React 前端默认请求后端：

```text
http://127.0.0.1:8000
```

如需部署到客户环境，在 `frontend/.env` 中配置 API 地址：

```env
VITE_API_BASE=https://api.example.com
```

React 前端使用 Tailwind CSS + Lucide Icons，主界面为三栏投研工作台：

- 左侧：推荐标的与 Watchlist
- 中间：公司搜索、候选股票、Yahoo/Stooq K 线、报告生成
- 右侧：报告结果与历史记录

生产环境建议关闭调试接口，并将 CORS 限制为正式前端域名：

```env
ENABLE_DEBUG_ROUTES=false
CORS_ALLOW_ORIGIN_REGEX=https://www.example.com
DEEPALPHA_DB_PATH=/var/lib/deepalpha/deepalpha.sqlite3
DEEPALPHA_ACCESS_CODE=change-this-access-code
```

当 `ENABLE_DEBUG_ROUTES=false` 时，React 首页不会展示“技术说明”入口，相关 debug 接口也会返回 404。

面向客户使用时，首页会展示一次性风险确认弹窗；生成报告区域也会保留风险提示。DeepAlpha 输出仅用于研究辅助，不构成投资建议、交易指令或收益承诺。

历史报告和 Watchlist 已使用 SQLite 持久化，默认数据库位置为：

```text
data/deepalpha.sqlite3
```

表结构已预留 `tenant_id` 和 `user_id` 字段，后续可接入登录和多租户隔离。

外部 provider 查询已加入内存 TTL 缓存和基础限流：

- `SYMBOL_CACHE_TTL_SECONDS`：公司名解析缓存时间，默认 86400 秒
- `MARKET_CACHE_TTL_SECONDS`：K 线缓存时间，默认 300 秒
- `SYMBOL_LOOKUP_RATE_LIMIT`：每分钟 symbol lookup 次数，默认 60
- `MARKET_CHART_RATE_LIMIT`：每分钟 K 线请求次数，默认 120
- `DEEPALPHA_ACCESS_CODE`：报告生成访问码；为空时不启用访问码保护
- `REPORT_USER_DAILY_LIMIT`：每个浏览器用户每天最多生成报告数，默认 3，设为 0 可关闭
- `REPORT_CREATE_RATE_LIMIT_PER_HOUR`：每个 IP 每小时最多生成报告数，默认 5，设为 0 可关闭
- `REPORT_CREATE_RATE_LIMIT_PER_DAY`：每个 IP 每天最多生成报告数，默认 10，设为 0 可关闭
- `REPORT_GLOBAL_DAILY_LIMIT`：全站每天最多生成报告数，默认 50，设为 0 可关闭

接口日志会以 JSON 形式输出到应用日志，包含 provider、cache hit、点位数量和任务状态等字段。

报告生成支持异步任务接口，适合前端避免长请求超时：

```bash
curl -X POST http://127.0.0.1:8000/report/tasks \
  -H "Content-Type: application/json" \
  -d '{"company_name":"Tesla","symbol":"NASDAQ:TSLA","yahoo_symbol":"TSLA","data_provider":"auto"}'

curl http://127.0.0.1:8000/report/tasks/{task_id}
```

如果请求中提供 `symbol`、`yahoo_symbol` 和 `data_provider`，后端会在生成报告前拉取 6 个月日线行情，计算最新价、区间涨跌幅、6 个月高低点、MA20/MA60、趋势和年化波动率，并写入 Technical Agent 上下文与 Markdown 报告的“行情数据摘要”章节。

如需启用 Tavily 真实搜索：

```env
SEARCH_PROVIDER=tavily
TAVILY_API_KEY=你的 Tavily API Key
```

Search Tool 会调用：

```text
POST https://api.tavily.com/search
```

并将 Tavily 返回结果统一转换为：

```json
[
  {
    "title": "...",
    "url": "...",
    "snippet": "..."
  }
]
```

如果 Tavily 调用失败，系统会打印错误并自动回退到 mock 搜索结果，不会中断 `/analyze`。

如需启用 OpenAI LLM：

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=你的 OpenAI API Key
OPENAI_MODEL=gpt-5
```

如需启用 DeepSeek LLM：

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的 DeepSeek API Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

DeepSeek 使用 OpenAI SDK 兼容模式，模型固定为：

```text
deepseek-chat
```

如果没有配置 API Key，或真实服务调用失败，系统会自动回退到 mock 结果，不会中断 `/analyze`。

RAG 检索层使用 Chroma 作为向量库：

```text
Tavily Search / mock search
→ documents
→ Chroma Vector Store
→ RAG Retriever
→ Industry Analyst
```

当前使用本地 hash embedding，避免额外下载 embedding 模型；如果 `chromadb` 不可用，会自动回退到简单内存关键词检索。

Chroma 索引会持久化到：

```text
data/chroma
```

可以用 RAG 诊断接口查看检索结果：

```bash
curl "http://127.0.0.1:8000/debug/rag?company_name=Tesla"
```

该接口会返回 query、vector_store、collection_name、chunks_count、chunks 和 sources。

可以通过 `/config` 检查当前运行模式。该接口只返回 provider、model 和是否启用，不会返回真实 API Key：

```bash
curl http://127.0.0.1:8000/config
```

## Docker 运行

构建镜像：

```bash
docker build -t deepalpha .
```

运行容器：

```bash
docker run --env-file .env -p 8000:8000 deepalpha
```

如果只使用 mock 模式，也可以不传 `.env`：

```bash
docker run -p 8000:8000 deepalpha
```

## 上云部署：Render + Vercel

推荐最小上线架构：

```text
Vercel: React/Vite 前端
Render: FastAPI 后端
Render Persistent Disk: SQLite + Chroma 数据目录
DeepSeek: LLM
Tavily: 搜索/RAG 外部检索
```

### 1. 部署后端到 Render

仓库根目录已提供 `render.yaml`。在 Render 中选择 Blueprint 或 Web Service 均可。

后端启动命令：

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Render 后端建议配置环境变量：

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的 DeepSeek API Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
SEARCH_PROVIDER=tavily
TAVILY_API_KEY=你的 Tavily API Key

ENABLE_DEBUG_ROUTES=false
CORS_ALLOW_ORIGIN_REGEX=https://你的前端域名

DEEPALPHA_ACCESS_CODE=给体验用户的访问码
DEEPALPHA_DB_PATH=/var/lib/deepalpha/deepalpha.sqlite3
CHROMA_DB_PATH=/var/lib/deepalpha/chroma

REPORT_USER_DAILY_LIMIT=3
REPORT_CREATE_RATE_LIMIT_PER_HOUR=5
REPORT_CREATE_RATE_LIMIT_PER_DAY=10
REPORT_GLOBAL_DAILY_LIMIT=50
```

如果使用 `render.yaml`，`DEEPSEEK_API_KEY`、`TAVILY_API_KEY`、`DEEPALPHA_ACCESS_CODE`、`CORS_ALLOW_ORIGIN_REGEX` 需要在 Render 控制台手动填写。

### 2. 部署前端到 Vercel

前端目录已提供 `frontend/vercel.json`。

在 Vercel 中将项目 Root Directory 设置为：

```text
frontend
```

Vercel 前端环境变量：

```env
VITE_API_BASE=https://你的 Render 后端域名
```

前端构建命令：

```bash
npm run build
```

输出目录：

```text
dist
```

### 3. 上线检查清单

- Render `/health` 返回 `{"status":"ok"}`
- Vercel 前端 `VITE_API_BASE` 指向 Render 后端
- Render `CORS_ALLOW_ORIGIN_REGEX` 精确匹配 Vercel 域名
- `ENABLE_DEBUG_ROUTES=false`
- DeepSeek/Tavily API Key 只存在后端环境变量中
- `DEEPALPHA_ACCESS_CODE` 已设置
- 生成报告触发访问码弹窗并能成功生成
- 达到限额时前端提示“报告生成次数已达当前上限”

## 免绑卡部署：Hugging Face Spaces + Vercel

如果 Render 要求添加付款方式，可以先用 Hugging Face Spaces 托管 FastAPI 后端，Vercel 托管前端。

推荐结构：

```text
Hugging Face Spaces: Docker/FastAPI 后端
Vercel: React/Vite 前端
DeepSeek: LLM
Tavily: 搜索/RAG 外部检索
```

### 1. 创建 Hugging Face Space

在 Hugging Face 新建 Space：

- SDK：`Docker`
- Repository：可以选择导入 GitHub 仓库，或手动同步代码
- Visibility：演示可设 Public；如不希望公开代码和日志，可设 Private

本项目 Dockerfile 默认监听：

```text
0.0.0.0:7860
```

Hugging Face Spaces 会自动使用该端口。

### 2. 配置 Hugging Face Secrets

在 Space 的 Settings -> Variables and secrets 中添加：

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的 DeepSeek API Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
SEARCH_PROVIDER=tavily
TAVILY_API_KEY=你的 Tavily API Key

ENABLE_DEBUG_ROUTES=false
CORS_ALLOW_ORIGIN_REGEX=https://你的 Vercel 前端域名

DEEPALPHA_ACCESS_CODE=给体验用户的访问码
DEEPALPHA_DB_PATH=/data/deepalpha.sqlite3
CHROMA_DB_PATH=/data/chroma

REPORT_USER_DAILY_LIMIT=3
REPORT_CREATE_RATE_LIMIT_PER_HOUR=5
REPORT_CREATE_RATE_LIMIT_PER_DAY=10
REPORT_GLOBAL_DAILY_LIMIT=50
```

注意：免费 Hugging Face Spaces 的文件系统不适合作为长期可靠数据库。演示版可以接受；正式客户试用建议迁移到 VPS、Render/Railway 付费实例，或接外部 Postgres/Redis。

### 3. 验证后端

Space 构建完成后，访问：

```text
https://你的用户名-你的space名.hf.space/health
```

返回：

```json
{"status":"ok"}
```

表示后端正常。

### 4. 部署前端到 Vercel

Vercel 项目 Root Directory 选择：

```text
frontend
```

设置环境变量：

```env
VITE_API_BASE=https://你的用户名-你的space名.hf.space
```

部署完成后，回到 Hugging Face Secrets，把：

```env
CORS_ALLOW_ORIGIN_REGEX=https://你的 Vercel 前端域名
```

改成真实 Vercel 域名，并重启 Space。

## Zeabur 部署：Zeabur + Vercel

Zeabur 支持从 GitHub 创建服务，也支持使用仓库中的 Dockerfile 部署。Zeabur 会通过 `PORT` 环境变量决定服务端口，本项目 Dockerfile 已兼容 `${PORT}`。

### 1. 部署后端到 Zeabur

在 Zeabur 中：

1. 创建 Project
2. 创建 Service
3. 选择 GitHub Repository
4. 选择 `wannathan20-sketch/deepalpha`
5. 使用根目录 Dockerfile 部署

后端环境变量可参考 `.env.zeabur.example`：

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的 DeepSeek API Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
SEARCH_PROVIDER=tavily
TAVILY_API_KEY=你的 Tavily API Key

ENABLE_DEBUG_ROUTES=false
CORS_ALLOW_ORIGIN_REGEX=https://你的 Vercel 前端域名

DEEPALPHA_ACCESS_CODE=给体验用户的访问码
DEEPALPHA_DB_PATH=/data/deepalpha.sqlite3
CHROMA_DB_PATH=/data/chroma

REPORT_USER_DAILY_LIMIT=3
REPORT_CREATE_RATE_LIMIT_PER_HOUR=5
REPORT_CREATE_RATE_LIMIT_PER_DAY=10
REPORT_GLOBAL_DAILY_LIMIT=50
```

Zeabur 部署完成后，访问：

```text
https://你的-zeabur-后端域名/health
```

返回 `{"status":"ok"}` 表示后端正常。

### 2. 部署前端到 Vercel

Vercel 项目 Root Directory：

```text
frontend
```

Vercel 环境变量：

```env
VITE_API_BASE=https://你的-zeabur-后端域名
```

前端部署完成后，回到 Zeabur，把：

```env
CORS_ALLOW_ORIGIN_REGEX=https://你的 Vercel 前端域名
```

改成真实前端域名并重新部署后端。

## API 示例

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

运行模式诊断：

```bash
curl http://127.0.0.1:8000/config
```

完整投研分析接口，适合开发调试：

```bash
curl -X POST http://127.0.0.1:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"company_name":"OpenAI"}'
```

可选传入 `thread_id`，用于 LangGraph 短期记忆和任务状态追踪；不传时系统会自动生成：

```bash
curl -X POST http://127.0.0.1:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"company_name":"OpenAI","thread_id":"demo-thread-001"}'
```

`/analyze` 返回内容包含：

```text
company_name
thread_id
status
research_plan
team_results
final_report
markdown_report
citation_check
trace
```

简洁报告接口，适合前端和面试演示：

```bash
curl -X POST http://127.0.0.1:8000/report \
  -H "Content-Type: application/json" \
  -d '{"company_name":"Tesla"}'
```

`/report` 内部复用完整分析流程，但不会返回完整 `team_results`，避免 JSON 过长。返回内容包含：

```text
company_name
thread_id
status
final_report
markdown_report
citation_check
trace_summary
```

长期 Memory 接口，使用本地 JSON 文件保存历史投研报告和关注列表：

```bash
curl http://127.0.0.1:8000/memory/history
```

```bash
curl http://127.0.0.1:8000/memory/history/Tesla
```

```bash
curl -X POST http://127.0.0.1:8000/memory/watchlist \
  -H "Content-Type: application/json" \
  -d '{"company_name":"Tesla"}'
```

```bash
curl http://127.0.0.1:8000/memory/watchlist
```

Memory 文件位于：

```text
data/research_history.json
data/watchlist.json
```

其中 `/analyze` 完成后会自动写入 `research_history.json`。当前实现是最小本地文件版，不接数据库。

系统也会在每次分析开始时读取同一家公司最近 3 条历史投研记录，并写入 LangGraph 上下文：

```text
context["memory"]["recent_history"]
```

Industry、Fundamental、News、Risk Manager 和 Committee Agent 会参考这些历史结论。重复分析同一家公司时，报告中的“历史投研记忆”章节会展示最近记录；如果没有历史记录，则显示“暂无历史投研记录”。

## 测试

运行自动化测试：

```bash
pytest
```

## 免责声明

本项目仅用于技术学习和信息整理，不构成投资建议。

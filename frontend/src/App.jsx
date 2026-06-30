import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  ArrowLeft,
  BarChart3,
  BookOpen,
  Brain,
  Building2,
  CheckCircle2,
  Clock3,
  Database,
  Download,
  FileSearch,
  FileText,
  History,
  Loader2,
  MessageCircle,
  Network,
  Plus,
  Play,
  Send,
  ShieldCheck,
  Star,
  TrendingUp,
  Wrench,
} from "lucide-react";
import { API_BASE, formatApiErrorMessage } from "./apiClient.js";
import { deleteReportChatMessage, getReportChatItemKey } from "./reportChatHistory.js";
import { cleanMarkdownText, extractExecutiveSummary, extractReportHeadings } from "./reportContent.js";
import { loadStockIndex, mergeSymbolCandidates, parseWatchlistImportText, searchStockIndex } from "./stockSearch.js";

const DISCLAIMER_STORAGE_KEY = "deepalpha_disclaimer_accepted";
const ACCESS_CODE_STORAGE_KEY = "deepalpha_access_code";
const USER_ID_STORAGE_KEY = "deepalpha_user_id";
const LAST_REPORT_TASK_STORAGE_KEY = "deepalpha_last_report_task_id";

const RECOMMENDED_COMPANIES = [
  { company: "Tesla", ticker: "NASDAQ:TSLA", sector: "EV / AI" },
  { company: "NVIDIA", ticker: "NASDAQ:NVDA", sector: "AI Chips" },
  { company: "Apple", ticker: "NASDAQ:AAPL", sector: "Consumer Tech" },
  { company: "Microsoft", ticker: "NASDAQ:MSFT", sector: "Cloud / AI" },
  { company: "Amazon", ticker: "NASDAQ:AMZN", sector: "Cloud / Retail" },
  { company: "Meta", ticker: "NASDAQ:META", sector: "Social / AI" },
  { company: "Google", ticker: "NASDAQ:GOOGL", sector: "Search / AI" },
];

const LOCAL_SYMBOL_FALLBACKS = [
  {
    symbol: "MU",
    name: "Micron Technology",
    company: "Micron Technology",
    ticker: "NASDAQ:MU",
    raw_symbol: "MU",
    exchange: "NASDAQ",
    market: "US",
    confidence: 0.9,
    source: "frontend_fallback",
    aliases: ["micron", "micron technology", "美光", "美光科技", "mu"],
  },
  {
    symbol: "NOK",
    name: "Nokia Oyj ADR",
    company: "Nokia Oyj ADR",
    ticker: "NYSE:NOK",
    raw_symbol: "NOK",
    exchange: "NYSE",
    market: "US",
    confidence: 0.9,
    source: "frontend_fallback",
    aliases: ["nokia", "nokia oyj", "诺基亚", "诺基亚公司", "nok", "nokia adr", "nokia us", "诺基亚美股"],
  },
  {
    symbol: "NOKIA.HE",
    name: "Nokia Oyj",
    company: "Nokia Oyj",
    ticker: "OMXHEX:NOKIA",
    raw_symbol: "NOKIA.HE",
    exchange: "OMXHEX",
    market: "FI",
    confidence: 0.9,
    source: "frontend_fallback",
    aliases: ["nokia", "nokia oyj", "诺基亚", "诺基亚公司", "nokia.hel", "nokia.he"],
  },
  {
    symbol: "MRVL",
    name: "Marvell Technology",
    company: "Marvell Technology",
    ticker: "NASDAQ:MRVL",
    raw_symbol: "MRVL",
    exchange: "NASDAQ",
    market: "US",
    confidence: 0.9,
    source: "frontend_fallback",
    aliases: ["marvell", "marvell technology", "迈威尔", "美满电子", "mrvl"],
  },
];

const YAHOO_SUFFIX_BY_EXCHANGE = {
  ASX: "AX",
  BMFBOVESPA: "SA",
  EURONEXT: "PA",
  HKEX: "HK",
  LSE: "L",
  MIL: "MI",
  OMXHEX: "HE",
  SSE: "SS",
  SZSE: "SZ",
  TSX: "TO",
  TWSE: "TW",
  XETR: "DE",
};

// Convert exchange-qualified tickers into Yahoo Finance symbols used by the backend market endpoint.
// 将带交易所前缀的 ticker 转换为后端行情接口使用的 Yahoo Finance 符号。
function toYahooSymbol(ticker, matchedSymbol) {
  if (matchedSymbol?.symbol) return matchedSymbol.symbol;
  if (matchedSymbol?.raw_symbol) return matchedSymbol.raw_symbol;
  if (matchedSymbol?.yahooSymbol) return matchedSymbol.yahooSymbol;

  const normalizedTicker = ticker.trim().toUpperCase();
  if (!normalizedTicker) return "";
  if (!normalizedTicker.includes(":")) return normalizedTicker;

  const [exchange, symbol] = normalizedTicker.split(":");
  if (["NASDAQ", "NYSE", "OTC", "AMEX"].includes(exchange)) return symbol;

  const yahooSuffix = YAHOO_SUFFIX_BY_EXCHANGE[exchange];
  return yahooSuffix ? `${symbol}.${yahooSuffix}` : symbol;
}

function exchangeFromTicker(ticker) {
  return ticker.includes(":") ? ticker.split(":", 1)[0] : "";
}

// Recommended picks bypass remote lookup, so build the same selection shape as search results.
// 推荐标的跳过远程搜索，因此这里构造与搜索结果一致的选中对象结构。
function buildRecommendedSelection(company, ticker) {
  const yahooSymbol = toYahooSymbol(ticker);
  return {
    symbol: yahooSymbol,
    name: company,
    company,
    ticker,
    raw_symbol: yahooSymbol,
    exchange: exchangeFromTicker(ticker),
    market: exchangeFromTicker(ticker),
    confidence: 1,
    source: "recommended",
  };
}

// A small local fallback keeps common ambiguous names usable if the symbol API is unavailable.
// 少量本地兜底数据用于符号接口不可用时处理常见且容易歧义的公司名称。
function findLocalFallbackMatches(query) {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) return [];

  return LOCAL_SYMBOL_FALLBACKS.filter((item) =>
    [item.name, item.company, item.symbol, item.ticker, ...(item.aliases || [])].some((alias) => {
      const normalizedAlias = String(alias).toLowerCase();
      return normalizedAlias === normalizedQuery || (
        normalizedQuery.length > 1 &&
        (normalizedAlias.includes(normalizedQuery) || normalizedQuery.includes(normalizedAlias))
      );
    }),
  );
}

function getTradingViewUrl(symbol, query = "") {
  if (symbol) {
    return `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(symbol)}`;
  }
  if (query.trim()) {
    return `https://www.tradingview.com/search/?query=${encodeURIComponent(query.trim())}`;
  }
  return "https://www.tradingview.com/markets/stocks-usa/market-movers-large-cap/";
}

function shouldAutoSelectSymbol(matches, data = {}) {
  if (matches.length !== 1) return false;
  if (data.needs_confirmation === false) return true;
  return (matches[0].confidence || 0) >= 0.9;
}

function getOrCreateUserId() {
  // Persist an anonymous id so backend limits are per user session instead of only per IP.
  // 持久化匿名用户标识，让后端限流能按用户会话区分，而不只依赖 IP。
  const existing = window.localStorage.getItem(USER_ID_STORAGE_KEY);
  if (existing) return existing;

  const nextId = window.crypto?.randomUUID?.() || `user-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  window.localStorage.setItem(USER_ID_STORAGE_KEY, nextId);
  return nextId;
}

function buildAuthHeaders() {
  return {
    "X-DeepAlpha-User-Id": getOrCreateUserId(),
    "X-DeepAlpha-Access-Code": window.localStorage.getItem(ACCESS_CODE_STORAGE_KEY) || "",
  };
}

async function requestJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...buildAuthHeaders(),
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    let errorPayload = {};
    try {
      errorPayload = await response.clone().json();
    } catch (err) {
      errorPayload = {};
    }
    throw new Error(formatApiErrorMessage(response.status, errorPayload));
  }

  return response.json();
}

function classNames(...items) {
  return items.filter(Boolean).join(" ");
}

function delay(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function Panel({ title, icon: Icon, children, className = "", action }) {
  return (
    <section className={classNames("rounded-lg border border-slate-800 bg-slate-900/80 p-4 shadow-xl shadow-slate-950/20", className)}>
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          {Icon && <Icon className="h-4 w-4 text-cyan-300" />}
          <h2 className="truncate text-sm font-semibold uppercase text-slate-200">{title}</h2>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

function StatusBadge({ enabled, label }) {
  return (
    <span
      className={classNames(
        "inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs",
        enabled
          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
          : "border-slate-700 bg-slate-800 text-slate-400",
      )}
    >
      {enabled ? <CheckCircle2 className="h-3 w-3" /> : <Activity className="h-3 w-3" />}
      {label}
    </span>
  );
}

function MetricCard({ label, value, icon: Icon }) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/70 p-3">
      <div className="flex items-center gap-2 text-xs uppercase text-slate-500">
        {Icon && <Icon className="h-3.5 w-3.5" />}
        {label}
      </div>
      <div className="mt-2 break-words text-lg font-semibold text-slate-100">{value ?? "N/A"}</div>
    </div>
  );
}

function CompactMetric({ label, value, tone = "slate" }) {
  const toneClass = {
    cyan: "border-cyan-400/25 bg-cyan-400/10 text-cyan-100",
    emerald: "border-emerald-400/25 bg-emerald-400/10 text-emerald-100",
    amber: "border-amber-400/25 bg-amber-400/10 text-amber-100",
    red: "border-red-400/25 bg-red-400/10 text-red-100",
    slate: "border-slate-800 bg-slate-950/70 text-slate-200",
  }[tone];

  return (
    <div className={classNames("rounded-md border px-3 py-2", toneClass)}>
      <div className="text-[11px] uppercase text-slate-500">{label}</div>
      <div className="mt-1 text-sm font-semibold">{value ?? "N/A"}</div>
    </div>
  );
}

function formatFinancialValue(value, currency = "") {
  if (value === null || value === undefined || value === "") return "N/A";
  if (typeof value !== "number") return value;
  const prefix = currency ? `${currency} ` : "";
  const absValue = Math.abs(value);
  if (absValue >= 1_000_000_000) return `${prefix}${(value / 1_000_000_000).toFixed(2)}B`;
  if (absValue >= 1_000_000) return `${prefix}${(value / 1_000_000).toFixed(2)}M`;
  return `${prefix}${value.toLocaleString("en-US")}`;
}

function safeReportUrl(url) {
  if (!url || url === "#") return "#";

  try {
    const parsed = new URL(url);
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.toString() : "#";
  } catch (err) {
    return "#";
  }
}

function LatestFinancials({ profile, status }) {
  if (status === "loading") {
    return (
      <div className="flex items-center gap-2 rounded-md border border-slate-800 bg-slate-950/70 p-3 text-sm text-slate-400">
        <Loader2 className="h-4 w-4 animate-spin" />
        正在加载最新财报...
      </div>
    );
  }

  if (!profile) {
    return <p className="text-sm text-slate-500">选择标的后会自动加载可用的最新财报摘要。</p>;
  }

  if (!profile.enabled) {
    return (
      <div className="rounded-md border border-amber-400/25 bg-amber-400/10 p-3 text-sm leading-6 text-amber-100">
        {profile.reason || "暂无可用财报摘要。"}
      </div>
    );
  }

  const filingUrl = safeReportUrl(profile.filing_url);
  const currency = profile.currency || "";
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3 rounded-md border border-slate-800 bg-slate-950/70 p-3">
        <div>
          <div className="text-sm font-semibold text-slate-100">{profile.company_name || profile.symbol}</div>
          <div className="mt-1 text-xs text-slate-500">
            {profile.filing_type || "SEC"} · {profile.fiscal_period || profile.report_date || "latest filing"}
            {currency ? ` · ${currency}` : ""}
          </div>
        </div>
        {filingUrl !== "#" && (
          <a
            className="inline-flex rounded-md border border-cyan-300/40 px-2 py-1 text-xs text-cyan-100 hover:border-cyan-300"
            href={filingUrl}
            rel="noreferrer"
            target="_blank"
          >
            SEC
          </a>
        )}
      </div>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <CompactMetric label="收入" value={formatFinancialValue(profile.revenue, currency)} tone="cyan" />
        <CompactMetric label="净利润" value={formatFinancialValue(profile.net_income, currency)} tone="emerald" />
        <CompactMetric label="毛利率" value={profile.gross_margin_percent == null ? "N/A" : `${profile.gross_margin_percent}%`} tone="slate" />
        <CompactMetric label="经营现金流" value={formatFinancialValue(profile.operating_cash_flow, currency)} tone="amber" />
      </div>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <CompactMetric label="营业利润率" value={profile.operating_margin_percent == null ? "N/A" : `${profile.operating_margin_percent}%`} />
        <CompactMetric label="EPS" value={formatFinancialValue(profile.eps_diluted)} />
        <CompactMetric label="现金" value={formatFinancialValue(profile.cash, currency)} />
        <CompactMetric label="债务" value={formatFinancialValue(profile.debt, currency)} />
      </div>
    </div>
  );
}

const REPORT_STEP_LABELS = {
  queued: "排队",
  fetch_market: "行情",
  fetch_financials: "财报",
  rag_search: "检索",
  agent_analysis: "分析",
  report_render: "报告",
  completed: "完成",
  failed: "失败",
};

function ReportTaskProgress({ task }) {
  const steps = task?.steps || [];
  if (!steps.length) return null;

  return (
    <div className="mt-3 rounded-md border border-slate-800 bg-slate-950/70 p-3">
      <div className="mb-2 flex items-center justify-between gap-2 text-xs text-slate-400">
        <span>报告任务状态：{task?.status || "queued"}</span>
        {task?.task_id && <span className="font-mono text-[11px] text-slate-600">{task.task_id.slice(0, 8)}</span>}
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {steps.map((step) => {
          const isRunning = step.status === "running";
          const isSuccess = step.status === "success";
          const isFailed = step.status === "failed";
          const Icon = isRunning ? Loader2 : isSuccess ? CheckCircle2 : isFailed ? Activity : Clock3;
          return (
            <div
              className={classNames(
                "flex min-h-10 items-start gap-2 rounded-md border px-2 py-2 text-xs",
                isSuccess && "border-emerald-400/25 bg-emerald-400/10 text-emerald-100",
                isRunning && "border-cyan-400/25 bg-cyan-400/10 text-cyan-100",
                isFailed && "border-red-400/25 bg-red-400/10 text-red-100",
                !isSuccess && !isRunning && !isFailed && "border-slate-800 bg-slate-900/70 text-slate-500",
              )}
              key={step.name}
            >
              <Icon className={classNames("mt-0.5 h-3.5 w-3.5 shrink-0", isRunning && "animate-spin")} />
              <div className="min-w-0">
                <div className="font-medium">{REPORT_STEP_LABELS[step.name] || step.name}</div>
                {(step.message || step.error) && (
                  <div className="mt-1 break-words text-[11px] leading-4 opacity-80">{step.error || step.message}</div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function formatPercent(value) {
  if (value === null || value === undefined || value === "") return "N/A";
  const number = Number(value);
  if (!Number.isFinite(number)) return "N/A";
  return `${number > 0 ? "+" : ""}${number.toFixed(2)}%`;
}

function formatPrice(value) {
  if (value === null || value === undefined || value === "") return "";
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  if (number >= 1000) {
    return number.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  return number.toFixed(2);
}

function MarketReviewPanel({ review }) {
  const reviews = review?.reviews || {};
  const markets = [
    ["cn", "A 股"],
    ["hk", "港股"],
    ["us", "美股"],
  ];

  if (!review) {
    return <p className="text-sm text-slate-500">正在加载市场复盘...</p>;
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
        <span>{review.cache_hit ? "缓存命中" : "实时拉取"}</span>
        {review.generated_at && <span>生成时间 {new Date(review.generated_at).toLocaleString()}</span>}
      </div>
      <div className="grid gap-3 lg:grid-cols-3">
        {markets.map(([market, label]) => {
          const item = reviews[market];
          const indices = item?.indices || [];
          const summary = item?.summary || [];
          return (
            <div className="rounded-md border border-slate-800 bg-slate-950/70 p-3" key={market}>
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="text-sm font-semibold text-slate-100">{label}</div>
                <span
                  className={classNames(
                    "rounded-md border px-2 py-1 text-[11px]",
                    item?.context_status === "available"
                      ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-100"
                      : "border-amber-400/25 bg-amber-400/10 text-amber-100",
                  )}
                >
                  {item?.context_status || "missing"}
                </span>
              </div>
              <div className="min-h-10 space-y-1 text-xs leading-5 text-slate-400">
                {(summary.length ? summary : ["暂无复盘数据。"]).map((line, index) => (
                  <p key={`${market}-summary-${index}`}>{line}</p>
                ))}
              </div>
              <div className="mt-3 space-y-2">
                {indices.slice(0, 3).map((index) => (
                  <div className="space-y-1 rounded-md border border-slate-800/70 bg-slate-900/40 p-2 text-xs" key={index.symbol}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-slate-300">{index.name}</span>
                      <span className="space-x-2 font-mono">
                        {index.latest_close != null && (
                          <span className="text-slate-200">{formatPrice(index.latest_close)}</span>
                        )}
                        <span
                          className={classNames(
                            Number(index.change_percent) > 0
                              ? "text-emerald-200"
                              : Number(index.change_percent) < 0
                                ? "text-red-200"
                                : "text-slate-400",
                          )}
                        >
                          {formatPercent(index.change_percent)}
                        </span>
                      </span>
                    </div>
                  </div>
                ))}
                {!indices.length && <div className="text-xs text-slate-500">指数数据暂缺。</div>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SourceQualitySummary({ sourceQuality }) {
  const gradeCounts = sourceQuality?.grade_counts || {};
  const grades = [
    ["A", gradeCounts.A || 0, "emerald"],
    ["B", gradeCounts.B || 0, "cyan"],
    ["C", gradeCounts.C || 0, "amber"],
    ["D", gradeCounts.D || 0, "red"],
  ];
  const warnings = sourceQuality?.data_quality?.warnings || sourceQuality?.risks || [];
  const ratings = sourceQuality?.source_ratings || [];

  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/70 p-3">
      <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase text-slate-300">
        <ShieldCheck className="h-3.5 w-3.5 text-cyan-300" />
        来源质量
      </div>
      <div className="grid grid-cols-4 gap-2">
        {grades.map(([grade, count, tone]) => (
          <CompactMetric label={`${grade} 级`} value={count} tone={tone} key={grade} />
        ))}
      </div>
      {warnings.length > 0 && (
        <p className="mt-3 text-xs leading-5 text-amber-100">{warnings[0]}</p>
      )}
      {ratings.length > 0 && (
        <div className="mt-3 text-xs text-slate-500">已评级来源：{ratings.length} 条</div>
      )}
    </div>
  );
}

function ReportEditorSummary({ editor }) {
  const edits = editor?.edits || {};

  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/70 p-3">
      <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase text-slate-300">
        <Wrench className="h-3.5 w-3.5 text-cyan-300" />
        Report Editor
      </div>
      <div className="grid grid-cols-3 gap-2">
        <CompactMetric label="重复" value={edits.removed_duplicates || 0} tone="cyan" />
        <CompactMetric label="残留" value={edits.removed_artifacts || 0} tone="amber" />
        <CompactMetric label="清理行" value={edits.cleaned_lines || 0} tone="emerald" />
      </div>
      <p className="mt-3 text-xs leading-5 text-slate-400">
        {editor?.summary || "报告已完成 PDF 前清洗。"}
      </p>
    </div>
  );
}

function CitationCheckSummary({ citationCheck }) {
  if (!citationCheck) return null;

  const coverage = citationCheck.claim_citation_coverage || 0;
  const semanticCov = citationCheck.semantic_coverage || 0;
  const unverifiedClaims = citationCheck.unverified_claims || [];
  const warnings = citationCheck.warnings || [];
  const issues = citationCheck.issues || [];

  const coveragePct = Math.round(coverage * 100);
  const semanticPct = Math.round(semanticCov * 100);
  const passed = citationCheck.passed !== false && issues.length === 0;

  const coverageTone = coveragePct >= 60 ? "emerald" : coveragePct >= 30 ? "amber" : "red";
  const semanticTone = semanticPct >= 60 ? "emerald" : semanticPct >= 30 ? "amber" : "red";

  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/70 p-3">
      <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase text-slate-300">
        <CheckCircle2 className="h-3.5 w-3.5 text-cyan-300" />
        引用验证
        <span className={classNames("ml-auto rounded px-1.5 py-0.5 text-[10px]", passed ? "bg-emerald-400/10 text-emerald-200" : "bg-amber-400/10 text-amber-200")}>
          {passed ? "通过" : "注意"}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <CompactMetric label="URL 覆盖率" value={`${coveragePct}%`} tone={coverageTone} />
        <CompactMetric label="语义匹配" value={`${semanticPct}%`} tone={semanticTone} />
      </div>
      {unverifiedClaims.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs text-amber-100 hover:text-amber-50 select-none">
            {unverifiedClaims.length} 条声明缺少 RAG 验证
          </summary>
          <div className="mt-2 max-h-48 space-y-1.5 overflow-auto">
            {unverifiedClaims.slice(0, 10).map((item, idx) => (
              <div className="rounded border border-amber-400/20 bg-amber-400/5 px-2 py-1.5 text-[11px] leading-4 text-amber-100/80" key={idx}>
                <span className="font-medium text-amber-100">{item.agent}</span>
                {item.has_source_url && <span className="ml-1 text-slate-500">(有 URL)</span>}
                <span className="mt-0.5 block">{item.claim}</span>
              </div>
            ))}
          </div>
        </details>
      )}
      {warnings.length > 0 && !unverifiedClaims.length && (
        <p className="mt-2 text-xs leading-5 text-slate-400">{warnings[0]}</p>
      )}
    </div>
  );
}

function DataQualityBar({ analysisContext }) {
  const dq = analysisContext?.data_quality;
  if (!dq || dq.overall_score == null) return null;

  const score = dq.overall_score;
  const levelLabel = { good: "优质", usable: "可用", limited: "有限", poor: "不足" }[dq.level] || dq.level;
  const barColor =
    score >= 85 ? "bg-emerald-400" : score >= 60 ? "bg-cyan-400" : score >= 35 ? "bg-amber-400" : "bg-red-400";
  const textColor =
    score >= 85 ? "text-emerald-200" : score >= 60 ? "text-cyan-200" : score >= 35 ? "text-amber-200" : "text-red-200";

  const sources = [
    { key: "market", label: "行情" },
    { key: "financials", label: "财报" },
    { key: "rag", label: "RAG" },
  ];

  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/70 p-3">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 shrink-0">
          <Database className="h-3.5 w-3.5 text-cyan-300" />
          <span className="text-xs font-semibold uppercase text-slate-300">数据质量</span>
        </div>
        <div className="flex-1 h-2 rounded-full bg-slate-800 overflow-hidden">
          <div
            className={classNames("h-full rounded-full transition-all", barColor)}
            style={{ width: `${Math.max(score, 4)}%` }}
          />
        </div>
        <span className={classNames("text-sm font-bold tabular-nums", textColor)}>{score}</span>
        <span className={classNames("text-[11px] rounded px-1.5 py-0.5", score >= 85 ? "bg-emerald-400/10 text-emerald-200" : score >= 60 ? "bg-cyan-400/10 text-cyan-200" : score >= 35 ? "bg-amber-400/10 text-amber-200" : "bg-red-400/10 text-red-200")}>
          {levelLabel}
        </span>
      </div>
      <div className="mt-2 flex gap-3 text-[11px] text-slate-500">
        {sources.map(({ key, label }) => {
          const item = analysisContext[key];
          const status = item?.status || "unknown";
          const dotColor =
            status === "available" ? "bg-emerald-400" :
            status === "partial" || status === "estimated" ? "bg-cyan-400" :
            status === "stale" || status === "fallback" ? "bg-amber-400" :
            "bg-red-400";
          return (
            <span className="flex items-center gap-1" key={key}>
              <span className={classNames("h-1.5 w-1.5 rounded-full", dotColor)} />
              {label}
            </span>
          );
        })}
        {dq.limitations?.length > 0 && (
          <span className="text-amber-400/70 truncate">{dq.limitations[0]}</span>
        )}
      </div>
    </div>
  );
}

function ExecutiveSummaryCard({ content }) {
  const items = extractExecutiveSummary(content);
  if (!items.length) return null;

  return (
    <div className="rounded-md border border-cyan-400/25 bg-cyan-400/10 p-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase text-cyan-100">
        <FileText className="h-3.5 w-3.5" />
        摘要
      </div>
      <div className="space-y-2">
        {items.map((item) => (
          <div className="flex gap-2 text-xs leading-5 text-slate-200" key={item}>
            <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-300" />
            <span>{renderInlineMarkdown(item, `exec-${item.slice(0, 8)}`)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function renderInlineMarkdown(text, keyPrefix = "line") {
  const nodes = [];
  const tokenPattern = /\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+)\*\*|__([^_]+)__|\*([^*]+)\*/g;
  let lastIndex = 0;
  let match = tokenPattern.exec(text);

  while (match) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }

    if (match[1] && match[2]) {
      const href = safeReportUrl(match[2]);
      nodes.push(
        <a
          className="report-link"
          href={href}
          key={`${keyPrefix}-${match.index}`}
          rel="noreferrer"
          target="_blank"
        >
          {cleanMarkdownText(match[1])}
        </a>,
      );
    } else {
      nodes.push(
        <strong className="font-semibold text-slate-100" key={`${keyPrefix}-${match.index}`}>
          {cleanMarkdownText(match[3] || match[4] || match[5])}
        </strong>,
      );
    }

    lastIndex = match.index + match[0].length;
    match = tokenPattern.exec(text);
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }

  return nodes.length ? nodes : text;
}

function reportSectionId(index, title) {
  const slug = String(title)
    .toLowerCase()
    .replace(/[^\p{L}\p{N}_]+/gu, "-")
    .replace(/^-+|-+$/g, "") || "section";
  return `report-section-${index}-${slug}`;
}

function ReportTOC({ content, onJump }) {
  const headings = useMemo(() => extractReportHeadings(content), [content]);
  if (!headings.length) return null;

  return (
    <details className="rounded-md border border-slate-800 bg-slate-950/70" open>
      <summary className="cursor-pointer px-4 py-2.5 text-xs font-semibold uppercase text-slate-400 hover:text-slate-200 select-none">
        报告目录 · {headings.length} 个章节
      </summary>
      <div className="border-t border-slate-800 px-3 py-2 max-h-[360px] overflow-auto">
        {headings.map((heading) => (
          <button
            className={classNames(
              "block w-full rounded px-2 py-1.5 text-left text-xs transition hover:bg-cyan-400/10 hover:text-cyan-100",
              heading.level === 1 ? "font-semibold text-slate-200" : "pl-6 text-slate-400",
            )}
            key={heading.sectionId}
            onClick={() => onJump(heading.sectionId)}
            type="button"
          >
            {heading.level === 1 ? "" : ""}
            {heading.text}
          </button>
        ))}
      </div>
    </details>
  );
}

function MarkdownReport({ content, printMode = false, highlightedSectionId = "" }) {
  if (!content) return null;
  let sectionIndex = 0;

  return (
    <div className={classNames("report-document space-y-3", printMode ? "print-report-body" : "")}>
      {content.split("\n").map((line, index) => {
        const key = `${index}-${line.slice(0, 16)}`;
        const trimmedLine = line.trim();
        if (!trimmedLine) return <div className="h-1" key={key} />;
        if (/^#\s+/.test(trimmedLine)) {
          sectionIndex += 1;
          const sectionId = reportSectionId(sectionIndex, cleanMarkdownText(trimmedLine));
          return (
            <h1
              className={classNames("report-title scroll-mt-4", highlightedSectionId === sectionId ? "report-section-highlight" : "")}
              id={sectionId}
              key={key}
            >
              {renderInlineMarkdown(cleanMarkdownText(trimmedLine), key)}
            </h1>
          );
        }
        if (/^##+\s*/.test(trimmedLine)) {
          sectionIndex += 1;
          const sectionId = reportSectionId(sectionIndex, cleanMarkdownText(trimmedLine));
          return (
            <div
              className={classNames("report-section-heading scroll-mt-4", highlightedSectionId === sectionId ? "report-section-highlight" : "")}
              id={sectionId}
              key={key}
            >
              <span>{renderInlineMarkdown(cleanMarkdownText(trimmedLine), key)}</span>
            </div>
          );
        }
        if (/^Sources[:：]$/i.test(trimmedLine)) {
          return (
            <h3 className="report-subheading" key={key}>
              信息来源
            </h3>
          );
        }
        if (/^[-*]\s+/.test(trimmedLine)) {
          const itemText = cleanMarkdownText(trimmedLine);
          return (
            <div className="report-list-item" key={key}>
              <span className="report-list-dot" />
              <span>{renderInlineMarkdown(itemText, key)}</span>
            </div>
          );
        }
        if (/^\d+\.\s+/.test(trimmedLine)) {
          const [numberLabel] = trimmedLine.match(/^\d+\./) || [""];
          const itemText = trimmedLine.replace(/^\d+\.\s+/, "");
          return (
            <div className="report-numbered-item" key={key}>
              <span className="report-number">{numberLabel}</span>
              <span>{renderInlineMarkdown(cleanMarkdownText(itemText), key)}</span>
            </div>
          );
        }
        if (/^[^：:]{2,24}[：:]$/.test(trimmedLine)) {
          return (
            <h3 className="report-subheading" key={key}>
              {renderInlineMarkdown(cleanMarkdownText(trimmedLine.replace(/[：:]$/, "")), key)}
            </h3>
          );
        }
        return (
          <p className="report-paragraph" key={key}>
            {renderInlineMarkdown(cleanMarkdownText(trimmedLine), key)}
          </p>
        );
      })}
    </div>
  );
}

function DisclaimerModal({ onAccept }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-lg border border-amber-300/30 bg-slate-900 p-5 shadow-2xl shadow-slate-950">
        <div className="mb-4 flex items-center gap-3">
          <ShieldCheck className="h-5 w-5 text-amber-200" />
          <h2 className="text-lg font-semibold text-slate-100">使用前确认</h2>
        </div>
        <div className="space-y-3 text-sm leading-6 text-slate-300">
          <p>DeepAlpha 生成的是研究辅助内容，不构成投资建议、交易指令或收益承诺。</p>
          <p>行情、新闻、模型输出和自动匹配股票代码都可能存在延迟或误差，正式决策前请结合权威数据源和专业判断复核。</p>
        </div>
        <button
          className="mt-5 inline-flex w-full items-center justify-center rounded-md bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-cyan-300"
          onClick={onAccept}
          type="button"
        >
          我已理解并继续
        </button>
      </div>
    </div>
  );
}

function AccessCodeModal({ value, onChange, onCancel, onSubmit }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-lg border border-cyan-300/30 bg-slate-900 p-5 shadow-2xl shadow-slate-950">
        <div className="mb-4 flex items-center gap-3">
          <ShieldCheck className="h-5 w-5 text-cyan-200" />
          <h2 className="text-lg font-semibold text-slate-100">请输入访问码</h2>
        </div>
        <p className="text-sm leading-6 text-slate-400">
          为控制报告生成成本，当前环境需要访问码后才能生成投研报告。
        </p>
        <input
          className="mt-4 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-cyan-400"
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") onSubmit();
          }}
          placeholder="访问码"
          type="password"
          value={value}
        />
        <div className="mt-5 grid grid-cols-2 gap-3">
          <button
            className="rounded-md border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:border-slate-500"
            onClick={onCancel}
            type="button"
          >
            稍后再说
          </button>
          <button
            className="rounded-md bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-cyan-300 disabled:opacity-50"
            disabled={!value.trim()}
            onClick={onSubmit}
            type="button"
          >
            保存访问码
          </button>
        </div>
      </div>
    </div>
  );
}

function DeepAlphaLogo({ compact = false }) {
  return (
    <div
      className={classNames(
        "relative flex shrink-0 items-center justify-center overflow-hidden rounded-md border border-cyan-300/40 bg-slate-950 shadow-lg shadow-cyan-950/40",
        compact ? "h-10 w-10" : "h-14 w-14",
      )}
      aria-label="DeepAlpha logo"
    >
      <div className="absolute h-10 w-10 rounded-full border border-emerald-300/30" />
      <div className="absolute h-7 w-7 rotate-45 rounded-sm border border-cyan-300/40" />
      <div className="absolute bottom-2 left-2 h-1.5 w-1.5 rounded-full bg-emerald-300" />
      <div className="absolute right-2 top-2 h-1.5 w-1.5 rounded-full bg-cyan-300" />
      <span className={classNames("relative font-black text-cyan-100", compact ? "text-xl" : "text-2xl")}>α</span>
    </div>
  );
}

function TradingViewFallback({ symbol }) {
  const containerRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current || !symbol) return undefined;

    containerRef.current.innerHTML = "";
    const widgetContainer = document.createElement("div");
    widgetContainer.className = "tradingview-widget-container";
    widgetContainer.style.height = "100%";
    widgetContainer.style.width = "100%";

    const widget = document.createElement("div");
    widget.className = "tradingview-widget-container__widget";
    widget.style.height = "100%";
    widget.style.width = "100%";

    const script = document.createElement("script");
    script.type = "text/javascript";
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.async = true;
    script.text = JSON.stringify({
      autosize: true,
      symbol,
      interval: "D",
      timezone: "Etc/UTC",
      theme: "dark",
      style: "1",
      locale: "zh_CN",
      allow_symbol_change: true,
      calendar: false,
      details: false,
      hide_side_toolbar: true,
      hide_top_toolbar: false,
      hide_legend: false,
      hide_volume: false,
      hotlist: false,
      save_image: false,
      withdateranges: true,
      backgroundColor: "#020617",
      gridColor: "rgba(30, 41, 59, 0.65)",
      studies: [],
      support_host: "https://www.tradingview.com",
    });
    widgetContainer.appendChild(widget);
    widgetContainer.appendChild(script);
    containerRef.current.appendChild(widgetContainer);

    return () => {
      if (containerRef.current) containerRef.current.innerHTML = "";
    };
  }, [symbol]);

  return <div ref={containerRef} className="h-[320px] w-full overflow-hidden rounded-md bg-slate-950" />;
}

function MarketChart({ symbol, displaySymbol, provider, exchange = "", tradingViewSymbol, searchQuery = "" }) {
  const [chartData, setChartData] = useState(null);
  const [chartStatus, setChartStatus] = useState("idle");
  const fallbackSymbol = tradingViewSymbol || displaySymbol || symbol;
  const tradingViewUrl = getTradingViewUrl(fallbackSymbol, searchQuery);

  useEffect(() => {
    if (!symbol) {
      setChartData(null);
      setChartStatus("idle");
      return undefined;
    }

    if (provider === "tradingview") {
      setChartData(null);
      setChartStatus("tradingview");
      return undefined;
    }

    const controller = new AbortController();
    setChartStatus("loading");
    requestJson(`/market/chart?symbol=${encodeURIComponent(symbol)}&exchange=${encodeURIComponent(exchange)}&range=6mo&interval=1d&provider=${encodeURIComponent(provider)}`, {
      signal: controller.signal,
    })
      .then((data) => {
        setChartData(data);
        setChartStatus(data.points?.length ? "ready" : "empty");
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setChartData(null);
          setChartStatus("empty");
        }
      });

    return () => controller.abort();
  }, [symbol, provider]);

  if (!symbol) {
    return (
      <div className="flex h-[420px] flex-col items-center justify-center gap-3 rounded-md border border-slate-800 bg-slate-950/70 px-6 text-center text-sm text-slate-400">
        <div>请输入或选择股票代码以查看 K 线。</div>
        <a
          className="inline-flex rounded-md border border-cyan-300/40 px-3 py-2 text-xs text-cyan-100 hover:border-cyan-300"
          href={tradingViewUrl}
          rel="noreferrer"
          target="_blank"
        >
          去 TradingView 搜索
        </a>
      </div>
    );
  }

  if (chartStatus === "loading") {
    return (
      <div className="flex h-[420px] items-center justify-center rounded-md border border-slate-800 bg-slate-950/70 text-sm text-slate-400">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        正在从行情 provider 加载数据...
      </div>
    );
  }

  if (provider === "tradingview" || chartStatus === "tradingview") {
    return (
      <div className="h-[420px] rounded-md border border-slate-800 bg-slate-950 p-4">
        <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-slate-100">{displaySymbol || symbol}</div>
            <div className="mt-1 text-xs text-slate-500">TradingView · 实时嵌入 K 线</div>
          </div>
        </div>
        <TradingViewFallback symbol={fallbackSymbol} />
        <div className="mt-3 text-xs text-slate-500">
          当前使用 TradingView 直接加载图表，不请求后端行情源。
        </div>
      </div>
    );
  }

  const points = chartData?.points || [];
  if (!points.length) {
    return (
      <div className="h-[420px] rounded-md border border-slate-800 bg-slate-950 p-4">
        <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-slate-100">{displaySymbol || symbol}</div>
            <div className="mt-1 text-xs text-slate-500">
              TradingView fallback · {provider.toUpperCase()} 暂未返回后端行情点位
            </div>
          </div>
        </div>
        <TradingViewFallback symbol={fallbackSymbol} />
        <div className="mt-3 text-xs text-slate-500">
          后端行情源不可用时，图表由 TradingView 直接加载。
        </div>
      </div>
    );
  }

  const width = 760;
  const height = 320;
  const padding = 28;
  const closes = points.map((point) => point.close);
  const minClose = Math.min(...closes);
  const maxClose = Math.max(...closes);
  const priceRange = maxClose - minClose || 1;
  const path = points
    .map((point, index) => {
      const x = padding + (index / Math.max(points.length - 1, 1)) * (width - padding * 2);
      const y = height - padding - ((point.close - minClose) / priceRange) * (height - padding * 2);
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
  const first = points[0];
  const latest = points[points.length - 1];
  const change = latest.close - first.close;
  const changePercent = first.close ? (change / first.close) * 100 : 0;
  const isUp = change >= 0;
  const latestDate = new Date(latest.time * 1000).toLocaleDateString("zh-CN");
  return (
    <div className="h-[420px] rounded-md border border-slate-800 bg-slate-950 p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-slate-100">{displaySymbol || symbol}</div>
          <div className="mt-1 text-xs text-slate-500">
            {chartData.symbol || symbol} · {chartData.exchange || ""} {chartData.currency ? `· ${chartData.currency}` : ""}
          </div>
        </div>
        <div className="text-right">
          <div className="text-lg font-semibold text-slate-100">{latest.close.toFixed(2)}</div>
          <div className={classNames("text-xs", isUp ? "text-emerald-300" : "text-red-300")}>
            {isUp ? "+" : ""}
            {change.toFixed(2)} ({isUp ? "+" : ""}
            {changePercent.toFixed(2)}%)
          </div>
          <div className="mt-2 flex flex-wrap justify-end gap-2">
            {(chartData.source_url || chartData.yahoo_chart_url) && (
              <a
                className="inline-flex rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:border-cyan-400 hover:text-cyan-200"
                href={chartData.source_url || chartData.yahoo_chart_url}
                rel="noreferrer"
                target="_blank"
              >
                打开来源 K 线
              </a>
            )}
            <a
              className="inline-flex rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:border-cyan-400 hover:text-cyan-200"
              href={tradingViewUrl}
              rel="noreferrer"
              target="_blank"
            >
              打开 TradingView
            </a>
          </div>
        </div>
      </div>
      <svg className="h-[320px] w-full" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${symbol} market chart`}>
        <defs>
          <linearGradient id="chartFill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={isUp ? "#22c55e" : "#ef4444"} stopOpacity="0.28" />
            <stop offset="100%" stopColor={isUp ? "#22c55e" : "#ef4444"} stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 1, 2, 3].map((line) => {
          const y = padding + line * ((height - padding * 2) / 3);
          return <line stroke="#1e293b" strokeWidth="1" x1={padding} x2={width - padding} y1={y} y2={y} key={line} />;
        })}
        <path d={`${path} L ${width - padding} ${height - padding} L ${padding} ${height - padding} Z`} fill="url(#chartFill)" />
        <path d={path} fill="none" stroke={isUp ? "#34d399" : "#fb7185"} strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" />
        <text fill="#64748b" fontSize="12" x={padding} y={height - 6}>
          6M
        </text>
        <text fill="#64748b" fontSize="12" textAnchor="end" x={width - padding} y={height - 6}>
          {latestDate}
        </text>
        <text fill="#94a3b8" fontSize="12" textAnchor="end" x={width - 8} y={padding + 4}>
          {maxClose.toFixed(2)}
        </text>
        <text fill="#94a3b8" fontSize="12" textAnchor="end" x={width - 8} y={height - padding}>
          {minClose.toFixed(2)}
        </text>
      </svg>
    </div>
  );
}

function ProjectIntro({ onBack }) {
  return (
    <div className="min-h-screen bg-slate-950 p-6 text-slate-100">
      <button
        className="mb-6 inline-flex items-center gap-2 rounded-md border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:border-cyan-400 hover:text-cyan-200"
        onClick={onBack}
      >
        <ArrowLeft className="h-4 w-4" />
        返回工作台
      </button>
      <div className="mx-auto max-w-5xl">
        <div className="mb-8 border-b border-slate-800 pb-6">
          <h1 className="text-3xl font-bold">深研 Alpha / DeepAlpha</h1>
          <p className="mt-3 max-w-3xl text-slate-400">
            DeepAlpha 是一个多智能体虚拟投研团队，围绕 LangGraph、RAG、Chroma、Memory、Trace 和 Citation Checker 构建可解释的投研分析工作流。
          </p>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          {[
            ["项目定位", "多智能体虚拟投研团队，用于生成结构化投研报告。"],
            ["核心流程", "Planner -> RAG Retriever -> Analysts -> Risk Manager -> Committee -> Report。"],
            ["RAG 能力", "使用 Brave、BlockBeats、Tavily 与 Chroma Vector Store 提供行业上下文；检索失败时明确标记数据不可用。"],
            ["Memory 能力", "短期 thread memory + SQLite 长期研究历史和 Watchlist。"],
          ].map(([title, text]) => (
            <div className="rounded-lg border border-slate-800 bg-slate-900 p-5" key={title}>
              <h2 className="font-semibold text-cyan-200">{title}</h2>
              <p className="mt-2 text-sm leading-6 text-slate-400">{text}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function TechDocs({ architecture, backendOnline, onBack }) {
  return (
    <div className="min-h-screen bg-slate-950 p-4 text-slate-100 md:p-6">
      <header className="mb-6 flex flex-col gap-3 border-b border-slate-800 pb-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center gap-3">
          <DeepAlphaLogo />
          <div>
            <h1 className="text-2xl font-bold">技术说明</h1>
            <p className="text-sm text-slate-400">DeepAlpha 架构、Agent 工作流、RAG、Memory、Trace 与调试信息</p>
          </div>
        </div>
        <button
          className="inline-flex items-center gap-2 rounded-md border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:border-cyan-400 hover:text-cyan-200"
          onClick={onBack}
        >
          <ArrowLeft className="h-4 w-4" />
          返回工作台
        </button>
      </header>

      <main className="space-y-4">
        <section className="space-y-4">
          <Panel title="系统能力" icon={Network}>
            {architecture ? (
              <div className="space-y-4">
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                  <StatusBadge enabled={backendOnline} label={backendOnline ? "Backend Online" : "Backend Offline"} />
                  {Object.entries(architecture.capabilities || {}).map(([name, enabled]) => (
                    <StatusBadge enabled={enabled} label={name} key={name} />
                  ))}
                </div>
                <div>
                  <div className="mb-2 flex items-center gap-2 text-xs uppercase text-slate-500">
                    <Wrench className="h-3.5 w-3.5" />
                    Tools
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {architecture.tools?.map((tool) => (
                      <span className="rounded-md bg-slate-800 px-2 py-1 text-xs text-slate-300" key={tool}>
                        {tool}
                      </span>
                    ))}
                  </div>
                </div>
                <pre className="overflow-auto rounded-md bg-slate-950 p-3 text-xs text-slate-400">{architecture.architecture}</pre>
              </div>
            ) : (
              <p className="text-sm text-slate-500">暂无架构诊断信息。</p>
            )}
          </Panel>

          <Panel title="Agent 工作流" icon={Brain}>
            <div className="space-y-4">
              <div className="rounded-md border border-slate-800 bg-slate-950/70 p-3">
                <div className="mb-2 text-xs font-semibold uppercase text-cyan-200">串行头部</div>
                <div className="grid gap-2 sm:grid-cols-2">
                  {[
                    ["Planner", "分析市场与财报，制定研究计划。"],
                    ["RAG Retriever", "检索行业上下文、竞品与监管背景。"],
                  ].map(([title, text]) => (
                    <div className="rounded border border-slate-800 bg-slate-900/60 p-2" key={title}>
                      <span className="text-xs font-semibold text-slate-200">{title}</span>
                      <p className="mt-1 text-[11px] leading-5 text-slate-500">{text}</p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-md border border-cyan-400/20 bg-cyan-400/5 p-3">
                <div className="mb-2 text-xs font-semibold uppercase text-cyan-200">并行组 1 · 7 位分析师</div>
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                  {[
                    ["Industry", "行业格局"],
                    ["Fundamental", "商业模式"],
                    ["Financial", "财报分析"],
                    ["Valuation", "估值情景"],
                    ["Technical", "技术面"],
                    ["News", "新闻事件"],
                    ["Sentiment", "市场情绪"],
                  ].map(([name, desc]) => (
                    <div className="rounded border border-slate-800 bg-slate-900/60 p-2" key={name}>
                      <span className="text-xs font-semibold text-slate-200">{name}</span>
                      <p className="mt-0.5 text-[11px] text-slate-500">{desc}</p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-md border border-amber-400/20 bg-amber-400/5 p-3">
                <div className="mb-2 text-xs font-semibold uppercase text-amber-200">并行组 2 · 多空辩论</div>
                <div className="grid gap-2 sm:grid-cols-2">
                  {[
                    ["Bull Analyst", "归纳看多论点与证据。"],
                    ["Bear Analyst", "归纳看空论点与风险。"],
                  ].map(([title, text]) => (
                    <div className="rounded border border-slate-800 bg-slate-900/60 p-2" key={title}>
                      <span className="text-xs font-semibold text-slate-200">{title}</span>
                      <p className="mt-1 text-[11px] leading-5 text-slate-500">{text}</p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-md border border-violet-400/20 bg-violet-400/5 p-3">
                <div className="mb-2 text-xs font-semibold uppercase text-violet-200">并行组 3 · 审查校验</div>
                <div className="grid gap-2 sm:grid-cols-3">
                  {[
                    ["Trader", "交易假设"],
                    ["Risk Manager", "风控审查"],
                    ["Source Quality", "来源质量评级"],
                  ].map(([title, text]) => (
                    <div className="rounded border border-slate-800 bg-slate-900/60 p-2" key={title}>
                      <span className="text-xs font-semibold text-slate-200">{title}</span>
                      <p className="mt-1 text-[11px] leading-5 text-slate-500">{text}</p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-md border border-slate-800 bg-slate-950/70 p-3">
                <div className="mb-2 text-xs font-semibold uppercase text-slate-300">串行尾部</div>
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                  {[
                    ["Committee", "综合决策"],
                    ["Report", "Markdown 渲染"],
                    ["Editor", "清理润色"],
                    ["Citation Check", "引用验证"],
                  ].map(([title, text]) => (
                    <div className="rounded border border-slate-800 bg-slate-900/60 p-2" key={title}>
                      <span className="text-xs font-semibold text-slate-200">{title}</span>
                      <p className="mt-1 text-[11px] leading-5 text-slate-500">{text}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </Panel>
        </section>
      </main>
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState("home");
  const [companyName, setCompanyName] = useState("Tesla");
  const [ticker, setTicker] = useState("NASDAQ:TSLA");
  const [watchlistCompany, setWatchlistCompany] = useState("");
  const [watchlistImportText, setWatchlistImportText] = useState("");
  const [watchlistImportResults, setWatchlistImportResults] = useState(null);
  const [runtimeConfig, setRuntimeConfig] = useState(null);
  const [architecture, setArchitecture] = useState(null);
  const [watchlist, setWatchlist] = useState([]);
  const [history, setHistory] = useState([]);
  const [reportResult, setReportResult] = useState(null);
  const [backendOnline, setBackendOnline] = useState(false);
  const [loading, setLoading] = useState("");
  const [reportTask, setReportTask] = useState(null);
  const [reportQuestion, setReportQuestion] = useState("");
  const [reportStrategy, setReportStrategy] = useState("general");
  const [reportSearchMode, setReportSearchMode] = useState("auto");
  const [reportChatHistory, setReportChatHistory] = useState([]);
  const [reportChatLoading, setReportChatLoading] = useState(false);
  const [reportChatError, setReportChatError] = useState("");
  const [highlightedReportSection, setHighlightedReportSection] = useState("");
  const [marketReview, setMarketReview] = useState(null);
  const [remoteSymbol, setRemoteSymbol] = useState(null);
  const [symbolCandidates, setSymbolCandidates] = useState([]);
  const [symbolLookupStatus, setSymbolLookupStatus] = useState("idle");
  const [stockIndex, setStockIndex] = useState([]);
  const [marketProvider, setMarketProvider] = useState("auto");
  const backendMarketProvider = marketProvider === "tradingview" ? "auto" : marketProvider;
  const [financialProfile, setFinancialProfile] = useState(null);
  const [financialStatus, setFinancialStatus] = useState("idle");
  const [error, setError] = useState("");
  const [accessCodeInput, setAccessCodeInput] = useState(() => window.localStorage.getItem(ACCESS_CODE_STORAGE_KEY) || "");
  const [accessCodePromptOpen, setAccessCodePromptOpen] = useState(false);
  const [disclaimerAccepted, setDisclaimerAccepted] = useState(() => window.localStorage.getItem(DISCLAIMER_STORAGE_KEY) === "true");

  const generatedThreadId = useMemo(() => {
    const safeName = companyName.trim().replace(/\s+/g, "-") || "company";
    return `react-${safeName}-${Date.now()}`;
  }, [companyName]);

  function selectCompany(company, nextTicker) {
    setCompanyName(company);
    setTicker(nextTicker);
    setRemoteSymbol(buildRecommendedSelection(company, nextTicker));
    setSymbolCandidates([]);
    setSymbolLookupStatus("selected");
  }

  function syncTickerFromCompany(value) {
    setCompanyName(value);
    setRemoteSymbol(null);
    setSymbolCandidates([]);
    setFinancialProfile(null);
    setFinancialStatus("idle");
    if (!value.trim()) {
      setTicker("");
      setSymbolLookupStatus("idle");
    } else {
      setTicker("");
      setSymbolLookupStatus("searching");
    }
  }

  function selectSymbolCandidate(candidate) {
    setRemoteSymbol(candidate);
    setTicker(candidate.ticker || candidate.symbol || "");
    setSymbolLookupStatus("selected");
  }

  async function loadDashboardData(targetCompany = companyName) {
    setError("");
    try {
      const [healthData, configData, watchlistData, historyData, marketReviewData] = await Promise.all([
        requestJson("/health"),
        requestJson("/config"),
        requestJson("/memory/watchlist"),
        requestJson("/memory/history"),
        requestJson("/market/review?market=auto"),
      ]);
      setBackendOnline(healthData.status === "ok");
      setRuntimeConfig(configData);
      setWatchlist(watchlistData);
      setHistory(historyData);
      setMarketReview(marketReviewData);
    } catch (err) {
      setBackendOnline(false);
      setError("无法连接 FastAPI 后端，请先启动：uvicorn app.main:app --reload");
      return;
    }

    try {
      const architectureData = await requestJson("/debug/architecture");
      setArchitecture(architectureData);
    } catch (err) {
      setArchitecture(null);
    }
  }

  async function loadHistoryDetail(record) {
    setError("");
    setLoading("history");
    try {
      const detail = await requestJson(`/memory/history/detail/${record.id}`);
      // The detail.result contains the full _build_report_response payload
      // (final_report, markdown_report, analysis_context, source_quality, etc.)
      const reportPayload = detail.result || {};
      setReportResult({
        ...reportPayload,
        // Ensure markdown_report is always set from either source.
        markdown_report: reportPayload.markdown_report || detail.markdown_report || "",
        company_name: detail.company_name,
      });
      // Synthetic task so the right panel renders the report view.
      setReportTask({ status: "success", task_id: null, steps: [] });
      setReportChatHistory([]);
      setReportChatError("");
      setHighlightedReportSection("");
    } catch (err) {
      setError("加载历史报告失败，请确认后端已启动。");
    } finally {
      setLoading("");
    }
  }

  function acceptDisclaimer() {
    window.localStorage.setItem(DISCLAIMER_STORAGE_KEY, "true");
    setDisclaimerAccepted(true);
  }

  function saveAccessCode() {
    window.localStorage.setItem(ACCESS_CODE_STORAGE_KEY, accessCodeInput.trim());
    setAccessCodePromptOpen(false);
    setError("");
  }

  function exportReportPdf() {
    if (!reportResult?.markdown_report) return;

    const originalTitle = document.title;
    const reportName = reportResult.company_name || selectedCompanyName || companyName.trim() || "DeepAlpha";
    document.title = `DeepAlpha-${reportName}-投研报告`;
    window.print();
    window.setTimeout(() => {
      document.title = originalTitle;
    }, 500);
  }

  useEffect(() => {
    loadDashboardData();
  }, []);

  useEffect(() => {
    const taskId = window.localStorage.getItem(LAST_REPORT_TASK_STORAGE_KEY);
    if (!taskId) return;
    requestJson(`/report/tasks/${taskId}`)
      .then((task) => {
        if (task.status === "success" && task.result?.markdown_report) {
          setReportTask(task);
          setReportResult(task.result);
        }
      })
      .catch(() => window.localStorage.removeItem(LAST_REPORT_TASK_STORAGE_KEY));
  }, []);

  useEffect(() => {
    const taskId = reportTask?.task_id;
    if (!taskId || reportTask?.status !== "success" || !reportResult?.markdown_report) return;
    requestJson(`/chat/report/${taskId}/history`)
      .then((data) => setReportChatHistory(data.items || []))
      .catch(() => setReportChatError("历史追问加载失败，本次仍可继续提问。"));
  }, [reportTask?.task_id, reportTask?.status, reportResult?.markdown_report, accessCodePromptOpen]);

  useEffect(() => {
    let mounted = true;

    loadStockIndex()
      .then((items) => {
        if (mounted) setStockIndex(items);
      })
      .catch(() => {
        if (mounted) setStockIndex([]);
      });

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    const query = companyName.trim();
    if (!query) {
      setSymbolCandidates([]);
      setSymbolLookupStatus("idle");
      return undefined;
    }

    const localMatches = searchStockIndex(query, stockIndex);
    const immediateMatches = localMatches.length ? localMatches : findLocalFallbackMatches(query);
    if (immediateMatches.length) {
      setSymbolCandidates(immediateMatches);
      if (shouldAutoSelectSymbol(immediateMatches)) {
        selectSymbolCandidate(immediateMatches[0]);
      } else {
        setSymbolLookupStatus("candidates");
      }
    } else {
      setSymbolCandidates([]);
      setSymbolLookupStatus("searching");
    }

    const controller = new AbortController();
    const timeoutId = window.setTimeout(async () => {
      if (!immediateMatches.length) {
        setSymbolLookupStatus("searching");
      }
      try {
        const data = await requestJson(`/symbol/lookup?query=${encodeURIComponent(query)}`, {
          signal: controller.signal,
        });
        const matches = data.matches || data.candidates || [];
        if (!matches.length) {
          const fallbackMatches = immediateMatches.length ? immediateMatches : findLocalFallbackMatches(query);
          setSymbolCandidates(fallbackMatches);
          if (shouldAutoSelectSymbol(fallbackMatches)) {
            selectSymbolCandidate(fallbackMatches[0]);
          } else {
            setSymbolLookupStatus(fallbackMatches.length ? "candidates" : "not_found");
          }
          return;
        }
        const mergedMatches = mergeSymbolCandidates(localMatches, matches);
        setSymbolCandidates(mergedMatches);
        if (shouldAutoSelectSymbol(mergedMatches, data)) {
          selectSymbolCandidate(mergedMatches[0]);
        } else {
          setSymbolLookupStatus("candidates");
        }
      } catch (err) {
        if (!controller.signal.aborted) {
          const fallbackMatches = immediateMatches.length ? immediateMatches : findLocalFallbackMatches(query);
          setSymbolCandidates(fallbackMatches);
          if (shouldAutoSelectSymbol(fallbackMatches)) {
            selectSymbolCandidate(fallbackMatches[0]);
          } else {
            setSymbolLookupStatus(fallbackMatches.length ? "candidates" : "not_found");
          }
        }
      }
    }, 500);

    return () => {
      controller.abort();
      window.clearTimeout(timeoutId);
    };
  }, [companyName, stockIndex]);

  async function runReport() {
    if (!companyName.trim()) {
      setError("请输入公司名称。");
      return;
    }
    if (!matchedSymbol || !ticker.trim()) {
      setError("请先从候选股票中选择一个结果。");
      return;
    }

    const finalThreadId = generatedThreadId;
    setLoading("report");
    setReportTask({ status: "queued", steps: [] });
    setReportResult(null);
    setReportQuestion("");
    setReportStrategy("general");
    setReportSearchMode("auto");
    setReportChatHistory([]);
    setReportChatError("");
    setError("");
    try {
      const task = await requestJson("/report/tasks", {
        method: "POST",
        body: JSON.stringify({
          company_name: selectedCompanyName,
          thread_id: finalThreadId,
          symbol: ticker.trim(),
          yahoo_symbol: yahooSymbol,
          exchange: matchedSymbol?.exchange || "",
          data_provider: backendMarketProvider,
        }),
      });
      setReportTask(task);

      let taskResult = null;
      for (let attempt = 0; attempt < 180; attempt += 1) {
        const status = await requestJson(`/report/tasks/${task.task_id}`);
        setReportTask(status);
        if (status.status === "success") {
          taskResult = status.result;
          break;
        }
        if (status.status === "failed") {
          throw new Error(status.error || "Report task failed");
        }
        await delay(1000);
      }

      if (!taskResult) {
        throw new Error("Report task timed out");
      }

      setReportResult(taskResult);
      window.localStorage.setItem(LAST_REPORT_TASK_STORAGE_KEY, task.task_id);
      await loadDashboardData(companyName.trim());
    } catch (err) {
      const message = String(err.message || "");
      if (message.includes("401")) {
        window.localStorage.removeItem(ACCESS_CODE_STORAGE_KEY);
        setAccessCodeInput("");
        setAccessCodePromptOpen(true);
        setError("请先输入有效访问码后再生成报告。");
      } else if (message.includes("429")) {
        setError("报告生成次数已达当前上限，请稍后再试。");
      } else {
        setError("Report 调用失败，请确认后端已启动。");
      }
    } finally {
      setLoading("");
    }
  }

  async function askReportQuestion() {
    const question = reportQuestion.trim();
    if (!question) {
      setReportChatError("请输入要围绕当前报告追问的问题。");
      return;
    }
    if (!reportResult?.markdown_report) {
      setReportChatError("请先生成报告。");
      return;
    }

    setReportChatLoading(true);
    setReportChatError("");
    try {
      const payload = {
        company_name: reportResult.company_name || selectedCompanyName,
        question,
        strategy: reportStrategy,
        search_mode: reportSearchMode,
      };
      if (reportTask?.task_id) {
        payload.task_id = reportTask.task_id;
      }
      payload.markdown_report = reportResult.markdown_report;
      const answer = await requestJson("/chat/report", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setReportChatHistory((items) => [
        ...items,
        {
          id: `${Date.now()}-${items.length}`,
          question,
          strategy: reportStrategy,
          search_mode: reportSearchMode,
          ...answer,
        },
      ]);
      setReportQuestion("");
    } catch (err) {
      const message = String(err.message || "");
      const detail = message.replace(/^HTTP \d+:\s*/, "");
      setReportChatError(
        message.startsWith("HTTP 503:")
          ? `模型服务暂时不可用：${detail}`
          : message.startsWith("HTTP ")
            ? `报告追问失败：${detail || message}`
            : "报告追问失败，请确认报告上下文仍然有效。",
      );
    } finally {
      setReportChatLoading(false);
    }
  }

  async function clearReportChatHistory() {
    const taskId = reportTask?.task_id;
    if (!taskId) return;
    setReportChatLoading(true);
    setReportChatError("");
    try {
      await requestJson(`/chat/report/${taskId}/history`, { method: "DELETE" });
      setReportChatHistory([]);
    } catch (err) {
      setReportChatError("清空追问历史失败，请稍后重试。");
    } finally {
      setReportChatLoading(false);
    }
  }

  function jumpToReportCitation(sectionId) {
    if (!sectionId) return;
    setHighlightedReportSection(sectionId);
    window.document.getElementById(sectionId)?.scrollIntoView({ behavior: "smooth", block: "start" });
    window.setTimeout(() => setHighlightedReportSection(""), 2200);
  }

  async function addWatchlistCompany() {
    const nextCompany = (watchlistCompany || companyName).trim();
    if (!nextCompany) {
      setError("请输入要关注的公司。");
      return;
    }

    setLoading("watchlist");
    setError("");
    try {
      await requestJson("/memory/watchlist", {
        method: "POST",
        body: JSON.stringify({
          company_name: nextCompany,
          symbol: ticker.trim(),
          yahoo_symbol: yahooSymbol,
          data_provider: backendMarketProvider,
        }),
      });
      setWatchlistCompany("");
      await loadDashboardData(companyName);
    } catch (err) {
      setError("添加 Watchlist 失败，请确认后端已启动。");
    } finally {
      setLoading("");
    }
  }

  function watchlistPayloadFromCandidate(candidate) {
    return {
      company_name: candidate.name || candidate.company || candidate.symbol,
      symbol: candidate.ticker || candidate.symbol,
      yahoo_symbol: candidate.raw_symbol || candidate.symbol,
      data_provider: backendMarketProvider,
    };
  }

  async function addWatchlistCandidate(candidate) {
    await requestJson("/memory/watchlist", {
      method: "POST",
      body: JSON.stringify(watchlistPayloadFromCandidate(candidate)),
    });
  }

  async function importWatchlistItems() {
    const items = parseWatchlistImportText(watchlistImportText);
    if (!items.length) {
      setError("请粘贴股票代码、名称或包含 symbol/name/company 的 CSV。");
      return;
    }

    setLoading("watchlist-import");
    setError("");
    try {
      const resolved = await requestJson("/symbol/resolve-batch", {
        method: "POST",
        body: JSON.stringify({ items }),
      });
      const autoItems = resolved.results.filter((item) => item.resolved);
      for (const item of autoItems) {
        await addWatchlistCandidate(item.resolved);
      }
      setWatchlistImportResults(resolved);
      await loadDashboardData(companyName);
    } catch (err) {
      setError("导入 Watchlist 失败，请确认后端已启动。");
    } finally {
      setLoading("");
    }
  }

  async function confirmWatchlistImportCandidate(candidate) {
    setLoading("watchlist-import");
    setError("");
    try {
      await addWatchlistCandidate(candidate);
      setWatchlistImportResults((current) => {
        if (!current) return current;
        return {
          ...current,
          results: current.results.map((item) => {
            const symbols = (item.candidates || []).map((entry) => entry.symbol);
            return symbols.includes(candidate.symbol)
              ? { ...item, resolved: candidate, candidates: [], needs_confirmation: false, error: null }
              : item;
          }),
        };
      });
      await loadDashboardData(companyName);
    } catch (err) {
      setError("添加候选股票失败，请稍后重试。");
    } finally {
      setLoading("");
    }
  }

  const matchedSymbol = remoteSymbol;
  const needsConfirmation = Boolean(symbolCandidates.length > 1 && !matchedSymbol);
  const yahooSymbol = toYahooSymbol(ticker, matchedSymbol);
  const selectedCompanyName = matchedSymbol?.name || matchedSymbol?.company || companyName.trim();
  const selectedExchange = matchedSymbol?.exchange || matchedSymbol?.market || "Auto";
  const selectedConfidence = typeof matchedSymbol?.confidence === "number" ? `${Math.round(matchedSymbol.confidence * 100)}%` : "N/A";

  useEffect(() => {
    if (!matchedSymbol || !yahooSymbol) {
      setFinancialProfile(null);
      setFinancialStatus("idle");
      return undefined;
    }

    const controller = new AbortController();
    setFinancialStatus("loading");
    requestJson(`/financials/latest?symbol=${encodeURIComponent(yahooSymbol)}&exchange=${encodeURIComponent(matchedSymbol.exchange || "")}`, {
      signal: controller.signal,
    })
      .then((data) => {
        setFinancialProfile(data);
        setFinancialStatus(data.enabled ? "ready" : "empty");
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setFinancialProfile({
            enabled: false,
            reason: "财报数据加载失败，请确认后端或 SEC 连接状态。",
          });
          setFinancialStatus("empty");
        }
      });

    return () => controller.abort();
  }, [matchedSymbol, yahooSymbol]);

  if (page === "intro") {
    return <ProjectIntro onBack={() => setPage("home")} />;
  }

  if (page === "tech" && runtimeConfig?.debug_routes_enabled) {
    return (
      <TechDocs
        architecture={architecture}
        backendOnline={backendOnline}
        onBack={() => setPage("home")}
      />
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 p-4 text-slate-100 md:p-6">
      {!disclaimerAccepted && <DisclaimerModal onAccept={acceptDisclaimer} />}
      {accessCodePromptOpen && (
        <AccessCodeModal
          onCancel={() => setAccessCodePromptOpen(false)}
          onChange={setAccessCodeInput}
          onSubmit={saveAccessCode}
          value={accessCodeInput}
        />
      )}
      <header className="mb-4 flex flex-col gap-3 border-b border-slate-800 pb-4 lg:flex-row lg:items-center lg:justify-between">
        <button className="text-left" onClick={() => setPage("intro")}>
          <div className="flex items-center gap-3">
            <DeepAlphaLogo compact />
            <div>
              <h1 className="text-xl font-bold">深研 Alpha / DeepAlpha</h1>
              <p className="text-sm text-slate-400">LangGraph Multi-Agent Research Console</p>
            </div>
          </div>
        </button>
        <div className="flex flex-wrap items-center gap-2">
          {runtimeConfig?.debug_routes_enabled && (
            <button
              className="inline-flex items-center gap-2 rounded-md border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:border-cyan-400 hover:text-cyan-200"
              onClick={() => setPage("tech")}
            >
              <Network className="h-4 w-4" />
              技术说明
            </button>
          )}
        </div>
      </header>

      {error && (
        <div className="mb-4 rounded-md border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      )}

      <main className="grid gap-4 xl:grid-cols-[280px_minmax(420px,1fr)_480px]">
        <aside className="space-y-4">
          <Panel title="推荐" icon={Star}>
            <div className="space-y-2">
              {RECOMMENDED_COMPANIES.map((item) => (
                <button
                  className={classNames(
                    "w-full rounded-md border px-3 py-2 text-left transition",
                    companyName === item.company
                      ? "border-cyan-400 bg-cyan-500/10"
                      : "border-slate-800 bg-slate-950/60 hover:border-slate-600",
                  )}
                  key={item.ticker}
                  onClick={() => selectCompany(item.company, item.ticker)}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-slate-100">{item.company}</span>
                    <span className="text-xs text-cyan-200">{item.ticker.replace("NASDAQ:", "")}</span>
                  </div>
                  <div className="mt-1 text-xs text-slate-500">{item.sector}</div>
                </button>
              ))}
            </div>
          </Panel>

          <Panel title="Watchlist" icon={BookOpen}>
            <div className="mb-3 flex gap-2">
              <input
                className="min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-400"
                value={watchlistCompany}
                onChange={(event) => setWatchlistCompany(event.target.value)}
                placeholder={companyName || "公司名称"}
              />
              <button
                className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-slate-700 text-slate-300 hover:border-cyan-400 hover:text-cyan-200 disabled:opacity-50"
                disabled={Boolean(loading)}
                onClick={addWatchlistCompany}
                title="添加关注"
              >
                {loading === "watchlist" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              </button>
            </div>
            <div className="mb-3 rounded-md border border-slate-800 bg-slate-950/70 p-3">
              <textarea
                className="min-h-20 w-full resize-y rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-400"
                onChange={(event) => setWatchlistImportText(event.target.value)}
                placeholder="粘贴多行或逗号分隔股票：600519, 0700.HK, NVDA, 智谱AI, 京东"
                value={watchlistImportText}
              />
              <button
                className="mt-2 inline-flex w-full items-center justify-center gap-2 rounded-md border border-cyan-300/40 px-3 py-2 text-sm text-cyan-100 hover:border-cyan-300 disabled:opacity-50"
                disabled={Boolean(loading)}
                onClick={importWatchlistItems}
                type="button"
              >
                {loading === "watchlist-import" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                智能导入
              </button>
              {watchlistImportResults && (
                <div className="mt-3 space-y-3 text-xs">
                  <div className="flex flex-wrap gap-2 text-slate-500">
                    <span>自动加入：{watchlistImportResults.resolved_count}</span>
                    <span>待确认：{watchlistImportResults.needs_confirmation_count}</span>
                    <span>失败：{watchlistImportResults.failed_count}</span>
                  </div>
                  {watchlistImportResults.results
                    .filter((item) => !item.resolved && item.candidates?.length)
                    .map((item) => (
                      <div className="rounded-md border border-amber-400/20 bg-amber-400/10 p-2" key={item.input}>
                        <div className="mb-2 text-amber-100">{item.input} 需要确认</div>
                        <div className="flex flex-wrap gap-2">
                          {item.candidates.slice(0, 3).map((candidate) => (
                            <button
                              className="rounded-md border border-slate-700 px-2 py-1 text-slate-200 hover:border-cyan-400 hover:text-cyan-100"
                              disabled={Boolean(loading)}
                              key={`${item.input}-${candidate.symbol}`}
                              onClick={() => confirmWatchlistImportCandidate(candidate)}
                              type="button"
                            >
                              {candidate.name || candidate.company || candidate.symbol} · {candidate.symbol}
                            </button>
                          ))}
                        </div>
                      </div>
                    ))}
                  {watchlistImportResults.results
                    .filter((item) => item.error && !item.candidates?.length)
                    .map((item) => (
                      <div className="rounded-md border border-red-400/20 bg-red-400/10 p-2 text-red-100" key={item.input}>
                        {item.input}：{item.error}
                      </div>
                    ))}
                </div>
              )}
            </div>
            {watchlist.length ? (
              <div className="space-y-2">
                {watchlist.slice(0, 8).map((item) => (
                  <div className="rounded-md border border-slate-800 bg-slate-950/70 p-3" key={item.company_name}>
                    <div className="font-medium">{item.company_name}</div>
                    <div className="mt-1 text-xs text-slate-500">最近分析：{item.last_analyzed_at || "尚未分析"}</div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-500">暂无关注列表。</p>
            )}
          </Panel>
        </aside>

        <section className="space-y-4">
          <Panel title="投研选择" icon={FileSearch}>
            <div className="grid gap-3">
              <label className="space-y-1 text-sm text-slate-400">
                搜索公司名称
                <input
                  className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-cyan-400"
                  value={companyName}
                  onChange={(event) => syncTickerFromCompany(event.target.value)}
                  placeholder="输入公司名、简称、拼音或股票代码，例如 美团、阿里、BABA"
                />
              </label>
            </div>

            <div className="mt-3 rounded-md border border-slate-800 bg-slate-950/70 p-3">
              <div className="mb-2 text-xs text-slate-500">已选股票</div>
              {matchedSymbol ? (
                <div className="grid gap-3 md:grid-cols-4">
                  <MetricCard label="Company" value={selectedCompanyName} icon={Building2} />
                  <MetricCard label="Symbol" value={ticker || "N/A"} icon={BarChart3} />
                  <MetricCard label="Yahoo" value={yahooSymbol || "N/A"} icon={TrendingUp} />
                  <MetricCard label="Confidence" value={selectedConfidence} icon={ShieldCheck} />
                </div>
              ) : symbolLookupStatus === "searching" ? (
                <div className="flex items-center gap-2 text-sm text-slate-400">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  正在解析公司和股票代码...
                </div>
              ) : symbolLookupStatus === "not_found" ? (
                <p className="text-sm text-amber-100">未找到，请换关键词。</p>
              ) : symbolCandidates.length ? (
                <p className="text-sm text-slate-400">请从下方候选股票中选择一个结果。</p>
              ) : (
                <p className="text-sm text-slate-500">输入关键词后，系统会返回候选股票列表。</p>
              )}
              {matchedSymbol && (
                <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <span>{selectedExchange}</span>
                  {matchedSymbol.source && <span>{matchedSymbol.source}</span>}
                </div>
              )}
            </div>

            {symbolCandidates.length > 0 && (
              <div className="mt-3 rounded-md border border-slate-800 bg-slate-950/70 p-3">
                <div className="mb-2 text-xs text-slate-500">候选股票</div>
                <div className="grid gap-2">
                  {symbolCandidates.slice(0, 5).map((candidate) => (
                    <button
                      className={classNames(
                        "rounded-md border px-3 py-2 text-left text-sm transition",
                        ticker === (candidate.ticker || candidate.symbol)
                          ? "border-cyan-400 bg-cyan-500/10 text-cyan-100"
                          : "border-slate-700 text-slate-300 hover:border-cyan-400 hover:text-cyan-200",
                      )}
                      key={`${candidate.symbol}-${candidate.exchange}`}
                      onClick={() => selectSymbolCandidate(candidate)}
                      type="button"
                    >
                      <span className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-semibold">{candidate.name || candidate.company}</span>
                        <span className="text-xs text-cyan-200">{candidate.symbol}</span>
                      </span>
                      <span className="mt-1 flex flex-wrap gap-2 text-xs text-slate-500">
                        <span>{candidate.exchange}</span>
                        <span>{candidate.market}</span>
                        <span>{Math.round((candidate.confidence || 0) * 100)}%</span>
                        <span>{candidate.source}</span>
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {needsConfirmation && (
              <p className="mt-3 rounded-md border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-xs leading-5 text-amber-100">
                该关键词存在多个候选股票，请选择具体上市市场后再生成报告。
              </p>
            )}

            <div className="mt-4 flex flex-wrap gap-2">
              <button
                className="inline-flex items-center gap-2 rounded-md bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-cyan-300 disabled:opacity-50"
                disabled={Boolean(loading)}
                onClick={runReport}
                title="生成投研报告"
              >
                {loading === "report" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                生成投研报告
              </button>
            </div>
          </Panel>

          <Panel title="市场复盘" icon={Activity}>
            <MarketReviewPanel review={marketReview} />
          </Panel>

          <Panel title="最新财报" icon={FileText}>
            <LatestFinancials profile={financialProfile} status={financialStatus} />
          </Panel>

          <Panel
            title="K 线"
            icon={BarChart3}
            action={
              <select
                className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200 outline-none focus:border-cyan-400"
                value={marketProvider}
                onChange={(event) => setMarketProvider(event.target.value)}
              >
                <option value="auto">Auto</option>
                <option value="yahoo">Yahoo</option>
                <option value="akshare">AkShare</option>
                <option value="efinance">Efinance</option>
                <option value="baostock">Baostock</option>
                <option value="finnhub">Finnhub</option>
                <option value="tradingview">TradingView</option>
              </select>
            }
          >
            <MarketChart
              displaySymbol={ticker}
              exchange={matchedSymbol?.exchange || ""}
              provider={marketProvider}
              searchQuery={companyName}
              symbol={yahooSymbol}
              tradingViewSymbol={ticker}
            />
          </Panel>
        </section>

        <aside className="space-y-4">
          <Panel title="投研报告生成" icon={FileText}>
            <ReportTaskProgress task={reportTask} />
            {reportResult?.markdown_report ? (
              <div className="mt-4 space-y-4">
                <div className="grid grid-cols-3 gap-2">
                  <MetricCard label="Decision" value={reportResult.final_report?.recommendation} icon={TrendingUp} />
                  <MetricCard label="Confidence" value={reportResult.final_report?.confidence} icon={ShieldCheck} />
                  <MetricCard label="Sources" value={reportResult.final_report?.sources_count} icon={Database} />
                </div>
                <ExecutiveSummaryCard content={reportResult.markdown_report} />
                <DataQualityBar analysisContext={reportResult.analysis_context} />
                <div className="grid gap-3 lg:grid-cols-2">
                  <SourceQualitySummary sourceQuality={reportResult.source_quality} />
                  <CitationCheckSummary citationCheck={reportResult.citation_check} />
                  <ReportEditorSummary editor={reportResult.report_editor} />
                  {reportResult.trace_summary?.duration_seconds != null && (
                    <div className="rounded-md border border-slate-800 bg-slate-950/70 p-3">
                      <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase text-slate-300">
                        <Clock3 className="h-3.5 w-3.5 text-cyan-300" />
                        执行追踪
                      </div>
                      <div className="grid grid-cols-3 gap-2">
                        <CompactMetric label="耗时" value={`${Math.round(reportResult.trace_summary.duration_seconds)}s`} tone="slate" />
                        <CompactMetric label="步数" value={reportResult.trace_summary.steps_count} tone="slate" />
                        <CompactMetric label="ID" value={reportResult.trace_summary.trace_id?.slice(0, 8) || "N/A"} tone="slate" />
                      </div>
                    </div>
                  )}
                </div>
                <div className="rounded-md border border-amber-400/20 bg-amber-400/10 px-3 py-2 text-xs leading-5 text-amber-100">
                  本报告为研究辅助输出，不构成投资建议。请结合交易所公告、公司财报与专业判断复核。
                </div>
                <button
                  className="inline-flex w-full items-center justify-center gap-2 rounded-md border border-cyan-300/40 bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-cyan-300"
                  onClick={exportReportPdf}
                  type="button"
                >
                  <Download className="h-4 w-4" />
                  导出报告 PDF
                </button>
                <ReportTOC content={reportResult.markdown_report} onJump={jumpToReportCitation} />
                <div className="max-h-[640px] overflow-auto rounded-md border border-slate-800 bg-slate-950 p-4 text-sm leading-6 text-slate-300">
                  <MarkdownReport content={reportResult.markdown_report} highlightedSectionId={highlightedReportSection} />
                </div>
                <div className="space-y-3 rounded-md border border-cyan-400/20 bg-slate-950/80 p-4">
                  <div className="flex items-center gap-2">
                    <MessageCircle className="h-4 w-4 text-cyan-300" />
                    <h3 className="text-sm font-semibold text-slate-100">继续追问</h3>
                    {reportChatHistory.length > 0 && (
                      <button
                        className="ml-auto text-xs text-slate-500 hover:text-red-200"
                        disabled={reportChatLoading}
                        onClick={clearReportChatHistory}
                        type="button"
                      >
                        清空历史
                      </button>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <select
                      className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-400"
                      value={reportStrategy}
                      onChange={(event) => setReportStrategy(event.target.value)}
                      disabled={reportChatLoading}
                    >
                      <option value="general">综合</option>
                      <option value="risk">风险</option>
                      <option value="valuation">估值</option>
                      <option value="technical">技术面</option>
                      <option value="news">新闻</option>
                    </select>
                    <select
                      className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-400"
                      value={reportSearchMode}
                      onChange={(event) => setReportSearchMode(event.target.value)}
                      disabled={reportChatLoading}
                    >
                      <option value="auto">自动检索</option>
                      <option value="report_only">仅报告</option>
                      <option value="web">联网补充</option>
                    </select>
                  </div>
                  <textarea
                    className="w-full resize-y rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-600 focus:border-cyan-400"
                    rows={3}
                    value={reportQuestion}
                    onChange={(event) => setReportQuestion(event.target.value)}
                    placeholder="例如：这份报告里最需要持续验证的风险是什么？"
                    disabled={reportChatLoading}
                  />
                  <button
                    className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-60"
                    onClick={askReportQuestion}
                    type="button"
                    disabled={reportChatLoading}
                  >
                    {reportChatLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                    {reportChatLoading ? "分析中" : "提问"}
                  </button>
                  {reportChatError && (
                    <div className="rounded-md border border-red-400/25 bg-red-400/10 px-3 py-2 text-sm text-red-100">
                      {reportChatError}
                    </div>
                  )}
                  {reportChatHistory.length > 0 && (
                    <div className="space-y-4">
                      {reportChatHistory.map((item, idx) => {
                        const itemKey = item.message_id || item.id || `${item.created_at}-${item.question}`;
                        const hasExtras = (item.key_points?.length || 0) + (item.risks?.length || 0) + (item.cited_sources?.length || 0) + (item.report_citations?.length || 0) + (item.web_citations?.length || 0) > 0;
                        return (
                        <article className={classNames("rounded-md border border-slate-800 bg-slate-900/80 p-4", idx > 0 && "border-t border-slate-700/50 pt-4")} key={itemKey}>
                          <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
                            <span className="font-semibold uppercase text-cyan-300">{item.strategy}</span>
                            <span className="text-slate-500">·</span>
                            <span>{item.search_mode || item.route?.mode}</span>
                            {item.route?.web_status && item.route.web_status !== "not_requested" && (
                              <>
                                <span className="text-slate-500">·</span>
                                <span className={item.route.web_status === "success" ? "text-emerald-300" : "text-amber-300"}>
                                  Web: {item.route.web_status}
                                </span>
                              </>
                            )}
                            {(item.freshness?.report_generated_at || item.freshness?.web_retrieved_at) && (
                              <>
                                <span className="text-slate-500">·</span>
                                <span>{item.freshness?.report_generated_at || item.freshness?.web_retrieved_at}</span>
                              </>
                            )}
                          </div>
                          <div className="mt-2 text-sm font-semibold text-slate-100">问：{item.question}</div>
                          <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-300">{item.answer}</p>
                          {item.data_quality_warning && (
                            <div className="mt-3 rounded-md border border-amber-400/20 bg-amber-400/10 px-3 py-2 text-xs leading-5 text-amber-100">
                              {item.data_quality_warning}
                            </div>
                          )}
                          {hasExtras && (
                            <details className="mt-3 group">
                              <summary className="cursor-pointer text-xs text-slate-500 hover:text-slate-300 select-none">
                                展开详情 · {[
                                  item.key_points?.length && `${item.key_points.length} 要点`,
                                  item.risks?.length && `${item.risks.length} 风险`,
                                  item.cited_sources?.length && `${item.cited_sources.length} 来源`,
                                  item.report_citations?.length && `${item.report_citations.length} 证据`,
                                  item.web_citations?.length && `${item.web_citations.length} 联网`,
                                ].filter(Boolean).join(" · ")}
                              </summary>
                              <div className="mt-3 space-y-3">
                                {item.key_points?.length > 0 && (
                                  <div>
                                    <div className="text-xs font-semibold text-slate-400">关键要点</div>
                                    <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-300">
                                      {item.key_points.map((point, index) => <li key={`${itemKey}-point-${index}`}>{point}</li>)}
                                    </ul>
                                  </div>
                                )}
                                {item.risks?.length > 0 && (
                                  <div>
                                    <div className="text-xs font-semibold text-amber-300">风险</div>
                                    <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-amber-100">
                                      {item.risks.map((risk, index) => <li key={`${itemKey}-risk-${index}`}>{risk}</li>)}
                                    </ul>
                                  </div>
                                )}
                                {item.cited_sources?.length > 0 && (
                                  <div className="flex flex-wrap gap-2">
                                    {item.cited_sources.map((source) => (
                                      <a
                                        className="rounded-md border border-cyan-300/30 px-2 py-1 text-xs text-cyan-100 hover:border-cyan-300"
                                        href={safeReportUrl(source.url)}
                                        key={`${itemKey}-${source.url}`}
                                        rel="noreferrer"
                                        target="_blank"
                                      >
                                        {source.title || source.url}
                                      </a>
                                    ))}
                                  </div>
                                )}
                                {item.report_citations?.length > 0 && (
                                  <div className="space-y-2">
                                    <div className="text-xs font-semibold text-cyan-300">报告证据</div>
                                    {item.report_citations.map((citation, index) => (
                                      <button
                                        className="block w-full rounded-md border border-cyan-300/20 bg-cyan-400/5 p-2 text-left text-xs leading-5 text-slate-300 hover:border-cyan-300/50"
                                        key={`${itemKey}-report-citation-${index}`}
                                        onClick={() => jumpToReportCitation(citation.section_id)}
                                        type="button"
                                      >
                                        <span className="font-semibold text-cyan-100">{citation.section_title}</span>
                                        <span className="mt-1 block">"{citation.excerpt}"</span>
                                      </button>
                                    ))}
                                  </div>
                                )}
                                {item.web_citations?.length > 0 && (
                                  <div className="space-y-2">
                                    <div className="text-xs font-semibold text-violet-300">联网新增证据</div>
                                    {item.web_citations.map((citation) => (
                                      <a
                                        className="block rounded-md border border-violet-300/20 bg-violet-400/5 p-2 text-xs leading-5 text-slate-300 hover:border-violet-300/50"
                                        href={safeReportUrl(citation.url)}
                                        key={`${itemKey}-${citation.url}`}
                                        rel="noreferrer"
                                        target="_blank"
                                      >
                                        <span className="font-semibold text-violet-100">{citation.title}</span>
                                        {citation.published_at && <span className="ml-2 text-slate-500">{citation.published_at}</span>}
                                        {citation.snippet && <span className="mt-1 block">{citation.snippet}</span>}
                                      </a>
                                    ))}
                                  </div>
                                )}
                              </div>
                            </details>
                          )}
                        </article>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            ) : reportResult ? (
              <div className="rounded-md border border-amber-400/25 bg-amber-400/10 p-3 text-sm leading-6 text-amber-100">
                该历史记录生成于较早版本，不含完整报告数据。请重新生成报告以查看详情与追问。
              </div>
            ) : (
              <p className="text-sm text-slate-500">点击"生成投研报告"后，报告会在这里生成。</p>
            )}
          </Panel>

          <Panel title="历史报告记录" icon={History}>
            {history.length ? (
              <div className="space-y-2 max-h-[520px] overflow-auto">
                {history.map((record) => (
                  <button
                    className="w-full rounded-md border border-slate-800 bg-slate-950/70 p-3 text-left transition hover:border-cyan-400/50 hover:bg-slate-900/80"
                    key={record.id || `${record.company_name}-${record.created_at}`}
                    onClick={() => loadHistoryDetail(record)}
                    type="button"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold text-slate-100 text-sm">{record.company_name}</span>
                      <span className="text-[11px] text-slate-500 shrink-0">{record.created_at?.slice(0, 10)}</span>
                    </div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-slate-400">
                      {record.recommendation && (
                        <span className={classNames(
                          "rounded px-1.5 py-0.5 text-[11px]",
                          record.recommendation?.toLowerCase().includes("buy") || record.recommendation?.toLowerCase().includes("long")
                            ? "bg-emerald-400/10 text-emerald-200"
                            : record.recommendation?.toLowerCase().includes("sell") || record.recommendation?.toLowerCase().includes("short")
                              ? "bg-red-400/10 text-red-200"
                              : "bg-amber-400/10 text-amber-200",
                        )}>
                          {record.recommendation}
                        </span>
                      )}
                      {record.confidence != null && (
                        <span>置信度 {typeof record.confidence === "number" ? `${Math.round(record.confidence * 100)}%` : record.confidence}</span>
                      )}
                      {record.sources_count != null && (
                        <span>{record.sources_count} 来源</span>
                      )}
                    </div>
                    {record.summary && (
                      <p className="mt-1.5 text-[11px] leading-4 text-slate-500 line-clamp-2">{record.summary}</p>
                    )}
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-500">暂无历史投研记录。</p>
            )}
          </Panel>

        </aside>
      </main>
      {reportResult?.markdown_report && (
        <div className="print-report">
          <div className="mb-6 border-b border-slate-300 pb-4">
            <div className="text-xs uppercase tracking-wide text-slate-500">DeepAlpha Research Report</div>
            <h1 className="mt-2 text-2xl font-bold text-slate-950">{reportResult.company_name || selectedCompanyName} 投研报告</h1>
            <div className="mt-2 text-sm text-slate-600">
              Symbol: {ticker || "N/A"} · Provider: {marketProvider.toUpperCase()} · Sources: {reportResult.final_report?.sources_count ?? 0}
            </div>
          </div>
          <div className="mb-5 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-900">
            本报告为研究辅助输出，不构成投资建议。请结合交易所公告、公司财报与专业判断复核。
          </div>
          <MarkdownReport content={reportResult.markdown_report} printMode />
        </div>
      )}
    </div>
  );
}

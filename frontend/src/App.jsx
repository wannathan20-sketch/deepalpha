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
  Network,
  Plus,
  Play,
  ShieldCheck,
  Star,
  TrendingUp,
  Wrench,
} from "lucide-react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";
const DISCLAIMER_STORAGE_KEY = "deepalpha_disclaimer_accepted";
const ACCESS_CODE_STORAGE_KEY = "deepalpha_access_code";
const USER_ID_STORAGE_KEY = "deepalpha_user_id";

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

function getOrCreateUserId() {
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
    throw new Error(`HTTP ${response.status}`);
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

function safeReportUrl(url) {
  if (!url || url === "#") return "#";

  try {
    const parsed = new URL(url);
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.toString() : "#";
  } catch (err) {
    return "#";
  }
}

function extractExecutiveSummary(content) {
  if (!content) return [];

  const lines = content.split("\n");
  const startIndex = lines.findIndex((line) => /^##\s+Executive Summary/i.test(line.trim()));
  if (startIndex < 0) return [];

  const items = [];
  for (const line of lines.slice(startIndex + 1)) {
    const trimmed = line.trim();
    if (/^##\s+/.test(trimmed)) break;
    if (/^[-*]\s+/.test(trimmed)) {
      items.push(cleanMarkdownText(trimmed));
    }
  }

  return items.slice(0, 8);
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

function ExecutiveSummaryCard({ content }) {
  const items = extractExecutiveSummary(content);
  if (!items.length) return null;

  return (
    <div className="rounded-md border border-cyan-400/25 bg-cyan-400/10 p-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase text-cyan-100">
        <FileText className="h-3.5 w-3.5" />
        Executive Summary
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

function cleanMarkdownText(text) {
  return String(text)
    .replace(/^#{1,6}\s*/, "")
    .replace(/^[-*]\s+/, "")
    .replace(/^\*{1,2}(.+?)\*{1,2}$/, "$1")
    .replace(/^_{1,2}(.+?)_{1,2}$/, "$1")
    .trim();
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

function MarkdownReport({ content, printMode = false }) {
  if (!content) return null;

  return (
    <div className={classNames("report-document space-y-3", printMode ? "print-report-body" : "")}>
      {content.split("\n").map((line, index) => {
        const key = `${index}-${line.slice(0, 16)}`;
        const trimmedLine = line.trim();
        if (!trimmedLine) return <div className="h-1" key={key} />;
        if (/^#\s+/.test(trimmedLine)) {
          return (
            <h1 className="report-title" key={key}>
              {renderInlineMarkdown(cleanMarkdownText(trimmedLine), key)}
            </h1>
          );
        }
        if (/^##+\s*/.test(trimmedLine)) {
          return (
            <div className="report-section-heading" key={key}>
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

function MarketChart({ symbol, displaySymbol, provider, tradingViewSymbol }) {
  const [chartData, setChartData] = useState(null);
  const [chartStatus, setChartStatus] = useState("idle");
  const fallbackSymbol = tradingViewSymbol || displaySymbol || symbol;

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
    requestJson(`/market/chart?symbol=${encodeURIComponent(symbol)}&range=6mo&interval=1d&provider=${encodeURIComponent(provider)}`, {
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
      <div className="flex h-[420px] items-center justify-center rounded-md border border-slate-800 bg-slate-950/70 text-sm text-slate-400">
        请输入或选择股票代码以查看 K 线。
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
          {chartData?.error && (
            <div className="max-w-sm text-right text-xs leading-5 text-amber-100">
              {chartData.error}
            </div>
          )}
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
  const tradingViewUrl = tradingViewSymbol
    ? `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tradingViewSymbol)}`
    : "";

  return (
    <div className="h-[420px] rounded-md border border-slate-800 bg-slate-950 p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-slate-100">{displaySymbol || symbol}</div>
          <div className="mt-1 text-xs text-slate-500">
            {chartData.provider || provider} · Symbol: {chartData.symbol || symbol} · {chartData.exchange || "Market"} · {chartData.currency || "Currency"}
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
            <a
              className="inline-flex rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:border-cyan-400 hover:text-cyan-200"
              href={chartData.yahoo_chart_url}
              rel="noreferrer"
              target="_blank"
            >
              打开来源 K 线
            </a>
            {tradingViewUrl && (
              <a
                className="inline-flex rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:border-cyan-400 hover:text-cyan-200"
                href={tradingViewUrl}
                rel="noreferrer"
                target="_blank"
              >
                打开 TradingView
              </a>
            )}
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
            ["RAG 能力", "使用 Tavily/mock documents 与 Chroma Vector Store 提供行业上下文。"],
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
            <p className="text-sm text-slate-400">DeepAlpha 架构、RAG、Memory、Trace 与调试信息</p>
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
            <div className="grid gap-3 md:grid-cols-2">
              {[
                ["Planner", "制定公司研究计划与分析路径。"],
                ["RAG Retriever", "检索行业资料并写入上下文。"],
                ["Analysts", "基本面、技术面、新闻、情绪与多空观点分析。"],
                ["Committee", "汇总风险审查与最终投研结论。"],
              ].map(([title, text]) => (
                <div className="rounded-md border border-slate-800 bg-slate-950/70 p-3" key={title}>
                  <h2 className="font-semibold text-cyan-200">{title}</h2>
                  <p className="mt-2 text-sm leading-6 text-slate-400">{text}</p>
                </div>
              ))}
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
  const [runtimeConfig, setRuntimeConfig] = useState(null);
  const [architecture, setArchitecture] = useState(null);
  const [watchlist, setWatchlist] = useState([]);
  const [history, setHistory] = useState([]);
  const [selectedHistoryIndex, setSelectedHistoryIndex] = useState(0);
  const [reportResult, setReportResult] = useState(null);
  const [backendOnline, setBackendOnline] = useState(false);
  const [loading, setLoading] = useState("");
  const [reportTaskStatus, setReportTaskStatus] = useState("");
  const [remoteSymbol, setRemoteSymbol] = useState(null);
  const [symbolCandidates, setSymbolCandidates] = useState([]);
  const [symbolLookupStatus, setSymbolLookupStatus] = useState("idle");
  const [marketProvider, setMarketProvider] = useState("auto");
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
      const [healthData, configData, watchlistData, historyData] = await Promise.all([
        requestJson("/health"),
        requestJson("/config"),
        requestJson("/memory/watchlist"),
        requestJson("/memory/history"),
      ]);
      setBackendOnline(healthData.status === "ok");
      setRuntimeConfig(configData);
      setWatchlist(watchlistData);
      setHistory(historyData);
      setSelectedHistoryIndex(0);
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
    const reportName = selectedCompanyName || companyName.trim() || "DeepAlpha";
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
    const query = companyName.trim();
    if (!query) {
      setSymbolCandidates([]);
      setSymbolLookupStatus("idle");
      return undefined;
    }

    const controller = new AbortController();
    const timeoutId = window.setTimeout(async () => {
      setSymbolLookupStatus("searching");
      try {
        const data = await requestJson(`/symbol/lookup?query=${encodeURIComponent(query)}`, {
          signal: controller.signal,
        });
        const matches = data.matches || data.candidates || [];
        if (!data.matched || !matches.length) {
          const fallbackMatches = findLocalFallbackMatches(query);
          setSymbolCandidates(fallbackMatches);
          setSymbolLookupStatus(fallbackMatches.length ? "candidates" : "not_found");
          return;
        }
        setSymbolCandidates(matches);
        setSymbolLookupStatus("candidates");
      } catch (err) {
        if (!controller.signal.aborted) {
          const fallbackMatches = findLocalFallbackMatches(query);
          setSymbolCandidates(fallbackMatches);
          setSymbolLookupStatus(fallbackMatches.length ? "candidates" : "not_found");
        }
      }
    }, 500);

    return () => {
      controller.abort();
      window.clearTimeout(timeoutId);
    };
  }, [companyName]);

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
    setReportTaskStatus("queued");
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
          data_provider: marketProvider,
        }),
      });

      let taskResult = null;
      for (let attempt = 0; attempt < 180; attempt += 1) {
        const status = await requestJson(`/report/tasks/${task.task_id}`);
        setReportTaskStatus(status.status);
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
      setReportTaskStatus("");
    }
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
          data_provider: marketProvider,
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

  const selectedHistory = history[selectedHistoryIndex];
  const matchedSymbol = remoteSymbol;
  const needsConfirmation = Boolean(symbolCandidates.length > 1 && !matchedSymbol);
  const yahooSymbol = toYahooSymbol(ticker, matchedSymbol);
  const selectedCompanyName = matchedSymbol?.name || matchedSymbol?.company || companyName.trim();
  const selectedExchange = matchedSymbol?.exchange || matchedSymbol?.market || "Auto";
  const selectedConfidence = typeof matchedSymbol?.confidence === "number" ? `${Math.round(matchedSymbol.confidence * 100)}%` : "N/A";

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

      <main className="grid gap-4 xl:grid-cols-[280px_minmax(460px,1fr)_380px]">
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
            {reportTaskStatus && (
              <p className="mt-3 text-xs text-slate-500">报告任务状态：{reportTaskStatus}</p>
            )}
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
                <option value="stooq">Stooq</option>
                <option value="tradingview">TradingView</option>
              </select>
            }
          >
            <MarketChart displaySymbol={ticker} provider={marketProvider} symbol={yahooSymbol} tradingViewSymbol={ticker} />
          </Panel>
        </section>

        <aside className="space-y-4">
          <Panel title="投研报告生成" icon={FileText}>
            {reportResult ? (
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-2">
                  <MetricCard label="Decision" value={reportResult.final_report?.recommendation} icon={TrendingUp} />
                  <MetricCard label="Confidence" value={reportResult.final_report?.confidence} icon={ShieldCheck} />
                  <MetricCard label="Sources" value={reportResult.final_report?.sources_count} icon={Database} />
                </div>
                <ExecutiveSummaryCard content={reportResult.markdown_report} />
                <div className="grid gap-3 lg:grid-cols-2">
                  <SourceQualitySummary sourceQuality={reportResult.source_quality} />
                  <ReportEditorSummary editor={reportResult.report_editor} />
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
                <div className="max-h-[520px] overflow-auto rounded-md border border-slate-800 bg-slate-950 p-4 text-sm leading-6 text-slate-300">
                  <MarkdownReport content={reportResult.markdown_report} />
                </div>
              </div>
            ) : (
              <p className="text-sm text-slate-500">点击“生成投研报告”后，报告会在这里生成。</p>
            )}
          </Panel>

          <Panel title="历史报告记录" icon={History}>
            {history.length ? (
              <div className="space-y-3">
                <select
                  className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
                  value={selectedHistoryIndex}
                  onChange={(event) => setSelectedHistoryIndex(Number(event.target.value))}
                >
                  {history.map((record, index) => (
                    <option value={index} key={`${record.company_name}-${record.created_at}`}>
                      {record.company_name} | {record.created_at}
                    </option>
                  ))}
                </select>
                {selectedHistory && (
                  <div className="rounded-md border border-slate-800 bg-slate-950/70 p-3 text-sm">
                    <div className="flex items-center gap-2 font-semibold">
                      <Building2 className="h-4 w-4 text-cyan-300" />
                      {selectedHistory.company_name}
                    </div>
                    <div className="mt-2 flex items-center gap-2 text-xs text-slate-500">
                      <Clock3 className="h-3.5 w-3.5" />
                      {selectedHistory.created_at}
                    </div>
                    <div className="mt-3 grid grid-cols-3 gap-2">
                      <MetricCard label="Rec" value={selectedHistory.recommendation} />
                      <MetricCard label="Conf" value={selectedHistory.confidence} />
                      <MetricCard label="Src" value={selectedHistory.sources_count} />
                    </div>
                    <p className="mt-3 max-h-40 overflow-auto text-slate-400">{selectedHistory.summary}</p>
                  </div>
                )}
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
            <h1 className="mt-2 text-2xl font-bold text-slate-950">{selectedCompanyName} 投研报告</h1>
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

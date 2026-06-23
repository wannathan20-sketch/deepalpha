const STOCK_INDEX_URL = "/stocks.index.json";

function normalizeText(value) {
  return String(value || "").trim().toLowerCase().replace(/\s+/g, "");
}

function normalizeSymbol(value) {
  return String(value || "").trim().toUpperCase().replace(":", ".");
}

function splitCsvLine(line) {
  const cells = [];
  let current = "";
  let quoted = false;
  for (const char of String(line || "")) {
    if (char === "\"") {
      quoted = !quoted;
    } else if (char === "," && !quoted) {
      cells.push(current.trim());
      current = "";
    } else {
      current += char;
    }
  }
  cells.push(current.trim());
  return cells;
}

export function parseWatchlistImportText(text) {
  const lines = String(text || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (!lines.length) return [];

  const firstRow = splitCsvLine(lines[0]).map((cell) => normalizeText(cell));
  const fieldIndex = firstRow.findIndex((cell) => ["symbol", "name", "company"].includes(cell));
  const values = [];

  if (fieldIndex >= 0) {
    lines.slice(1).forEach((line) => {
      const cell = splitCsvLine(line)[fieldIndex]?.trim();
      if (cell) values.push(cell);
    });
  } else {
    lines.forEach((line) => {
      splitCsvLine(line.replace(/，/g, ",")).forEach((cell) => {
        const clean = cell.trim();
        if (clean) values.push(clean);
      });
    });
  }

  const seen = new Set();
  return values.filter((value) => {
    const key = normalizeText(value);
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function symbolKeys(item) {
  const values = [
    item.symbol,
    item.displaySymbol,
    item.ticker,
    item.rawSymbol,
    item.yahooSymbol,
  ];
  const keys = new Set();
  values.forEach((value) => {
    const normalized = normalizeSymbol(value);
    if (!normalized) return;
    keys.add(normalized);
    keys.add(normalized.replace(/^HK0*/, ""));
    keys.add(normalized.replace(/^0+/, ""));
    if (normalized.includes(".")) {
      const [base] = normalized.split(".");
      keys.add(base);
      keys.add(base.replace(/^0+/, ""));
    }
    if (normalized.includes(":")) {
      const [, base] = normalized.split(":");
      keys.add(base);
      keys.add(base.replace(/^0+/, ""));
    }
  });
  return keys;
}

function textFields(item) {
  return [
    item.name,
    item.nameZh,
    item.nameEn,
    item.company,
    item.pinyinFull,
    item.pinyinAbbr,
    ...(item.aliases || []),
  ].filter(Boolean);
}

function scoreItem(query, item) {
  const normalizedQuery = normalizeText(query);
  const symbolQuery = normalizeSymbol(query);
  if (!normalizedQuery) return null;

  const codeKeys = symbolKeys(item);
  const normalizedNames = [item.name, item.nameZh, item.nameEn, item.company].filter(Boolean).map((field) => normalizeText(field));
  const normalizedPinyin = [item.pinyinFull, item.pinyinAbbr].filter(Boolean).map((field) => normalizeText(field));
  const normalizedAliases = (item.aliases || []).map((field) => normalizeText(field));
  const normalizedFields = [...normalizedNames, ...normalizedPinyin, ...normalizedAliases];

  if (codeKeys.has(symbolQuery) || codeKeys.has(symbolQuery.replace(/^0+/, ""))) {
    return { score: 100, source: "local_index_code", confidence: 0.99 };
  }
  if (normalizedNames.some((field) => field === normalizedQuery)) {
    return { score: 98, source: "local_index_name", confidence: 0.98 };
  }
  if (normalizedAliases.some((field) => field === normalizedQuery)) {
    return { score: 97, source: "local_index_alias", confidence: 0.95 };
  }
  if (normalizedPinyin.some((field) => field === normalizedQuery)) {
    return { score: 96, source: "local_index_pinyin", confidence: 0.96 };
  }

  const codePrefix = [...codeKeys].some((key) => key.startsWith(symbolQuery));
  if (symbolQuery.length >= 2 && codePrefix) {
    return { score: 82, source: "local_index_code_prefix", confidence: 0.86 };
  }

  const textPrefix = normalizedFields.some((field) => field.startsWith(normalizedQuery));
  if (normalizedQuery.length >= 2 && textPrefix) {
    return { score: 78, source: "local_index_prefix", confidence: 0.84 };
  }

  const textContains = normalizedFields.some(
    (field) => normalizedQuery.length >= 2 && (field.includes(normalizedQuery) || normalizedQuery.includes(field)),
  );
  if (textContains) {
    return { score: 62, source: "local_index_contains", confidence: 0.78 };
  }

  return null;
}

export function toSymbolCandidate(item, match) {
  const symbol = item.symbol || item.yahooSymbol || item.displaySymbol || "";
  const displayName = item.nameZh || item.name || item.company || symbol;
  return {
    symbol,
    name: displayName,
    company: item.name || item.company || displayName,
    ticker: item.ticker || symbol,
    raw_symbol: item.rawSymbol || symbol,
    exchange: item.exchange || "",
    market: item.market || item.exchange || "",
    country: item.country || "",
    currency: item.currency || "",
    confidence: match.confidence,
    source: match.source,
    score: match.score + (item.popularity || 0),
    quote_type: item.assetType || "EQUITY",
  };
}

export function searchStockIndex(query, index, limit = 8) {
  if (!query || !Array.isArray(index) || !index.length) return [];

  return index
    .map((item) => {
      const match = scoreItem(query, item);
      return match ? toSymbolCandidate(item, match) : null;
    })
    .filter(Boolean)
    .sort((left, right) => {
      if (right.confidence !== left.confidence) return right.confidence - left.confidence;
      return (right.score || 0) - (left.score || 0);
    })
    .slice(0, limit);
}

export function mergeSymbolCandidates(localCandidates, remoteCandidates, limit = 8) {
  const bySymbol = new Map();

  [...(localCandidates || []), ...(remoteCandidates || [])].forEach((candidate) => {
    if (!candidate?.symbol) return;
    const key = normalizeSymbol(candidate.symbol);
    const existing = bySymbol.get(key);
    if (!existing || (candidate.confidence || 0) >= (existing.confidence || 0)) {
      bySymbol.set(key, candidate);
    }
  });

  return [...bySymbol.values()]
    .sort((left, right) => {
      if ((right.confidence || 0) !== (left.confidence || 0)) {
        return (right.confidence || 0) - (left.confidence || 0);
      }
      return (right.score || 0) - (left.score || 0);
    })
    .slice(0, limit);
}

export async function loadStockIndex() {
  const response = await fetch(`${STOCK_INDEX_URL}?v=2026-06-23`);
  if (!response.ok) {
    throw new Error(`Failed to load stock index: HTTP ${response.status}`);
  }
  const data = await response.json();
  return Array.isArray(data) ? data : [];
}

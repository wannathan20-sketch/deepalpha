import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { mergeSymbolCandidates, searchStockIndex } from "./stockSearch.js";

const publicIndex = JSON.parse(readFileSync(new URL("../public/stocks.index.json", import.meta.url), "utf8"));

const index = [
  {
    symbol: "600519.SS",
    displaySymbol: "600519",
    ticker: "SSE:600519",
    name: "Kweichow Moutai",
    nameZh: "贵州茅台",
    exchange: "SSE",
    market: "CN",
    aliases: ["茅台", "moutai"],
    pinyinFull: "guizhoumaotai",
    pinyinAbbr: "gzmt",
    popularity: 95,
  },
  {
    symbol: "9988.HK",
    displaySymbol: "9988",
    ticker: "HKEX:9988",
    name: "Alibaba Group",
    nameZh: "阿里巴巴",
    exchange: "HKEX",
    market: "HK",
    aliases: ["阿里", "alibaba hk"],
    pinyinFull: "alibaba",
    pinyinAbbr: "albb",
    popularity: 94,
  },
  {
    symbol: "BABA",
    displaySymbol: "BABA",
    ticker: "NYSE:BABA",
    name: "Alibaba Group",
    nameZh: "阿里巴巴",
    exchange: "NYSE",
    market: "US",
    aliases: ["阿里", "alibaba us", "baba"],
    pinyinFull: "alibaba",
    pinyinAbbr: "albb",
    popularity: 92,
  },
  {
    symbol: "0700.HK",
    displaySymbol: "0700",
    ticker: "HKEX:0700",
    name: "Tencent Holdings",
    nameZh: "腾讯控股",
    exchange: "HKEX",
    market: "HK",
    aliases: ["腾讯", "700", "00700"],
    pinyinFull: "tengxunkonggu",
    pinyinAbbr: "txkg",
    popularity: 93,
  },
];

test("searches by pinyin abbreviation", () => {
  const results = searchStockIndex("gzmt", index);

  assert.equal(results[0].symbol, "600519.SS");
  assert.equal(results[0].name, "贵州茅台");
  assert.equal(results[0].source, "local_index_pinyin");
});

test("returns ambiguous aliases as multiple candidates", () => {
  const symbols = searchStockIndex("阿里", index).map((item) => item.symbol);

  assert.deepEqual(symbols, ["9988.HK", "BABA"]);
});

test("normalizes Hong Kong code lookup with leading zero", () => {
  const results = searchStockIndex("00700", index);

  assert.equal(results[0].symbol, "0700.HK");
  assert.equal(results[0].ticker, "HKEX:0700");
});

test("merges remote candidates without duplicating local index matches", () => {
  const local = searchStockIndex("阿里", index);
  const merged = mergeSymbolCandidates(local, [
    {
      symbol: "9988.HK",
      name: "Alibaba Group",
      ticker: "HKEX:9988",
      exchange: "HKEX",
      market: "HK",
      confidence: 0.97,
      source: "alias",
    },
  ]);

  assert.equal(merged.filter((item) => item.symbol === "9988.HK").length, 1);
  assert.equal(merged[0].symbol, "9988.HK");
  assert.equal(merged[0].source, "alias");
});

test("public index includes high-attention US AI names", () => {
  const results = searchStockIndex("pltr", publicIndex);

  assert.equal(results[0].symbol, "PLTR");
  assert.equal(results[0].source, "local_index_code");
});

test("public index includes high-attention A-share semiconductor names", () => {
  const results = searchStockIndex("中芯国际", publicIndex).map((item) => item.symbol);

  assert.ok(results.includes("688981.SS"));
  assert.ok(results.includes("0981.HK"));
});

test("public index includes dual-listed Chinese internet names", () => {
  const results = searchStockIndex("京东", publicIndex).map((item) => item.symbol);

  assert.ok(results.includes("9618.HK"));
  assert.ok(results.includes("JD"));
});

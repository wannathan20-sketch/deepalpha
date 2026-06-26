import assert from "node:assert/strict";
import { test } from "node:test";

import { formatApiErrorMessage, resolveApiBase } from "./apiClient.js";


test("explicit VITE_API_BASE wins over hostname defaults", () => {
  assert.equal(
    resolveApiBase({
      envApiBase: "https://custom-api.example.com",
      hostname: "deepalpha.best",
    }),
    "https://custom-api.example.com",
  );
});


test("deepalpha.best defaults to api.deepalpha.best", () => {
  assert.equal(
    resolveApiBase({ envApiBase: "", hostname: "deepalpha.best" }),
    "https://api.deepalpha.best",
  );
});


test("www.deepalpha.best defaults to api.deepalpha.best", () => {
  assert.equal(
    resolveApiBase({ envApiBase: "", hostname: "www.deepalpha.best" }),
    "https://api.deepalpha.best",
  );
});


test("local development defaults to the local FastAPI backend", () => {
  assert.equal(
    resolveApiBase({ envApiBase: "", hostname: "localhost" }),
    "http://127.0.0.1:8000",
  );
});


test("formats backend detail in HTTP errors", () => {
  assert.equal(
    formatApiErrorMessage(503, { detail: "deepseek LLM request failed" }),
    "HTTP 503: deepseek LLM request failed",
  );
});

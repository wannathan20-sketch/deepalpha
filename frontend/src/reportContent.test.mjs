import assert from "node:assert/strict";
import { test } from "node:test";

import { extractExecutiveSummary, normalizeReportMarkdown } from "./reportContent.js";

test("normalizes unexpected report markdown payloads without throwing", () => {
  assert.equal(normalizeReportMarkdown(null), "");
  assert.equal(normalizeReportMarkdown({ markdown_report: "## Executive Summary\n- Kept" }), "## Executive Summary\n- Kept");
  assert.equal(normalizeReportMarkdown(["# A", "body"]), "# A\nbody");
  assert.equal(normalizeReportMarkdown({ unexpected: true }), "");
});

test("extracts executive summary only from normalized report text", () => {
  const summary = extractExecutiveSummary({
    markdown_report: "## Executive Summary\n- **Durable moat**\n- Cash flow\n\n## Risks\n- Demand",
  });

  assert.deepEqual(summary, ["Durable moat", "Cash flow"]);
  assert.deepEqual(extractExecutiveSummary({ unexpected: true }), []);
});

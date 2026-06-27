export function normalizeReportMarkdown(value) {
  if (typeof value === "string") return value;
  if (value == null) return "";
  if (Array.isArray(value)) return value.map((item) => normalizeReportMarkdown(item)).filter(Boolean).join("\n");
  if (typeof value === "object") {
    return normalizeReportMarkdown(value.markdown_report ?? value.content ?? value.text ?? "");
  }
  return String(value);
}

export function cleanMarkdownText(text) {
  return String(text)
    .replace(/^#{1,6}\s*/, "")
    .replace(/^[-*]\s+/, "")
    .replace(/^\*{1,2}(.+?)\*{1,2}$/, "$1")
    .replace(/^_{1,2}(.+?)_{1,2}$/, "$1")
    .trim();
}

export function extractExecutiveSummary(content) {
  const reportText = normalizeReportMarkdown(content);
  if (!reportText) return [];

  const lines = reportText.split("\n");
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

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

const HEADING_LABEL_MAP = {
  "Executive Summary": "摘要",
  "Sources": "信息来源",
};

export function extractReportHeadings(content) {
  const reportText = normalizeReportMarkdown(content);
  if (!reportText) return [];

  const lines = reportText.split("\n");
  const headings = [];
  let sectionIndex = 0;

  for (const line of lines) {
    const trimmed = line.trim();
    const h1Match = trimmed.match(/^#\s+(.+)/);
    const h2Match = trimmed.match(/^##+\s*(.+)/);

    if (h1Match || h2Match) {
      const rawText = (h1Match || h2Match)[1];
      const displayText = cleanMarkdownText(rawText);
      sectionIndex += 1;
      const slug = String(displayText)
        .toLowerCase()
        .replace(/[^\p{L}\p{N}_]+/gu, "-")
        .replace(/^-+|-+$/g, "") || "section";

      headings.push({
        level: h1Match ? 1 : 2,
        text: HEADING_LABEL_MAP[displayText] || displayText,
        sectionId: `report-section-${sectionIndex}-${slug}`,
      });
    }
  }

  return headings;
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

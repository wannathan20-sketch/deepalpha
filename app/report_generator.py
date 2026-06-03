from app.agents.llm_helpers import clean_markdown_artifacts


PLACEHOLDER_ANALYSIS = "该模块当前为占位分析，后续可接入真实数据源。"
BLOCKED_TERMS = ("mock", "placeholder", "assumed", "modeled")


def _sanitize_text(value: object) -> str:
    text = clean_markdown_artifacts(str(value))
    lowered = text.lower()
    return PLACEHOLDER_ANALYSIS if any(term in lowered for term in BLOCKED_TERMS) else text


def _sanitize_url(value: object) -> str:
    url = str(value)
    lowered = url.lower()
    return "#" if any(term in lowered for term in BLOCKED_TERMS) else url


def _render_key_points(key_points: list[str]) -> list[str]:
    return [f"- {_sanitize_text(point)}" for point in key_points]


def _first_item(items: list[str], fallback: str) -> str:
    for item in items:
        cleaned = _sanitize_text(item)
        if cleaned and cleaned != PLACEHOLDER_ANALYSIS:
            return cleaned
    return fallback


def _render_executive_summary(
    company_name: str,
    final_report: dict,
    team_results: dict,
    market_profile: dict,
    financial_profile: dict,
) -> list[str]:
    bull_points = team_results.get("bull", {}).get("key_points", [])
    bear_points = team_results.get("bear", {}).get("key_points", [])
    risk_points = final_report.get("risks", []) or team_results.get("risk", {}).get("risks", [])
    source_quality = team_results.get("source_quality", {})
    grade_counts = source_quality.get("grade_counts", {})

    core_conflict = (
        f"{_first_item(bull_points, '成长与基本面改善仍需验证')}；"
        f"{_first_item(bear_points, '估值、竞争和数据完整性仍是主要约束')}"
    )
    market_line = "行情数据暂不可用，价格趋势需后续补充。"
    if market_profile.get("enabled"):
        market_line = (
            f"最新收盘价 {market_profile.get('latest_close')}，"
            f"6 个月区间回报 {market_profile.get('period_return_percent')}%，"
            f"趋势判断为 {market_profile.get('trend')}。"
        )
    financial_line = "财报数据暂不可用，财务事实需后续补充。"
    if financial_profile.get("enabled"):
        financial_line = (
            f"{financial_profile.get('filing_type', 'SEC filing')} / {financial_profile.get('fiscal_period', '最新披露期')}，"
            f"收入 {financial_profile.get('revenue', '待补充')}，"
            f"净利润 {financial_profile.get('net_income', '待补充')}，"
            f"经营现金流 {financial_profile.get('operating_cash_flow', '待补充')}。"
        )

    return [
        "## Executive Summary",
        "",
        f"- 公司：{_sanitize_text(company_name)}",
        f"- 评级：{_sanitize_text(final_report.get('recommendation', 'watchlist'))}",
        f"- 置信度：{_sanitize_text(final_report.get('confidence', '待补充'))}",
        f"- 核心矛盾：{core_conflict}",
        f"- 行情摘要：{_sanitize_text(market_line)}",
        f"- 财报锚点：{_sanitize_text(financial_line)}",
        f"- 关键风险：{_first_item(risk_points, '需补充最新公告、财报和估值数据后再复核。')}",
        (
            "- 来源质量："
            f"A/B/C/D = {grade_counts.get('A', 0)}/{grade_counts.get('B', 0)}/"
            f"{grade_counts.get('C', 0)}/{grade_counts.get('D', 0)}"
        ),
        "- 结论边界：本报告用于研究辅助，不构成任何投资建议或交易指令。",
        "",
    ]


def _render_source_ratings(result: dict) -> list[str]:
    ratings = result.get("source_ratings", [])
    if not ratings:
        return []

    lines = ["", "来源评级："]
    for rating in ratings[:8]:
        title = _sanitize_text(rating.get("title", "Untitled"))
        grade = _sanitize_text(rating.get("grade", "D"))
        reason = _sanitize_text(rating.get("reason", "需复核。"))
        url = _sanitize_url(rating.get("url", "#"))
        if url and url != "#":
            lines.append(f"- {grade}｜[{title}]({url})：{reason}")
        else:
            lines.append(f"- {grade}｜{title}：{reason}")
    return lines


def _render_agent_section(title: str, result: dict) -> list[str]:
    lines = [title, ""]
    lines.append("分析摘要：")
    lines.append(_sanitize_text(result.get("summary", "暂无 summary。")))
    lines.append("")

    claims = result.get("claims", [])
    if claims:
        lines.extend(["核心判断："])
        for claim in claims:
            claim_text = _sanitize_text(claim.get("claim", ""))
            evidence = _sanitize_text(claim.get("evidence", ""))
            source_url = _sanitize_url(claim.get("source_url", ""))
            if source_url and source_url != "#":
                lines.append(f"- {claim_text}（证据：{evidence}，[来源]({source_url})）")
            else:
                lines.append(f"- {claim_text}（证据：{evidence}）")
    else:
        lines.extend(_render_key_points(result.get("key_points", [])))

    risks = result.get("risks", [])
    if risks:
        lines.extend(["", "主要风险："])
        lines.extend(_render_key_points(risks))

    watch_items = result.get("watch_items", [])
    if watch_items:
        lines.extend(["", "后续跟踪指标："])
        lines.extend(_render_key_points(watch_items))

    data_quality = result.get("data_quality", {})
    warnings = data_quality.get("warnings", [])
    if data_quality:
        lines.extend(
            [
                "",
                f"数据质量：来源 {data_quality.get('source_count', 0)} 条，可访问链接 {data_quality.get('linked_source_count', 0)} 条，时效状态 {data_quality.get('freshness', 'unknown')}。",
            ]
        )
    if warnings:
        lines.extend(_render_key_points(warnings))

    lines.extend(_render_source_ratings(result))

    sources = result.get("sources", [])
    if sources:
        lines.extend(["", "Sources:"])
        for source in sources:
            title_text = _sanitize_text(source.get("title", "Untitled"))
            url = _sanitize_url(source.get("url", "#"))
            lines.append(f"- [{title_text}]({url})")

    return lines


def _collect_sources(team_results: dict) -> list[dict]:
    sources = []
    seen_urls = set()

    for result in team_results.values():
        for source in result.get("sources", []):
            url = _sanitize_url(source.get("url", "#"))
            key = url or source.get("title", "")
            if key in seen_urls:
                continue
            seen_urls.add(key)
            sources.append(source)

    return sources


def generate_markdown_report(
    company_name: str,
    research_plan: dict,
    team_results: dict,
    final_report: dict,
    memory: dict | None = None,
    market_profile: dict | None = None,
    financial_profile: dict | None = None,
) -> str:
    lines = [
        f"# 深研 Alpha 投研报告：{company_name}",
        "",
    ]
    lines.extend(
        _render_executive_summary(
            company_name,
            final_report,
            team_results,
            market_profile or {},
            financial_profile or {},
        )
    )
    lines.extend(["## 1. 研究计划", ""])

    for task in research_plan.get("tasks", []):
        lines.append(
            f"- {task.get('title', '未命名任务')}：{task.get('assigned_to', '未分配')}"
        )

    lines.extend(["", "## 历史投研记忆", ""])
    recent_history = (memory or {}).get("recent_history", [])
    if recent_history:
        for record in recent_history[:3]:
            lines.extend(
                [
                    f"- 时间：{_sanitize_text(record.get('created_at', ''))}",
                    f"  - Recommendation：{_sanitize_text(record.get('recommendation', ''))}",
                    f"  - Confidence：{_sanitize_text(record.get('confidence', ''))}",
                    f"  - Summary：{_sanitize_text(record.get('summary', ''))}",
                ]
            )
    else:
        lines.append("暂无历史投研记录。")

    lines.extend(["", "## 行情数据摘要", ""])
    market_profile = market_profile or {}
    if market_profile.get("enabled"):
        lines.extend(
            [
                f"- Symbol：{_sanitize_text(market_profile.get('symbol') or market_profile.get('yahoo_symbol', ''))}",
                f"- Provider：{_sanitize_text(market_profile.get('provider', ''))}",
                f"- Latest Close：{_sanitize_text(market_profile.get('latest_close', ''))}",
                f"- 6M Return：{_sanitize_text(market_profile.get('period_return_percent', ''))}%",
                f"- 6M High / Low：{_sanitize_text(market_profile.get('high_6m', ''))} / {_sanitize_text(market_profile.get('low_6m', ''))}",
                f"- MA20 / MA60：{_sanitize_text(market_profile.get('ma20', ''))} / {_sanitize_text(market_profile.get('ma60', ''))}",
                f"- Trend：{_sanitize_text(market_profile.get('trend', ''))}",
                f"- Annualized Volatility：{_sanitize_text(market_profile.get('annualized_volatility_percent', ''))}%",
            ]
        )
    else:
        lines.append(f"暂无可用行情摘要。{_sanitize_text(market_profile.get('reason', ''))}")

    lines.extend(["", "## 财报数据摘要", ""])
    financial_profile = financial_profile or {}
    if financial_profile.get("enabled"):
        lines.extend(
            [
                f"- Symbol：{_sanitize_text(financial_profile.get('symbol', ''))}",
                f"- Source：{_sanitize_text(financial_profile.get('source', ''))}",
                f"- Filing：{_sanitize_text(financial_profile.get('filing_type', ''))} / {_sanitize_text(financial_profile.get('fiscal_period', ''))}",
                f"- Report Date：{_sanitize_text(financial_profile.get('report_date', ''))}",
                f"- Revenue：{_sanitize_text(financial_profile.get('revenue', ''))}",
                f"- Gross Margin：{_sanitize_text(financial_profile.get('gross_margin_percent', ''))}%",
                f"- Operating Margin：{_sanitize_text(financial_profile.get('operating_margin_percent', ''))}%",
                f"- Net Income：{_sanitize_text(financial_profile.get('net_income', ''))}",
                f"- EPS Diluted：{_sanitize_text(financial_profile.get('eps_diluted', ''))}",
                f"- Operating Cash Flow：{_sanitize_text(financial_profile.get('operating_cash_flow', ''))}",
                f"- Free Cash Flow：{_sanitize_text(financial_profile.get('free_cash_flow', ''))}",
                f"- Cash / Debt：{_sanitize_text(financial_profile.get('cash', ''))} / {_sanitize_text(financial_profile.get('debt', ''))}",
                f"- Total Assets / Liabilities：{_sanitize_text(financial_profile.get('total_assets', ''))} / {_sanitize_text(financial_profile.get('total_liabilities', ''))}",
            ]
        )
        filing_url = _sanitize_url(financial_profile.get("filing_url", ""))
        if filing_url and filing_url != "#":
            lines.append(f"- Filing URL：[SEC]({filing_url})")
        summary_items = financial_profile.get("summary", [])
        if summary_items:
            lines.extend(["", "结构化摘要："])
            lines.extend(_render_key_points(summary_items))
    else:
        lines.append(f"暂无可用 SEC 财报摘要。{_sanitize_text(financial_profile.get('reason', ''))}")

    sections = [
        ("## 2. 行业研究分析", "industry"),
        ("## 3. 基本面分析", "fundamental"),
        ("## 4. 财务报表分析", "financial"),
        ("## 5. 估值与情景分析", "valuation"),
        ("## 6. 技术面分析", "technical"),
        ("## 7. 新闻事件分析", "news"),
        ("## 8. 市场情绪分析", "sentiment"),
        ("## 9. 看多观点", "bull"),
        ("## 10. 看空观点", "bear"),
        ("## 11. 交易假设", "trader"),
        ("## 12. 风控审查", "risk"),
        ("## 13. 来源质量审查", "source_quality"),
    ]

    for title, key in sections:
        lines.extend([""])
        lines.extend(_render_agent_section(title, team_results.get(key, {})))

    lines.extend(
        [
            "",
            "## 14. 投研委员会综合判断",
            "",
            _sanitize_text(final_report.get("summary", "暂无 summary。")),
            "",
        ]
    )
    lines.extend(_render_key_points(final_report.get("key_points", [])))
    lines.extend(
        [
            "",
            f"- Recommendation: {final_report.get('recommendation', 'N/A')}",
            f"- Confidence: {final_report.get('confidence', 'N/A')}",
            f"- Sources Count: {final_report.get('sources_count', 0)}",
            "",
            "## 15. 免责声明",
            "",
            "本报告仅用于信息整理和学习研究，不构成任何投资建议。",
            "",
            "## 16. 信息来源",
            "",
        ]
    )

    all_sources = _collect_sources(team_results)
    if all_sources:
        for source in all_sources:
            title_text = _sanitize_text(source.get("title", "Untitled"))
            url = _sanitize_url(source.get("url", "#"))
            lines.append(f"- [{title_text}]({url})")
    else:
        lines.append("- 暂无信息来源。")

    return "\n".join(lines)

def create_plan(company_name: str) -> dict:
    return {
        "agent": "Planner Agent",
        "objective": "Generate a structured research plan",
        "tasks": [
            {
                "id": "fundamental",
                "title": "基本面分析",
                "assigned_to": "Fundamental Analyst",
            },
            {
                "id": "financial",
                "title": "财务报表分析",
                "assigned_to": "Financial Analyst",
            },
            {
                "id": "valuation",
                "title": "估值与情景分析",
                "assigned_to": "Valuation Analyst",
            },
            {
                "id": "technical",
                "title": "技术面分析",
                "assigned_to": "Technical Analyst",
            },
            {
                "id": "news",
                "title": "新闻事件分析",
                "assigned_to": "News Analyst",
            },
            {
                "id": "sentiment",
                "title": "市场情绪分析",
                "assigned_to": "Sentiment Analyst",
            },
            {
                "id": "bull",
                "title": "看多观点",
                "assigned_to": "Bull Analyst",
            },
            {
                "id": "bear",
                "title": "看空观点",
                "assigned_to": "Bear Analyst",
            },
            {
                "id": "trader",
                "title": "交易假设",
                "assigned_to": "Trader",
            },
            {
                "id": "risk",
                "title": "风控审查",
                "assigned_to": "Risk Manager",
            },
            {
                "id": "source_quality",
                "title": "来源质量审查",
                "assigned_to": "Source Quality Agent",
            },
            {
                "id": "committee",
                "title": "综合决策汇总",
                "assigned_to": "Committee Agent",
            },
        ],
    }

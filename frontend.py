from datetime import datetime

import requests
import streamlit as st


BASE_URL = "http://127.0.0.1:8000"
REPORT_URL = f"{BASE_URL}/report"
WATCHLIST_URL = f"{BASE_URL}/memory/watchlist"
HISTORY_URL = f"{BASE_URL}/memory/history"
ARCHITECTURE_URL = f"{BASE_URL}/debug/architecture"
BACKEND_ERROR = "请先启动 FastAPI 后端：uvicorn app.main:app --reload"


def api_get(url: str):
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        st.error(BACKEND_ERROR)
        return None


def api_post(url: str, payload: dict, timeout: int = 20):
    try:
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        st.error(BACKEND_ERROR)
        return None


def refresh_memory() -> None:
    st.session_state.watchlist = api_get(WATCHLIST_URL) or []
    st.session_state.history = api_get(HISTORY_URL) or []


def refresh_architecture() -> None:
    st.session_state.architecture = api_get(ARCHITECTURE_URL) or {}


def build_thread_id(company_name: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    safe_name = company_name.strip().replace(" ", "-")
    return f"streamlit-{safe_name}-{timestamp}"


st.set_page_config(page_title="深研 Alpha / DeepAlpha", layout="wide")

if "watchlist" not in st.session_state or "history" not in st.session_state:
    refresh_memory()

if "architecture" not in st.session_state:
    refresh_architecture()

st.title("深研 Alpha / DeepAlpha")
st.subheader("多智能体虚拟投研团队")

with st.sidebar:
    st.markdown("### Watchlist 关注列表")
    watchlist_company = st.text_input("添加公司到关注列表", value="")

    if st.button("添加关注"):
        if watchlist_company.strip():
            created = api_post(WATCHLIST_URL, {"company_name": watchlist_company.strip()})
            if created:
                st.success(f"已关注 {created.get('company_name', watchlist_company.strip())}")
                refresh_memory()
        else:
            st.warning("请输入公司名称。")

    if st.session_state.watchlist:
        for item in st.session_state.watchlist:
            last_analyzed_at = item.get("last_analyzed_at") or "尚未分析"
            st.markdown(f"- **{item.get('company_name', '')}**")
            st.caption(f"最近分析：{last_analyzed_at}")
    else:
        st.caption("暂无关注公司。")

    st.markdown("---")
    st.markdown("### 历史投研记录")
    history = st.session_state.history

    if history:
        history_labels = [
            f"{record.get('company_name', '')} | {record.get('created_at', '')}"
            for record in history
        ]
        selected_label = st.selectbox("选择历史记录", history_labels)
        selected_record = history[history_labels.index(selected_label)]

        st.markdown(f"**Company:** {selected_record.get('company_name', '')}")
        st.caption(f"Created At: {selected_record.get('created_at', '')}")
        st.write(f"Recommendation: {selected_record.get('recommendation', '')}")
        st.write(f"Confidence: {selected_record.get('confidence', '')}")
        st.write(f"Sources Count: {selected_record.get('sources_count', '')}")
        st.write(selected_record.get("summary", ""))
    else:
        st.caption("暂无历史投研记录。")

    st.markdown("---")
    with st.expander("Architecture / Debug", expanded=False):
        architecture = st.session_state.architecture

        if architecture:
            st.markdown(f"**Project:** {architecture.get('project', '')}")

            st.markdown("**Capabilities**")
            for name, enabled in architecture.get("capabilities", {}).items():
                status = "✅" if enabled else "❌"
                st.write(f"{status} {name}")

            st.markdown("**Agents**")
            for agent in architecture.get("agents", []):
                st.write(f"- {agent}")

            st.markdown("**Tools**")
            for tool in architecture.get("tools", []):
                st.write(f"- {tool}")

            st.markdown("**Architecture Flow**")
            st.code(architecture.get("architecture", ""), language="text")
        else:
            st.caption("暂无架构诊断信息。")


left_col, main_col = st.columns([1, 2])

with left_col:
    st.markdown("### 分析设置")
    company_name = st.text_input("公司名称", value="Tesla")
    thread_id = st.text_input("Thread ID（可选）", value="")
    start_analysis = st.button("开始分析", type="primary")

with main_col:
    if start_analysis:
        if not company_name.strip():
            st.warning("请输入公司名称。")
        else:
            final_thread_id = thread_id.strip() or build_thread_id(company_name)
            payload = {
                "company_name": company_name.strip(),
                "thread_id": final_thread_id,
            }

            with st.spinner("虚拟投研团队正在分析，请稍候..."):
                result = api_post(REPORT_URL, payload, timeout=120)

            if result:
                refresh_memory()
                final_report = result.get("final_report", {})
                citation_check = result.get("citation_check", {})
                trace_summary = result.get("trace_summary", {})

                st.success("分析完成")
                st.caption(f"Thread ID: {result.get('thread_id', final_thread_id)}")

                metric_col1, metric_col2, metric_col3 = st.columns(3)
                metric_col1.metric("Recommendation", final_report.get("recommendation", "N/A"))
                metric_col2.metric("Confidence", final_report.get("confidence", "N/A"))
                metric_col3.metric("Sources Count", final_report.get("sources_count", 0))

                st.markdown("### Markdown 投研报告")
                st.markdown(result.get("markdown_report", "暂无报告。"))

                with st.expander("Citation Check"):
                    st.json(citation_check)

                with st.expander("Trace Summary"):
                    st.json(trace_summary)
    else:
        st.info("输入公司名称后点击“开始分析”。")

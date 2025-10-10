import streamlit as st
from utils.db import sqlQuery

# ------------------------------------------------------------
# 📊 Load Summary Data
# ------------------------------------------------------------
@st.cache_data(ttl=300)
def load_summary_growth():
    query = """
        WITH last_date_cte AS (
            SELECT MAX(Created) AS last_date
            FROM workspace_west_2.default.st_query_parsed
        ),
        summary AS (
            SELECT
                COUNT(*) AS total_tickets_all_time,
                SUM(CASE WHEN lower(Status) IN ('resolved','closed') THEN 1 ELSE 0 END) AS resolved_all_time,
                COUNT(DISTINCT Agent_ID) AS total_agents_all_time,
                SUM(CASE WHEN Created >= DATEADD(month, -1, ld.last_date) THEN 1 ELSE 0 END) AS tickets_last_month,
                SUM(CASE WHEN lower(Status) IN ('resolved','closed') 
                        AND Created >= DATEADD(month, -1, ld.last_date) THEN 1 ELSE 0 END) AS resolved_last_month,
                COUNT(DISTINCT CASE WHEN Created >= DATEADD(month, -1, ld.last_date) THEN Agent_ID END) AS agents_last_month
            FROM workspace_west_2.default.st_query_parsed t
            CROSS JOIN last_date_cte ld
        )
        SELECT * FROM summary
    """
    return sqlQuery(query)


st.set_page_config(
    page_title="AI Support Assistant",
    layout="wide"
)

st.markdown("""
    <style>
                
    /* Sidebar background */
    [data-testid="stSidebar"] {
        background-color: #eeeeee;
        padding-top: 1rem;
    }

    /* Sidebar section title */
    .sidebar .sidebar-content h2 {
        color: #165CCC;
    }

    /* Sidebar buttons */
    .sidebar .sidebar-content div[role="radiogroup"] label {
        display: flex;
        align-items: center;
        padding: 0.6rem 0.8rem;
        margin-bottom: 0.3rem;
        border-radius: 10px;
        transition: all 0.2s;
        font-weight: 500;
    }

    /* Hover effect */
    .sidebar .sidebar-content div[role="radiogroup"] label:hover {
        background-color: #E8F0FE;
        cursor: pointer;
    }

    /* Selected option */
    .sidebar .sidebar-content div[role="radiogroup"] input:checked + label {
        background-color: #165CCC;
        color: white;
    }

    /* Icon spacing */
    .sidebar-icon {
        margin-right: 0.5rem;
    }
    /* App background */
    .stApp {
        background-color: #FAFAFB;
    }

    /* Header styling */
    .header {
        background: linear-gradient(#e66465, #9198e5);
        padding: 1.8rem;
        border-radius: 14px;
        color: white;
        text-align: center;
        margin-bottom: 1rem;
        box-shadow: 0px 4px 10px rgba(0,0,0,0.15);
    }
    .header h1 {
        font-size: 2.3rem;
        margin-bottom: 0.3rem;
    }
    .header p {
        font-size: 1.1rem;
        opacity: 0.9;
    }

    .metric-card {
        border-radius: 14px;
        padding: 1.2rem;
        text-align: center;
        box-shadow: 0px 3px 8px rgba(0,0,0,0.08);
        transition: transform 0.2s ease-in-out;
    }
    .metric-card:hover {
        transform: scale(1.02);
    }
    .metric-title {
        font-size: 1.1rem;
        color: #333;
        margin-bottom: 0.4rem;
    }
    .metric-value {
        font-size: 2rem;
        font-weight: bold;
    }
    .metric-delta {
        font-size: 1rem;
        margin-top: 0.3rem;
        font-weight: 500;
    }
    .delta-positive {
        color: #0B8043;
    }
    .delta-negative {
        color: #D93025;
    }

    /* Progress section */
    .progress-container {
        margin-top: 1.2rem;
        padding: 1rem;
        background-color: #F1F3F4;
        border-radius: 10px;
        text-align: center;
        box-shadow: inset 0px 2px 6px rgba(0,0,0,0.05);
    }
    progress {
        width: 80%;
        height: 20px;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)



# --- Sidebar Navigation ---
# st.sidebar.subheader("Navigation")
pages = {
    "Home": "🏠",
    "Helpdesk": "🤖",
    "Assisted Learning": "📚",
    "Tickets Insights": "🧾"
}

selected_page = st.sidebar.radio(
    "Navigation",
    options=list(pages.keys()),
    format_func=lambda x: f"{pages[x]} {x}"
)


if selected_page == "Home":
    st.markdown("""
    <div class="header">
        <h1>🤖 AI Support Assistant</h1>
        <p>Your unified hub for intelligent support insights & automation</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    Welcome to **AI Support Assistant**, your unified platform for support analytics and intelligent chat.

    This tool helps your company:
    - 💬 Chat with an AI agent trained on company policies, guides, and FAQs  
    - 📚 Search and explore the **Knowledge Base**  
    - 🧾 View and analyze **Support Tickets** performance metrics  

    Use the sidebar to navigate between sections.
    """)

    st.divider()
    st.markdown("### Support Metrics Overview")

    try:
        df = load_summary_growth().iloc[0]

        # Extract values
        total_tickets = int(df["total_tickets_all_time"])
        resolved = int(df["resolved_all_time"])
        agents = int(df["total_agents_all_time"])

        last_month_tickets = int(df["tickets_last_month"])
        last_month_resolved = int(df["resolved_last_month"])
        last_month_agents = int(df["agents_last_month"])

        # Compute growth vs. total history before last month
        def pct_growth(curr_month, total_all):
            prev_total = total_all - curr_month
            if prev_total <= 0:
                return 0
            return round((curr_month / prev_total) * 100, 1)

        delta_tickets = pct_growth(last_month_tickets, total_tickets)
        delta_resolved = pct_growth(last_month_resolved, resolved)
        delta_agents = pct_growth(last_month_agents, agents)

    except Exception as e:
        st.error(f"❌ Could not fetch metrics: {e}")
        total_tickets = resolved = agents = 0
        delta_tickets = delta_resolved = delta_agents = 0


    def delta_html(value):
        symbol = "▲" if value > 0 else ("▼" if value < 0 else "—")
        css_class = "delta-positive" if value > 0 else ("delta-negative" if value < 0 else "")
        return f"<span class='metric-delta {css_class}'>{symbol} {abs(value)}%</span>"

    col1, col2, col3 = st.columns(3)

    col1.markdown(
        f"""
        <div class="metric-card" style="background-color:#E8F0FE;">
            <div class="metric-title">Total Tickets</div>
            <div class="metric-value" style="color:#165CCC;">{total_tickets:,}</div>
            {delta_html(delta_tickets)}<br/>
            <small style="color:gray;">vs last 1 month ({last_month_tickets:,} new)</small>
        </div>
        """,
        unsafe_allow_html=True
    )

    col2.markdown(
        f"""
        <div class="metric-card" style="background-color:#E6F4EA;">
            <div class="metric-title">Resolved Tickets</div>
            <div class="metric-value" style="color:#0B8043;">{resolved:,}</div>
            {delta_html(delta_resolved)}<br/>
            <small style="color:gray;">{last_month_resolved:,} resolved last month</small>
        </div>
        """,
        unsafe_allow_html=True
    )

    col3.markdown(
        f"""
        <div class="metric-card" style="background-color:#FFF4E5;">
            <div class="metric-title">Active Agents</div>
            <div class="metric-value" style="color:#F9AB00;">{agents:,}</div>
            {delta_html(delta_agents)}<br/>
            <small style="color:gray;">{last_month_agents:,} active last month</small>
        </div>
        """,
        unsafe_allow_html=True
    )

    # ------------------------------------------------------------
    # 📊 Progress Visualization
    # ------------------------------------------------------------
    progress_ratio = resolved / total_tickets if total_tickets else 0

    st.markdown(f"""
    <div class="progress-container">
        <h4>🎯 Ticket Resolution Progress</h4>
        <progress value="{progress_ratio}" max="1"></progress>
        <p><b>{progress_ratio*100:.1f}%</b> tickets resolved</p>
    </div>
    """, unsafe_allow_html=True)

    st.text(" ")

    # Optional dynamic feedback
    if progress_ratio == 1:
        st.success("✅ All tickets resolved! Excellent work by the support team 🎉")
    elif progress_ratio > 0.7:
        st.info("🚀 Support performance improving steadily!")
    else:
        st.warning("📈 Keep pushing — room to resolve more tickets!")


elif selected_page == "Helpdesk":
    from _pages import helpdesk
    helpdesk.show_page()
elif selected_page == "Assisted Learning":
    from _pages import assisted_learning
    assisted_learning.show_page()
elif selected_page == "Tickets Insights":
    from _pages import insights
    insights.show_page()

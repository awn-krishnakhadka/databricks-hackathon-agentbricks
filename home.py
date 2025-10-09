import streamlit as st
from utils.db import sqlQuery
import pandas as pd

st.set_page_config(
    page_title="AI Support Assistant",
    layout="wide"
)

st.title("AI Support Assistant")
st.markdown("""
Welcome to **AI Support Assistant**, your unified platform for support analytics and intelligent chat.

This tool helps your company:
- 💬 Chat with an AI agent trained on company policies, guides, and FAQs.
- 📚 Search and explore the **Knowledge Base**.
- 🧾 View and analyze **Support Tickets** performance metrics.

Use the sidebar to navigate between sections.
""")

@st.cache_data(ttl=300)
def load_summary():
    query = """
        SELECT 
            COUNT(*) AS total_tickets,
            SUM(CASE WHEN lower(Status) = 'resolved' or lower(Status) = 'closed' THEN 1 ELSE 0 END) AS resolved_tickets,
            COUNT(DISTINCT Agent_ID) AS total_agents
        FROM workspace_west_2.default.st_query_parsed
    """
    return sqlQuery(query)


st.divider()
st.subheader("📊 Support Metrics Overview")

# col1, col2, col3 = st.columns(3)
# col1.metric("Total Tickets", "1,245", "+12%")
# col2.metric("Avg. Resolution Time", "3.2 hrs", "-8%")
# col3.metric("CSAT Score", "92%", "+2%")

# st.progress(0.75)
# st.caption("Support performance improving over time 🚀")

try:
    summary = load_summary()
    total_tickets = int(summary["total_tickets"].iloc[0])
    resolved = int(summary["resolved_tickets"].iloc[0])
    agents = int(summary["total_agents"].iloc[0])
except Exception as e:
    st.error(f"❌ Could not fetch metrics: {e}")
    total_tickets, resolved, agents = 0, 0, 0

# Display dashboard metrics
col1, col2, col3 = st.columns(3)
col1.metric("Total Tickets", total_tickets)
col2.metric("Resolved Tickets", resolved)
col3.metric("Active Agents", agents)
remaining_tickets=100 - (total_tickets-resolved)
if (int(remaining_tickets)==0):
    st.progress(1.0)
    st.caption("No open tickets, all tickets resolved")
else:
    st.progress(remaining_tickets/100)
    st.caption("Support performance improving over time 🚀")

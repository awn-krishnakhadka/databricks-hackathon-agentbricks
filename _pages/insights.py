import streamlit as st
import pandas as pd
import plotly.express as px
from utils.db import sqlQuery
import os
from databricks.sdk import WorkspaceClient

def show_page():
    st.markdown(
        """
        <style>
        /* General page background */
        # .stApp {
        #     background-color: #f0f2f6;
        # }

        /* Metric Cards */
        .metric-card {
            padding: 1rem;
            border-radius: 12px;
            color: white;
            text-align: center;
            box-shadow: 0 4px 12px rgba(0,0,0,0.08);
            margin-bottom: 1rem;
        }
        .metric-title {
            font-size: 0.95rem;
            font-weight: 600;
            opacity: 0.85;
        }
        .metric-value {
            font-size: 1.8rem;
            font-weight: 700;
        }

        /* Filter Card */
        # .filter-card {
        #     background-color: white;
        #     padding: 1rem;
        #     border-radius: 12px;
        #     box-shadow: 0 4px 12px rgba(0,0,0,0.06);
        #     margin-bottom: 1rem;
        # }

        /* Genie Card */
        # .genie-card {
        #     background-color: #E8F0FE;
        #     padding: 1rem;
        #     border-radius: 12px;
        #     box-shadow: 0 4px 12px rgba(0,0,0,0.06);
        #     margin-bottom: 1rem;
        # }

        /* Data Table Container */
        .table-card {
            background-color: white;
            padding: 0.5rem;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.06);
            margin-top: 1rem;
        }
        </style>
        """, unsafe_allow_html=True
    )

    st.title("Insights Dashboard")

    @st.cache_data(ttl=300)
    def load_tickets():
        query = """
            SELECT Ticket_ID, Agent_ID, Category, Status, Priority,
                   Created, Resolved, Customer_ID, Resolution
            FROM workspace_west_2.default.st_query_parsed
        """
        return sqlQuery(query)
    
    @st.cache_data(ttl=300)
    def load_summary_growth():
        query = """
            WITH monthly_stats AS (
                SELECT
                    DATE_TRUNC('month', Created) AS month,
                    COUNT(*) AS total_tickets,
                    SUM(CASE WHEN LOWER(Status) = 'resolved' THEN 1 ELSE 0 END) AS resolved_tickets,
                    SUM(CASE WHEN LOWER(Status) = 'closed' THEN 1 ELSE 0 END) AS closed_tickets,
                    SUM(CASE WHEN LOWER(Status) = 'open' THEN 1 ELSE 0 END) AS open_tickets
                FROM workspace_west_2.default.st_query_parsed
                GROUP BY 1
            ),
            totals AS (
                SELECT
                    SUM(total_tickets) AS total_tickets_all_time,
                    SUM(resolved_tickets) AS resolved_all_time,
                    SUM(closed_tickets) AS closed_all_time,
                    SUM(open_tickets) AS open_all_time
                FROM monthly_stats
            ),
            last_month AS (
                SELECT *
                FROM monthly_stats
                ORDER BY month DESC
                LIMIT 1
            )
            SELECT
                t.total_tickets_all_time,
                t.resolved_all_time,
                t.closed_all_time,
                t.open_all_time,
                lm.total_tickets AS tickets_last_month,
                lm.resolved_tickets AS resolved_last_month,
                lm.closed_tickets AS closed_last_month,
                lm.open_tickets AS open_last_month
            FROM totals t
            CROSS JOIN last_month lm;
        """
        return sqlQuery(query)

    try:
        tickets = load_tickets()
    except Exception as e:
        st.error(f"❌ Failed to fetch tickets: {e}")
        st.stop()

    # --- Metrics Cards with gradient colors ---
    total_tickets = len(tickets)
    resolved_tickets = len(tickets[tickets['Status'].str.lower() == 'resolved'])
    closed_tickets = len(tickets[tickets['Status'].str.lower() == 'closed'])
    open_tickets = len(tickets[tickets['Status'].str.lower() == 'open'])
    tickets['Created'] = pd.to_datetime(tickets['Created'], errors='coerce')
    tickets['Resolved'] = pd.to_datetime(tickets['Resolved'], errors='coerce')
    tickets['Resolution_Hours'] = (tickets['Resolved'] - tickets['Created']).dt.total_seconds() / 3600
    try:
        df = load_summary_growth().iloc[0]

        # Extract values
        total_tickets = int(df["total_tickets_all_time"])
        resolved = int(df["resolved_all_time"])
        closed = int(df["closed_all_time"])
        open_tickets = int(df["open_all_time"])

        # Last month values
        last_month_tickets = int(df["tickets_last_month"])
        last_month_resolved = int(df["resolved_last_month"])
        last_month_closed = int(df["closed_last_month"])
        last_month_open = int(df["open_last_month"])

        # Compute growth vs previous total
        def pct_growth(curr_month, total_all):
            prev_total = total_all - curr_month
            if prev_total <= 0:
                return 0
            return round((curr_month / prev_total) * 100, 1)

        delta_tickets = pct_growth(last_month_tickets, total_tickets)
        delta_resolved = pct_growth(last_month_resolved, resolved)
        delta_closed = pct_growth(last_month_closed, closed)
        delta_open = pct_growth(last_month_open, open_tickets)

    except Exception as e:
        st.error(f"❌ Could not fetch metrics: {e}")
        total_tickets = resolved = closed = open_tickets = 0
        delta_tickets = delta_resolved = delta_closed = delta_open = 0


    # --- Helper for delta HTML ---
    def delta_html(value):
        symbol = "▲" if value > 0 else ("▼" if value < 0 else "—")
        css_class = "delta-positive" if value > 0 else ("delta-negative" if value < 0 else "")
        return f"<span class='metric-delta {css_class}'>{symbol} {abs(value)}%</span>"


    # --- Metric cards ---
    col1, col2, col3, col4 = st.columns(4)

    col1.markdown(
        f"""
        <div class="metric-card" style="background-color:#E8F0FE;">
            <div class="metric-title">Total Tickets</div>
            <div class="metric-value" style="color:#165CCC;">{total_tickets:,}</div>
            {delta_html(delta_tickets)}<br/>
            <small style="color:gray;">{last_month_tickets:,} last month</small>
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
            <small style="color:gray;">{last_month_resolved:,} last month</small>
        </div>
        """,
        unsafe_allow_html=True
    )

    col3.markdown(
        f"""
        <div class="metric-card" style="background-color:#DDEAF6;">
            <div class="metric-title">Closed Tickets</div>
            <div class="metric-value" style="color:#1E88E5;">{closed:,}</div>
            {delta_html(delta_closed)}<br/>
            <small style="color:gray;">{last_month_closed:,} last month</small>
        </div>
        """,
        unsafe_allow_html=True
    )

    col4.markdown(
        f"""
        <div class="metric-card" style="background-color:#FDE2E1;">
            <div class="metric-title">Open Tickets</div>
            <div class="metric-value" style="color:#D32F2F;">{open_tickets:,}</div>
            {delta_html(delta_open)}<br/>
            <small style="color:gray;">{last_month_open:,} last month</small>
        </div>
        """,
        unsafe_allow_html=True
    )

    # --- Multi-color Progress Bar ---
    st.markdown("##### 🎯 Ticket Resolution Progress")

    closed_ratio = closed_tickets / total_tickets if total_tickets else 0
    resolved_ratio = resolved_tickets / total_tickets if total_tickets else 0
    open_ratio = open_tickets / total_tickets if total_tickets else 0  # optional for remaining

    st.markdown(f"""
    <div style="width: 100%; background-color: #e0e0e0; border-radius: 8px; overflow: hidden; height: 25px; display: flex;">
        <div style="width: {resolved_ratio*100:.1f}%; background-color: #28a745;"></div>
        <div style="width: {closed_ratio*100:.1f}%; background-color: #3498db;"></div>
        <div style="width: {open_ratio*100:.1f}%; background-color: #e74c3c;"></div>
    </div>
    <div style="display: flex; justify-content: space-between; margin-top: 4px; font-size: 0.9rem;">
        <span style="color:#28a745;">Resolved: {resolved_tickets}</span>
        <span style="color:#3498db;">Closed: {closed_tickets}</span>
        <span style="color:#e74c3c;">Open: {open_tickets}</span>
    </div>
    """, unsafe_allow_html=True)

    st.text(" ")

    if resolved_ratio + closed_ratio == 1:
        st.success("✅ All tickets resolved or closed! Excellent work 🎉")
    elif resolved_ratio + closed_ratio > 0.7:
        st.info("🚀 Support performance improving steadily!")
    else:
        st.warning("📈 Keep pushing — room to resolve more tickets!")

    st.divider()

    st.markdown("##### Filter Tickets")
    with st.container():
        col1, col2, col3 = st.columns(3)
        with col1:
            status_filter = st.multiselect("Status", options=tickets['Status'].unique(), default=tickets['Status'].unique())
        with col2:
            category_filter = st.multiselect("Category", options=tickets['Category'].unique(), default=tickets['Category'].unique())
        with col3:
            priority_filter = st.multiselect("Priority", options=tickets['Priority'].unique(), default=tickets['Priority'].unique())
        st.markdown('</div>', unsafe_allow_html=True)

    filtered = tickets[
        (tickets['Status'].isin(status_filter)) &
        (tickets['Category'].isin(category_filter)) &
        (tickets['Priority'].isin(priority_filter))
    ]
    st.markdown(f"Showing **{len(filtered)} tickets** after filtering.")

    # st.subheader("Visual Insights")
    grid_col1, grid_col2 = st.columns(2)
    with grid_col1:
        fig1 = px.pie(
            filtered, names='Status', title="Tickets by Status",
            color='Status', color_discrete_map={'Resolved':'green','Closed':'blue','Open':'red'}
        )
        st.plotly_chart(fig1, use_container_width=True)

    with grid_col2:
        category_counts = filtered['Category'].value_counts().reset_index()
        category_counts.columns = ['Category', 'Count']
        fig2 = px.bar(category_counts, x='Category', y='Count', text='Count', title="Tickets by Category",
                      color='Category', color_discrete_sequence=px.colors.qualitative.Pastel)
        st.plotly_chart(fig2, use_container_width=True)

    with grid_col1:
        res_time = filtered[['Resolution_Hours']].dropna()
        if not res_time.empty:
            hist = pd.cut(res_time['Resolution_Hours'], bins=30).value_counts().sort_index()
            hist_df = pd.DataFrame({
                'Resolution_Hours': [interval.mid for interval in hist.index],
                'Ticket_Count': hist.values
            })
            hist_df['Smoothed_Count'] = hist_df['Ticket_Count'].rolling(window=3, center=True, min_periods=1).mean()
            plot_df = hist_df[hist_df['Smoothed_Count'] > 0]
            fig3 = px.line(
                plot_df, x='Resolution_Hours', y='Smoothed_Count',
                title="Smoothed Resolution Time Distribution (hrs) vs Ticket Count",
                labels={'Resolution_Hours': 'Resolution Hours', 'Smoothed_Count': 'Ticket Count'},
                markers=True
            )
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("No resolution time data available.")

    with grid_col2:
        if 'Created' in filtered.columns:
            trend = filtered.groupby(filtered['Created'].dt.date).size().reset_index(name='Tickets')
            trend['Cumulative_Tickets'] = trend['Tickets'].cumsum()
            fig4 = px.line(trend, x='Created', y='Cumulative_Tickets', title="Cumulative Tickets Created Over Time")
            st.plotly_chart(fig4, use_container_width=True)


    st.markdown("##### Tickets Table")
    st.dataframe(filtered, use_container_width=True)

    st.divider()

    # --- AI Genie Chat in a card ---
    st.subheader("💬 Ask Genie")
    space_id = os.getenv("GENIE_SPACE_ID")
    w = WorkspaceClient()

    if "genie_response" not in st.session_state:
        st.session_state.genie_response = []

    with st.container():
        user_query = st.text_input("Ask Genie something about tickets or products:")

        if st.button("Send to Genie"):
            if user_query.strip() != "":
                try:
                    response = w.genie.start_conversation_and_wait(space_id=space_id, content=user_query)
                    messages = [att.text.content for att in response.attachments if hasattr(att.text, "content")]
                    if messages:
                        st.session_state.genie_response.append({"query": user_query, "responses": messages})
                    else:
                        st.warning("Genie did not return any text response.")
                except Exception as e:
                    st.error(f"Failed to connect to Genie: {e}")

        for conv in st.session_state.genie_response:
            st.markdown(f"**You:** {conv['query']}")
            for msg in conv['responses']:
                st.markdown(f"**Genie:** {msg}")
        st.markdown('</div>', unsafe_allow_html=True)

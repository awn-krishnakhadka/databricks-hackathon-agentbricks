import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
from utils.db import sqlQuery
import os
from databricks.sdk import WorkspaceClient
from datetime import timedelta
import time
import traceback

st.set_page_config(page_title="Tickets Dashboard", layout="wide")

st.title("Support Tickets Analysis")
# st.markdown("Analyze all support tickets with interactive charts and metrics.")

# --- Load data from Databricks ---
@st.cache_data(ttl=300)
def load_tickets():
    query = """
        SELECT 
            Ticket_ID,
            Agent_ID,
            Category,
            Status,
            Priority,
            Created,
            Resolved,
            Customer_ID,
            Resolution
        FROM workspace_west_2.default.st_query_parsed
    """
    return sqlQuery(query)

try:
    tickets = load_tickets()
except Exception as e:
    st.error(f"❌ Failed to fetch tickets: {e}")
    st.stop()

# --- Basic Metrics ---
total_tickets = len(tickets)
resolved_tickets = len(tickets[tickets['Status'].str.lower() == 'resolved'])
closed_tickets = len(tickets[tickets['Status'].str.lower() == 'closed'])
open_tickets = len(tickets[tickets['Status'].str.lower() == 'open'])

# st.subheader("📊 Ticket Metrics")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Tickets", total_tickets)
col2.metric("Resolved Tickets", resolved_tickets)
col3.metric("Closed Tickets", closed_tickets)
col4.metric("Open Tickets", open_tickets)

# --- Progress bar for resolution ---
st.text("Closed tickets Progress")
if total_tickets > 0:
    st.progress(closed_tickets / total_tickets)
else:
    st.progress(0)

st.divider()

space_id = os.getenv("GENIE_SPACE_ID")
w = WorkspaceClient()

# Initialize session state for conversation
if "genie_response" not in st.session_state:
    st.session_state.genie_response = []

# Input query
user_query = st.text_input("Ask Genie something about tickets or products:")

# Button to start chat
if st.button("Send to Genie"):
    if user_query.strip() != "":
        try:
            # Start conversation
            response = w.genie.start_conversation_and_wait(
                space_id=space_id,
                content=user_query
            )

            # Collect Genie responses safely
            messages = []
            for attachment in response.attachments:
                # Some attachments may not have text
                if attachment.text and hasattr(attachment.text, "content"):
                    messages.append(attachment.text.content)

            # Save responses in session state
            if messages:
                st.session_state.genie_response.append({
                    "query": user_query,
                    "responses": messages
                })
            else:
                st.warning("Genie did not return any text response.")

        except Exception as e:
            st.error(f"Failed to connect to Genie: {e}")

# Display previous conversation
for conv in st.session_state.genie_response:
    st.markdown(f"**You:** {conv['query']}")
    for msg in conv['responses']:
        st.markdown(f"**Genie:** {msg}")
    st.divider()
st.divider()
# --- Data Preprocessing ---
tickets['Created'] = pd.to_datetime(tickets['Created'], errors='coerce')
tickets['Resolved'] = pd.to_datetime(tickets['Resolved'], errors='coerce')
tickets['Resolution_Hours'] = (tickets['Resolved'] - tickets['Created']).dt.total_seconds() / 3600

# --- Interactive Filters ---
st.subheader("Support Data Analysis")
col1, col2, col3 = st.columns(3)

with col1:
    status_filter = st.multiselect(
        "Status", options=tickets['Status'].unique(), default=tickets['Status'].unique()
    )
with col2:
    category_filter = st.multiselect(
        "Category", options=tickets['Category'].unique(), default=tickets['Category'].unique()
    )
with col3:
    priority_filter = st.multiselect(
        "Priority", options=tickets['Priority'].unique(), default=tickets['Priority'].unique()
    )

filtered = tickets[
    (tickets['Status'].isin(status_filter)) &
    (tickets['Category'].isin(category_filter)) &
    (tickets['Priority'].isin(priority_filter))
]
st.markdown(f"Showing **{len(filtered)} tickets** after filtering.")

st.dataframe(filtered, use_container_width=True)

st.divider()

# --- 2x2 Grid Plots ---
grid_col1, grid_col2 = st.columns(2)

# 1️⃣ Tickets by Status (Pie)
with grid_col1:
    fig1 = px.pie(filtered, names='Status', title="Tickets by Status",
                  color='Status', color_discrete_map={'Resolved':'green','Closed':'blue','Open':'red'})
    st.plotly_chart(fig1, use_container_width=True)

# 2️⃣ Tickets by Category (Bar)
with grid_col2:
    category_counts = filtered['Category'].value_counts().reset_index()
    category_counts.columns = ['Category', 'Count']
    fig2 = px.bar(category_counts, x='Category', y='Count', text='Count', title="Tickets by Category")
    st.plotly_chart(fig2, use_container_width=True)

# 3️⃣ Resolution Time Distribution (line)
with grid_col1:
    res_time = filtered[['Resolution_Hours']].dropna()
    if not res_time.empty:
        # Create histogram bins
        hist = pd.cut(res_time['Resolution_Hours'], bins=30).value_counts().sort_index()

        # Convert Interval index to midpoint numeric
        hist_df = pd.DataFrame({
            'Resolution_Hours': [interval.mid for interval in hist.index],
            'Ticket_Count': hist.values
        })

        # Smooth the counts using rolling average
        hist_df['Smoothed_Count'] = hist_df['Ticket_Count'].rolling(window=3, center=True, min_periods=1).mean()

        # Filter out zero counts
        plot_df = hist_df[hist_df['Smoothed_Count'] > 0]

        # Plotly line chart
        fig3 = px.line(
            plot_df,
            x='Resolution_Hours',
            y='Smoothed_Count',
            title="Smoothed Resolution Time Distribution (hrs) vs Ticket Count",
            labels={'Resolution_Hours': 'Resolution Hours', 'Smoothed_Count': 'Ticket Count'},
            markers=True
        )
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("No resolution time data available.")


# 4️⃣ Tickets Created Over Time (cumulative)
with grid_col2:
    if 'Created' in filtered.columns:
        trend = filtered.groupby(filtered['Created'].dt.date).size().reset_index(name='Tickets')
        trend['Cumulative_Tickets'] = trend['Tickets'].cumsum()
        fig4 = px.line(trend, x='Created', y='Cumulative_Tickets', title="Cumulative Tickets Created Over Time")
        st.plotly_chart(fig4, use_container_width=True)
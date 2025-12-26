
import streamlit as st
import pandas as pd
import sqlite3
import os
import plotly.express as px

# --- Configuration ---
DB_PATH = os.path.join("data", "xauusd_news.db")
PAGE_TITLE = "🤖 Signals Bot Dashboard"
LAYOUT = "wide"

st.set_page_config(page_title=PAGE_TITLE, layout=LAYOUT)

# --- Database Function ---
def load_data():
    """
    Connect to SQLite and load trade_history table.
    """
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    
    try:
        conn = sqlite3.connect(DB_PATH)
        query = "SELECT * FROM trade_history ORDER BY close_time DESC"
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        # Data Processing
        # Ensure numeric columns are actually numeric
        numeric_cols = ['volume', 'open_price', 'sl', 'tp', 'close_price', 'profit']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
                
        # Handle Date Columns
        date_cols = ['open_time', 'close_time']
        for col in date_cols:
             if col in df.columns:
                 df[col] = pd.to_datetime(df[col], errors='coerce')
                 
        return df
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame()

# --- Main Layout ---
st.title(PAGE_TITLE)

# Refresh Button
if st.button("🔄 Refresh Data"):
    st.cache_data.clear() # Clear cache if implemented, or just rerun
    st.rerun()

# Load Data
df = load_data()

if df.empty:
    st.warning("⚠️ No trade data found. The database might be empty or the table 'trade_history' does not exist.")
else:
    # --- Metrics Section (Top Row) ---
    # Filter closed trades for clearer stats (or include open? Request said 'closed trades' for Total Trades)
    # Actually request: "Total Trades: Count of closed trades". 
    # Win Rate: Profit > 0
    
    closed_trades = df[df['status'] == 'CLOSED']
    total_closed = len(closed_trades)
    
    # Win Rate calculation
    if total_closed > 0:
        wins = len(closed_trades[closed_trades['profit'] > 0])
        win_rate = (wins / total_closed) * 100
    else:
        win_rate = 0.0
        
    # Net Profit (Request: Sum of 'profit' column - implying all processed trades?)
    # Usually Net Profit implies realized profit, i.e., closed trades.
    # Open trades have 'profit' as floating PnL (updated by monitor).
    # If users want current equity impact, we should include open.
    # But usually dashboard stats focus on Realized.
    # Ref: "Count of closed trades" for metric 1. 
    # Let's assume Net Profit is likewise Realized Profit to correspond to Win Rate and Total Closed.
    net_profit = closed_trades['profit'].sum()

    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Trades (Closed)", f"{total_closed}")
        
    with col2:
        st.metric("Win Rate", f"{win_rate:.1f}%")
        
    with col3:
        st.metric("Net Profit", f"${net_profit:,.2f}", delta_color="normal" if net_profit >= 0 else "inverse")

    st.markdown("---")

    # --- Charts Section ---
    chart_col1, chart_col2 = st.columns(2)
    
    with chart_col1:
        st.subheader("📈 Cumulative PnL")
        # Sort by close_time ascending for cumulative calculation
        if not closed_trades.empty:
            chart_df = closed_trades.sort_values(by="close_time").copy()
            chart_df['cumulative_pnl'] = chart_df['profit'].cumsum()
            
            fig_line = px.line(chart_df, x="close_time", y="cumulative_pnl", 
                               title="Cumulative Profit Over Time",
                               labels={"cumulative_pnl": "Profit (USD)", "close_time": "Time"},
                               markers=True)
            st.plotly_chart(fig_line, use_container_width=True)
        else:
            st.info("No closed trades to plot Cumulative PnL.")

    with chart_col2:
        st.subheader("📊 PnL Distribution")
        if not closed_trades.empty:
            # Bar chart of profit per ticket
            # Color bars by profit > 0
            closed_trades['color'] = closed_trades['profit'] > 0
            fig_bar = px.bar(closed_trades, x="ticket", y="profit",
                             color="color",
                             color_discrete_map={True: 'green', False: 'red'},
                             title="Profit/Loss per Trade",
                             labels={"profit": "Profit (USD)", "ticket": "Ticket ID"})
            fig_bar.update_layout(showlegend=False)
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("No closed trades to plot PnL Distribution.")

    st.markdown("---")
    
    # --- Data Table Section ---
    st.subheader("📋 Trade History Details")
    
    # Style text for profit column
    def color_profit(val):
        color = 'green' if val > 0 else 'red' if val < 0 else 'black'
        return f'color: {color}'
    
    # Standard dataframe display
    # Sorting by close_time descending (done in SQL or Pandas)
    # df is already sorted by close_time DESC from SQL query above.
    
    # Selecting relevant columns for display
    display_cols = ['ticket', 'symbol', 'order_type', 'volume', 'open_price', 'close_price', 'profit', 'status', 'open_time', 'close_time', 'sl', 'tp']
    # Filter only existing columns
    display_cols = [c for c in display_cols if c in df.columns]
    
    st.dataframe(
        df[display_cols].style.applymap(color_profit, subset=['profit']),
        use_container_width=True,
        height=500
    )

    # Auto-refresh hint
    st.caption(f"Last updated: {pd.Timestamp.now()}")

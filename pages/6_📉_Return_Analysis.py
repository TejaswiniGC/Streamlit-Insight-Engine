import streamlit as st
import pandas as pd
import plotly.express as px # Still needed for px.colors if you explicitly reference them
from datetime import datetime, date # Import date as well
from utils.data_loader import load_ecommerce_data, load_returned_products_data, get_filtered_data
from utils.kpi_calculations import format_kpi_number
from utils.plot_utils import plot_time_series, plot_bar_chart # Ensure these are imported

st.set_page_config(layout="wide", page_title="Return Analysis", page_icon="📉")

css_file_path = "styles.css"

# Check if the file exists before trying to read it
try:
    with open(css_file_path) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except FileNotFoundError:
    st.error(f"Could not find {css_file_path}.")

st.title("📉 Product Return Analysis")

st.markdown("""
This dashboard provides insights into product returns. It aggregates sales and return data
by product and date to calculate return rates and identify common return reasons.
\n**Note:** Without specific order IDs for returns, the return rate is calculated based on
aggregated daily sales and returns for a given product.
""")

df_orders = load_ecommerce_data()
df_returns = load_returned_products_data()

# --- Data Validation ---
if df_orders.empty:
    st.error("Sales order data could not be loaded. Please check BigQuery connection and table configuration.")
    st.stop()
if df_returns.empty:
    st.error("Returned products data could not be loaded. Please check Google Sheet connection and sheet configuration (.streamlit/secrets.toml and sheet sharing).")
    st.stop()

required_sales_cols = ['order_date', 'product_name', 'quantity', 'line_item_revenue']
if not all(col in df_orders.columns for col in required_sales_cols):
    st.error(f"Sales data is missing one or more required columns for return analysis: {required_sales_cols}. Please verify your `merged_orderdata` schema.")
    st.stop()

required_returns_cols = ['return_date', 'product_name', 'returned_quantity', 'return_comments'] # Added return_comments for robustness
if not all(col in df_returns.columns for col in required_returns_cols):
    st.error(f"Returned products data is missing one or more required columns: {required_returns_cols}. Please verify your Google Sheet columns match expected names.")
    st.stop()

# Ensure date columns are datetime objects
df_orders['order_date'] = pd.to_datetime(df_orders['order_date'])
df_returns['return_date'] = pd.to_datetime(df_returns['return_date'])


# --- Sidebar Filters ---
st.sidebar.header("Apply Filters")

# Determine min/max dates from ALL loaded data (before any filtering)
all_dates = []
if 'order_date' in df_orders.columns and not df_orders['order_date'].dropna().empty:
    all_dates.extend(df_orders['order_date'].dt.date.tolist())
if 'return_date' in df_returns.columns and not df_returns['return_date'].dropna().empty:
    all_dates.extend(df_returns['return_date'].dt.date.tolist())

if all_dates:
    min_date_available = min(all_dates)
    max_date_available = max(all_dates)
else:
    min_date_available = date(2020, 1, 1) # Default if no dates found
    max_date_available = date.today()

# Date Range Selection (single box)
date_range = st.sidebar.date_input(
    "Select Date Range",
    value=(min_date_available, max_date_available),
    min_value=min_date_available,
    max_value=max_date_available
)

# Initialize filtered DataFrames based on date range
df_orders_filtered = pd.DataFrame()
df_returns_filtered = pd.DataFrame()

if len(date_range) == 2:
    start_date, end_date = date_range
    if start_date > end_date:
        st.sidebar.error("Error: Start date cannot be after end date. Displaying all available dates.")
        df_orders_filtered = df_orders.copy()
        df_returns_filtered = df_returns.copy()
    else:
        df_orders_filtered = get_filtered_data(df_orders, start_date, end_date) # Assuming get_filtered_data handles order_date
        df_returns_filtered = df_returns[(df_returns['return_date'].dt.date >= start_date) &
                                         (df_returns['return_date'].dt.date <= end_date)].copy()
else:
    st.sidebar.warning("Please select both a start and end date for filtering. Displaying all available dates.")
    df_orders_filtered = df_orders.copy()
    df_returns_filtered = df_returns.copy()

# Product Name Filter
all_product_names = sorted(df_orders_filtered['product_name'].dropna().unique().tolist() +
                           df_returns_filtered['product_name'].dropna().unique().tolist())
unique_product_names = ['All'] + sorted(list(set(all_product_names))) # Get unique names from both DFs
selected_product_name = st.sidebar.selectbox("Filter by Product Name", unique_product_names)

# Apply product name filter after date filtering
if selected_product_name != 'All':
    df_orders_filtered = df_orders_filtered[df_orders_filtered['product_name'] == selected_product_name].copy()
    df_returns_filtered = df_returns_filtered[df_returns_filtered['product_name'] == selected_product_name].copy()


# Check for data after all filters
if df_orders_filtered.empty and df_returns_filtered.empty:
    st.info("No data available for the selected filters. Please adjust your filters.")
    st.stop()


# Aggregate sales data by date and product
df_sales_aggregated = df_orders_filtered.groupby([
    df_orders_filtered['order_date'].dt.date.rename('date'),
    'product_name'
]).agg(
    total_sold_quantity=('quantity', 'sum'),
    total_sales_revenue=('line_item_revenue', 'sum')
).reset_index()

# Aggregate returns data by date and product
df_returns_aggregated = df_returns_filtered.groupby([
    df_returns_filtered['return_date'].dt.date.rename('date'),
    'product_name'
]).agg(
    total_returned_quantity=('returned_quantity', 'sum')
).reset_index()


# Merge aggregated sales and returns data
df_combined = pd.merge(df_sales_aggregated, df_returns_aggregated,
                         on=['date', 'product_name'],
                         how='outer').fillna(0)

# Calculate Return Rate (as a percentage)
df_combined['return_rate_percentage'] = df_combined.apply(
    lambda row: (row['total_returned_quantity'] / row['total_sold_quantity']) * 100
    if row['total_sold_quantity'] > 0 else 0,
    axis=1
)

# Calculate Estimated Returned Value (assuming average price from sales)
df_combined['estimated_unit_price'] = df_combined.apply(
    lambda row: row['total_sales_revenue'] / row['total_sold_quantity']
    if row['total_sold_quantity'] > 0 else 0,
    axis=1
)
df_combined['estimated_returned_value'] = df_combined['total_returned_quantity'] * df_combined['estimated_unit_price']


st.header("Overall Return Metrics")
total_sold = df_combined['total_sold_quantity'].sum()
total_returned = df_combined['total_returned_quantity'].sum()
total_sales_value = df_combined['total_sales_revenue'].sum()
total_estimated_returned_value = df_combined['estimated_returned_value'].sum()

overall_return_rate = (total_returned / total_sold) * 100 if total_sold > 0 else 0

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric(label="Total Products Sold", value=f"{format_kpi_number(int(total_sold))}")
with col2:
    st.metric(label="Total Products Returned", value=f"{format_kpi_number(int(total_returned))}")
with col3:
    # Ensure percentages are formatted correctly by format_kpi_number
    st.metric(label="Overall Return Rate", value=f"{format_kpi_number(overall_return_rate)}%")
with col4:
    st.metric(label="Estimated Total Value of Returns", value=f"₹{format_kpi_number(total_estimated_returned_value)}")

st.markdown("---")

st.header("Products by Return Quantity and Rate")
df_product_returns = df_combined.groupby('product_name').agg(
    total_returned_quantity=('total_returned_quantity', 'sum'),
    total_sold_quantity=('total_sold_quantity', 'sum'),
    estimated_returned_value=('estimated_returned_value', 'sum')
).reset_index()

df_product_returns['return_rate_percentage'] = df_product_returns.apply(
    lambda row: (row['total_returned_quantity'] / row['total_sold_quantity']) * 100
    if row['total_sold_quantity'] > 0 else 0,
    axis=1
)

df_product_returns_sorted_qty = df_product_returns.sort_values(by='total_returned_quantity', ascending=False)
df_product_returns_sorted_rate = df_product_returns.sort_values(by='return_rate_percentage', ascending=False)

col_top_qty, col_top_rate = st.columns(2)

with col_top_qty:
    st.write("Top 10 Products by Returned Quantity")
    if not df_product_returns_sorted_qty.empty:
        st.dataframe(df_product_returns_sorted_qty.head(10).reset_index(drop=True).style.format({
            'total_returned_quantity': '{:,.0f}',
            'total_sold_quantity': '{:,.0f}',
            'estimated_returned_value': '₹{:,.2f}',
            'return_rate_percentage': '{:.2f}%'
        }), use_container_width=True)

        # --- USING plot_bar_chart HERE ---
        fig_returns_by_product_qty = plot_bar_chart(
            df_product_returns_sorted_qty.head(10),
            x_col='product_name',
            y_col='total_returned_quantity',
            title='Top 10 Products by Returned Quantity',
            x_axis_title='Product',
            y_axis_title='Returned Quantity',
        )
        st.plotly_chart(fig_returns_by_product_qty, use_container_width=True)
    else:
        st.info("No product return quantity data available for the selected period.")

with col_top_rate:
    st.write("Top 10 Products by Return Rate (%)")
    df_product_returns_sorted_rate_filtered = df_product_returns_sorted_rate[
        (df_product_returns_sorted_rate['total_sold_quantity'] > 0) |
        (df_product_returns_sorted_rate['total_returned_quantity'] == 0) # Include 0/0 scenarios for rate = 0
    ].copy()

    if not df_product_returns_sorted_rate_filtered.empty:
        st.dataframe(df_product_returns_sorted_rate_filtered.head(10).reset_index(drop=True).style.format({
            'total_returned_quantity': '{:,.0f}',
            'total_sold_quantity': '{:,.0f}',
            'estimated_returned_value': '₹{:,.2f}',
            'return_rate_percentage': '{:.2f}%'
        }), use_container_width=True)

        # --- USING plot_bar_chart HERE ---
        fig_returns_by_product_rate = plot_bar_chart(
            df_product_returns_sorted_rate_filtered.head(10),
            x_col='product_name',
            y_col='return_rate_percentage',
            title='Top 10 Products by Return Rate (%)',
            x_axis_title='Product',
            y_axis_title='Return Rate (%)',
        )
        st.plotly_chart(fig_returns_by_product_rate, use_container_width=True)
    else:
        st.info("No product return rate data available for the selected period (or no products sold).")

st.markdown("---")

st.header("Return Trends Over Time")
df_daily_returns = df_combined.groupby('date').agg(
    total_returned_quantity=('total_returned_quantity', 'sum'),
    total_sold_quantity=('total_sold_quantity', 'sum'),
    estimated_returned_value=('estimated_returned_value', 'sum')
).reset_index()

df_daily_returns['return_rate_percentage'] = df_daily_returns.apply(
    lambda row: (row['total_returned_quantity'] / row['total_sold_quantity']) * 100
    if row['total_sold_quantity'] > 0 else 0,
    axis=1
)

if not df_daily_returns.empty:
    # --- USING plot_time_series HERE ---
    fig_daily_returns = plot_time_series(
        df_daily_returns,
        x_col='date',
        y_col='total_returned_quantity',
        title='Daily Returned Quantity Over Time',
        y_axis_title='Returned Quantity'
        # hover_data is handled within plot_time_series if you add it there
    )
    st.plotly_chart(fig_daily_returns, use_container_width=True)

    # --- USING plot_time_series HERE ---
    fig_daily_return_rate = plot_time_series(
        df_daily_returns,
        x_col='date',
        y_col='return_rate_percentage',
        title='Daily Return Rate Over Time',
        y_axis_title='Return Rate (%)'
        # hover_data is handled within plot_time_series if you add it there
    )
    st.plotly_chart(fig_daily_return_rate, use_container_width=True)
else:
    st.info("No daily return data available for the selected period.")

st.markdown("---")

st.header("Return Comments Analysis")
if 'return_comments' in df_returns_filtered.columns and not df_returns_filtered.empty:

    comments_series = df_returns_filtered['return_comments'].dropna().astype(str)

    if not comments_series.empty:
        cleaned_comments = comments_series.str.lower()

        cleaned_comments = cleaned_comments.str.replace(r'\s*[/,]\s*', '-', regex=True)

        cleaned_comments = cleaned_comments.str.replace(r'\s+', '-', regex=True)

        cleaned_comments = cleaned_comments.str.strip('- ').str.strip()

        all_comments = cleaned_comments.tolist()

        if all_comments: # Check if the list is not empty after cleaning
            comment_counts = pd.Series(all_comments).value_counts().reset_index()
            comment_counts.columns = ['Comment', 'Count']

            st.write("Common reasons for returns:") # Updated title
            st.dataframe(comment_counts.head(10).reset_index(drop=True), use_container_width=True)

            # --- USING plot_bar_chart HERE ---
            fig_comments = plot_bar_chart(
                comment_counts.head(10),
                x_col='Comment',
                y_col='Count',
                title='Top 10 Return Comments', # Updated title
                x_axis_title='Reason for Return',
                y_axis_title='Number of Returns',
            )
            st.plotly_chart(fig_comments, use_container_width=True)
        else:
            st.info("No return comments available for analysis in the selected period after filtering and standardization.")
    else:
        st.info("No return comments available for analysis in the selected period.")
else:
    st.info("The 'Comments' column (`return_comments`) is not available in the returned products data or no data found.")
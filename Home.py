import streamlit as st
import pandas as pd
from utils.data_loader import load_ecommerce_data, get_filtered_data, load_customer_data
from utils.kpi_calculations import calculate_sales_kpis, get_daily_revenue_trend, format_kpi_number
from datetime import date # Import date for date inputs

st.set_page_config(
    layout="wide",
    page_title="E-commerce Dashboard",
    page_icon=":material/rocket_launch:",
    initial_sidebar_state="expanded"
)

css_file_path = "styles.css"

try:
    with open(css_file_path) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except FileNotFoundError:
    st.error(f"Could not find {css_file_path}.")

st.title(":blue[Welcome to Your E-commerce Dashboard :material/rocket_launch:]")

st.write("""
This dashboard provides a comprehensive view of your e-commerce business by unifying data from your Shopify store (soon, payment & delivery partners).
\nwe bring you real-time insights to help you make data-driven decisions.
""")

st.write("##### WHAT YOU WILL FIND HERE:")
st.markdown("""
- **:blue[:material/finance:] Sales Overview:** Key performance indicators, trends and breakdowns of your sales.
- **:blue[:material/groups:] Customer Insights:** Understand your customer base, their behaviors and value segments.
- **:blue[:material/monitoring:] Customer RFM Analysis:** Segment your customers based on Recency, Frequency and Monetary value.
- **:green[:material/yard:] Product Performance:** Analyze your product catalog, best-sellers, and inventory.
- **:red[:material/trending_down:] Product Return Analysis:** Insights into product returns to identify potential issues.
- **🗺️ Geospatial Analysis:** Visualize where your sales are coming from.
""")

st.info("Data is automatically refreshed from BigQuery every hour.")

st.markdown("---")

st.write("#### GET STARTED")
st.write("Navigate through the pages using the sidebar on the left to explore different aspects of your business.")

# --- Corrected Data Loading and KPI Calculation with Date Filter ---

df_orders = load_ecommerce_data()
df_customers = load_customer_data()

# Define the start date for the KPIs on the Home page
start_date_for_kpis = date(2025, 7, 13)
end_date_for_kpis = date.today() 

# Initialize filtered dataframes
df_orders_filtered_for_kpis = pd.DataFrame()
df_customers_filtered_for_kpis = pd.DataFrame()

if not df_orders.empty:
    # Ensure 'order_date' is datetime for filtering
    if 'order_date' in df_orders.columns:
        df_orders['order_date'] = pd.to_datetime(df_orders['order_date'], errors='coerce')
        df_orders.dropna(subset=['order_date'], inplace=True)
        # Apply the date filter using get_filtered_data
        df_orders_filtered_for_kpis = get_filtered_data(df_orders, start_date_for_kpis, end_date_for_kpis)
    else:
        st.error("Missing 'order_date' column in e-commerce data. KPIs may be inaccurate.")
        # Fallback to unfiltered if date column is missing
        df_orders_filtered_for_kpis = df_orders.copy()

if not df_customers.empty and 'customer_id' in df_customers.columns:
    # If customer data has a 'creation_date' or 'first_order_date', you could filter by that.
    # For simplicity, assuming customers are related to orders within the filtered period.
    # We will filter customers based on if they have an order in the filtered period.
    if not df_orders_filtered_for_kpis.empty:
        customers_in_filtered_orders = df_orders_filtered_for_kpis['customer_id'].unique()
        df_customers_filtered_for_kpis = df_customers[
            df_customers['customer_id'].isin(customers_in_filtered_orders)
        ].copy()
    else:
        df_customers_filtered_for_kpis = pd.DataFrame() # No orders means no customers for this period

# --- KPI Calculation using filtered data ---
if not df_orders_filtered_for_kpis.empty or not df_customers_filtered_for_kpis.empty:
    st.write("**KPI Summary (From July 13, 2025)**") # Updated title to reflect the date range

    total_revenue_glance = df_orders_filtered_for_kpis.drop_duplicates(subset=['order_id'])['total_order_value'].sum() if not df_orders_filtered_for_kpis.empty else 0

    total_orders_glance = df_orders_filtered_for_kpis['order_id'].nunique() if not df_orders_filtered_for_kpis.empty else 0

    total_customers_glance = df_customers_filtered_for_kpis['customer_id'].nunique() if not df_customers_filtered_for_kpis.empty else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Revenue", f"₹ {format_kpi_number(total_revenue_glance)}")
    col2.metric("Total Orders", f"{format_kpi_number(total_orders_glance)}")
    col3.metric("Total Customers", f"{format_kpi_number(total_customers_glance)}")
else:
    st.warning(f"No data available for the period starting {start_date_for_kpis.strftime('%Y-%m-%d')}. Please check BigQuery connection details and your GCP authentication.")
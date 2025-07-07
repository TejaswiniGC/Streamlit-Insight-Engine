import streamlit as st
import pandas as pd
from utils.data_loader import load_ecommerce_data, get_filtered_data, load_customer_data
from utils.kpi_calculations import calculate_sales_kpis, get_daily_revenue_trend, format_kpi_number

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

st.title(":material/rocket_launch: Welcome to Your E-commerce Dashboard!")

st.write("""
This dashboard provides a comprehensive view of your e-commerce business by unifying data from your Shopify store (and soon, payment and delivery partners!).
\nwe bring you real-time insights to help you make data-driven decisions.
""")

st.subheader("What you'll find here:")
st.markdown("""
- **📊 Sales Overview:** Key performance indicators, trends and breakdowns of your sales.
- **👥 Customer Insights:** Understand your customer base, their behaviors and value segments.
- **📈 Customer RFM Analysis:** Segment your customers based on Recency, Frequency and Monetary value.
- **📦 Product Performance:** Analyze your product catalog, best-sellers, and inventory.
- **📉 Product Return Analysis:** Insights into product returns to identify potential issues.
- **🗺️ Geospatial Analysis:** Visualize where your sales are coming from.
""")

st.info("Data is automatically refreshed from BigQuery every hour.")

st.markdown("---")

st.subheader("Get Started")
st.write("Navigate through the pages using the sidebar on the left to explore different aspects of your business.")

# --- Corrected Data Loading and KPI Calculation ---

df_orders = load_ecommerce_data() 
df_customers = load_customer_data() 

if not df_orders.empty or not df_customers.empty: 
    st.subheader("Overall Data Summary")
    
    total_revenue_glance = df_orders.drop_duplicates(subset=['order_id'])['total_order_value'].sum() if not df_orders.empty else 0

    total_orders_glance = df_orders['order_id'].nunique() if not df_orders.empty else 0

    total_customers_glance = df_customers['customer_id'].nunique() if not df_customers.empty and 'customer_id' in df_customers.columns else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Revenue (All Time)", f"₹ {format_kpi_number(total_revenue_glance)}")
    col2.metric("Total Orders (All Time)", f"{format_kpi_number(total_orders_glance)}")
    col3.metric("Total Customers (All Time)", f"{format_kpi_number(total_customers_glance)}")
else:
    st.warning("No data loaded. Please check BigQuery connection details and your GCP authentication for both order and customer data.")
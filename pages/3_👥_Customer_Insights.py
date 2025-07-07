import streamlit as st
import pandas as pd
from utils.data_loader import load_ecommerce_data, load_customer_data, get_filtered_data
from utils.plot_utils import plot_bar_chart, plot_time_series
from utils.kpi_calculations import format_kpi_number
import plotly.express as px

st.set_page_config(layout="wide", page_title="Customer Insights", page_icon="👥")

css_file_path = "styles.css" 

# Check if the file exists before trying to read it
try:
    with open(css_file_path) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except FileNotFoundError:
    st.error(f"Could not find {css_file_path}.")

st.title("👥 Customer Insights")

st.markdown("""
Explore customer demographics, acquisition trends, and lifetime value.
This page uses the complete customer master data for accurate lifetime metrics and imputes customer type.
""")

# Load both datasets
df_orders = load_ecommerce_data() # This is your merged_orderdata
df_customers_master = load_customer_data() # This is complete customer table

# --- Sidebar Filters ---
st.sidebar.header("Filter Data")

# Date filter primarily for order-related metrics or customer signups within a period
df_filtered_orders = pd.DataFrame()
df_filtered_customers_by_signup = pd.DataFrame() 

if not df_customers_master.empty and 'signup_date' in df_customers_master.columns:
    valid_signup_dates = df_customers_master['signup_date'].dropna()
    if not valid_signup_dates.empty:
        min_date_available_customers = valid_signup_dates.min().date()
        max_date_available_customers = valid_signup_dates.max().date()
    else:
        min_date_available_customers = pd.Timestamp.now().date() - pd.Timedelta(days=365)
        max_date_available_customers = pd.Timestamp.now().date()
else:
    if not df_orders.empty and 'order_date' in df_orders.columns:
        valid_order_dates = df_orders['order_date'].dropna()
        if not valid_order_dates.empty:
            min_date_available_customers = valid_order_dates.min().date()
            max_date_available_customers = valid_order_dates.max().date()
        else:
            min_date_available_customers = pd.Timestamp.now().date() - pd.Timedelta(days=365)
            max_date_available_customers = pd.Timestamp.now().date()
    else:
        min_date_available_customers = pd.Timestamp.now().date() - pd.Timedelta(days=365)
        max_date_available_customers = pd.Timestamp.now().date()


date_range = st.sidebar.date_input(
    "Select Customer Signup Date Range", 
    value=(min_date_available_customers, max_date_available_customers),
    min_value=min_date_available_customers,
    max_value=max_date_available_customers
)

start_date, end_date = min_date_available_customers, max_date_available_customers 
if len(date_range) == 2:
    start_date, end_date = date_range
    if start_date > end_date:
        st.sidebar.error("Error: Start date cannot be after end date.")
        # Revert to default full range if error
        start_date, end_date = min_date_available_customers, max_date_available_customers
        st.info("Displaying data from **all available customer signup dates** due to invalid date range selection.")
    else:
        st.info(f"Customer signups filtered from **{start_date.strftime('%Y-%m-%d')}** to **{end_date.strftime('%Y-%m-%d')}**")
else:
    st.warning("Please select both a start and end date for filtering. Displaying data from **all available customer signup dates**.")


# Initial filtering of customers by signup date
if not df_customers_master.empty and 'signup_date' in df_customers_master.columns:
    df_filtered_customers_by_signup = df_customers_master[
        (df_customers_master['signup_date'].dt.date >= start_date) & 
        (df_customers_master['signup_date'].dt.date <= end_date)
    ].copy()
else:
    st.warning("Customer master data or 'signup_date' column missing for filtering customer acquisitions.")
    df_filtered_customers_by_signup = pd.DataFrame()


# Filter df_orders based on the customer IDs present in df_filtered_customers_by_signup
if not df_filtered_customers_by_signup.empty and not df_orders.empty:
    customer_ids_in_filtered_customers = df_filtered_customers_by_signup['customer_id'].unique()
    df_filtered_orders = df_orders[df_orders['customer_id'].isin(customer_ids_in_filtered_customers)].copy()
else:
    df_filtered_orders = pd.DataFrame() 


# Imputed Customer Type filter (based on orders_count in master customer data)
selected_imputed_type = 'All' 
if 'imputed_customer_type' in df_filtered_customers_by_signup.columns and not df_filtered_customers_by_signup['imputed_customer_type'].dropna().empty:
    unique_imputed_types = ['All'] + sorted(df_filtered_customers_by_signup['imputed_customer_type'].dropna().unique().tolist())
    selected_imputed_type = st.sidebar.selectbox("Filter by Customer Type (Imputed)", unique_imputed_types)
    if selected_imputed_type != 'All':
        df_filtered_customers_by_signup = df_filtered_customers_by_signup[df_filtered_customers_by_signup['imputed_customer_type'] == selected_imputed_type]
        # Re-filter orders based on the new set of customer IDs
        if 'customer_id' in df_filtered_orders.columns:
            filtered_customer_ids = df_filtered_customers_by_signup['customer_id'].unique()
            df_filtered_orders = df_filtered_orders[df_filtered_orders['customer_id'].isin(filtered_customer_ids)]


# Regional Filters for Customers (DIRECTLY from df_customers_master 'state' and 'city' columns)
selected_state_customer = 'All' 
if 'state' in df_customers_master.columns and not df_customers_master['state'].dropna().empty:
    unique_states_customers = ['All'] + sorted(df_filtered_customers_by_signup['state'].dropna().unique().tolist())
    selected_state_customer = st.sidebar.selectbox("Filter Customers by State (Registered)", unique_states_customers)
    if selected_state_customer != 'All':
        df_filtered_customers_by_signup = df_filtered_customers_by_signup[df_filtered_customers_by_signup['state'] == selected_state_customer]
        # Re-filter orders based on the new set of customer IDs
        if 'customer_id' in df_filtered_orders.columns:
            filtered_customer_ids = df_filtered_customers_by_signup['customer_id'].unique()
            df_filtered_orders = df_filtered_orders[df_filtered_orders['customer_id'].isin(filtered_customer_ids)]

selected_city_customer = 'All' # Default value
if 'city' in df_customers_master.columns and not df_customers_master['city'].dropna().empty:
    # Filter cities based on selected state for customers
    current_cities_customers = df_filtered_customers_by_signup['city'].dropna().unique().tolist()
    unique_cities_customers = ['All'] + sorted(current_cities_customers)
    selected_city_customer = st.sidebar.selectbox("Filter Customers by City (Registered)", unique_cities_customers)
    if selected_city_customer != 'All':
        df_filtered_customers_by_signup = df_filtered_customers_by_signup[df_filtered_customers_by_signup['city'] == selected_city_customer]
        # Re-filter orders based on the new set of customer IDs
        if 'customer_id' in df_filtered_orders.columns:
            filtered_customer_ids = df_filtered_customers_by_signup['customer_id'].unique()
            df_filtered_orders = df_filtered_orders[df_filtered_orders['customer_id'].isin(filtered_customer_ids)]


# --- Main Content Area ---
if df_filtered_orders.empty and df_filtered_customers_by_signup.empty:
    st.warning("No data available for the selected filters. Please adjust your date range or other filters.")
else:
    # --- Customer KPIs ---
    st.subheader("Customer Key Performance Indicators (Lifetime)")
    
    total_customers = df_filtered_customers_by_signup['customer_id'].nunique() if 'customer_id' in df_filtered_customers_by_signup.columns else 0
    total_lifetime_spent = df_filtered_customers_by_signup['total_spent'].sum() if 'total_spent' in df_filtered_customers_by_signup.columns else 0
    
    avg_lifetime_orders = df_filtered_customers_by_signup['orders_count'].mean() if 'orders_count' in df_filtered_customers_by_signup.columns else 0
    avg_lifetime_aov = df_filtered_customers_by_signup['aov'].mean() if 'aov' in df_filtered_customers_by_signup.columns else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Active Customers (filtered by signup)", f"{format_kpi_number(int(total_customers))}")
    col2.metric("Total Lifetime Revenue (filtered by signup)", f"₹ {format_kpi_number(total_lifetime_spent)}")
    col3.metric("Avg. Lifetime Orders per Customer", f"{format_kpi_number(avg_lifetime_orders)}")
    col4.metric("Avg. Lifetime AOV per Customer", f"₹ {format_kpi_number(avg_lifetime_aov)}")

    st.markdown("---")

    # --- Customer Acquisition Trend ---
    st.subheader("Customer Acquisition Trend")
    if 'signup_date' in df_customers_master.columns and not df_customers_master.empty:
        daily_signups_trend_data = df_customers_master.copy()
        daily_signups_trend_data = daily_signups_trend_data[
            (daily_signups_trend_data['signup_date'].dt.date >= start_date) & 
            (daily_signups_trend_data['signup_date'].dt.date <= end_date)
        ]
        # Apply ALL existing filters to the trend data for consistency
        if 'imputed_customer_type' in daily_signups_trend_data.columns and selected_imputed_type != 'All':
             daily_signups_trend_data = daily_signups_trend_data[daily_signups_trend_data['imputed_customer_type'] == selected_imputed_type]
        if 'state' in daily_signups_trend_data.columns and selected_state_customer != 'All':
            daily_signups_trend_data = daily_signups_trend_data[daily_signups_trend_data['state'] == selected_state_customer]
        if 'city' in daily_signups_trend_data.columns and selected_city_customer != 'All':
            daily_signups_trend_data = daily_signups_trend_data[daily_signups_trend_data['city'] == selected_city_customer]


        if not daily_signups_trend_data.empty:
            signup_trend = daily_signups_trend_data.groupby(daily_signups_trend_data['signup_date'].dt.date)['customer_id'].nunique().reset_index()
            signup_trend.columns = ['Date', 'New Customers']
            signup_trend['Date'] = pd.to_datetime(signup_trend['Date'])
            signup_trend = signup_trend.sort_values('Date')

            if not signup_trend.empty:
                fig_signup_trend = plot_time_series(signup_trend, 'Date', 'New Customers', 'Daily Customer Signups', 'Number of New Customers')
                st.plotly_chart(fig_signup_trend, use_container_width=True)
            else:
                st.info("No new customer signups in the selected date range and applied filters.")
        else:
            st.info("No customer signup data available in the selected date range for the trend or filters.")
    else:
        st.warning("Signup date column not found in customer master data.")

    st.markdown("---")

    # --- Customer Type Distribution (Imputed from Master Data) ---
    st.subheader("Customer Type Distribution (Imputed)")
    if 'imputed_customer_type' in df_filtered_customers_by_signup.columns and not df_filtered_customers_by_signup['imputed_customer_type'].dropna().empty:
        imputed_customer_type_dist = df_filtered_customers_by_signup['imputed_customer_type'].value_counts().reset_index()
        imputed_customer_type_dist.columns = ['Imputed Customer Type', 'Count']
        
        fig_imputed_customer_type = px.pie(imputed_customer_type_dist, 
                                   values='Count', 
                                   names='Imputed Customer Type', 
                                   title='Customer Distribution by Imputed Type',
                                   hole=0.4)
        fig_imputed_customer_type.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig_imputed_customer_type, use_container_width=True)
    else:
        st.info("Imputed customer type data not available or empty for customer demographics.")
    
    st.markdown("---")

    # --- Customers by State (Using df_filtered_customers_by_signup's 'state' column) ---
    st.subheader("Customers by State (Registered Address)")
    if 'state' in df_filtered_customers_by_signup.columns and not df_filtered_customers_by_signup['state'].dropna().empty:
        customers_by_state = df_filtered_customers_by_signup.groupby('state')['customer_id'].nunique().nlargest(10).reset_index()
        customers_by_state.columns = ['State', 'Number of Customers']
        if not customers_by_state.empty:
            fig_cust_state = plot_bar_chart(customers_by_state, 'State', 'Number of Customers', 'Top 10 Customers by State (Registered Address)', 'State', 'Number of Customers')
            st.plotly_chart(fig_cust_state, use_container_width=True)
        else:
            st.info("No customer data available for states with current filters.")
    else:
        st.warning("State column not found in customer master data or no data available for analysis with current filters.")

    st.markdown("---")

    # --- Customers by City (Using df_filtered_customers_by_signup's 'city' column) ---
    st.subheader("Customers by City (Registered Address)")
    if 'city' in df_filtered_customers_by_signup.columns and not df_filtered_customers_by_signup['city'].dropna().empty:
        customers_by_city = df_filtered_customers_by_signup.groupby('city')['customer_id'].nunique().nlargest(10).reset_index()
        customers_by_city.columns = ['City', 'Number of Customers']
        if not customers_by_city.empty:
            fig_cust_city = plot_bar_chart(customers_by_city, 'City', 'Number of Customers', 'Top 10 Customers by City (Registered Address)', 'City', 'Number of Customers')
            st.plotly_chart(fig_cust_city, use_container_width=True)
        else:
            st.info("No customer data available for cities with current filters.")
    else:
        st.warning("City column not found in customer master data or no data available for analysis with current filters.")

    st.markdown("---")


    # --- Top Customers by Lifetime Value ---
    st.subheader("Top Customers by Lifetime Value")
    # Ensure using unfiltered master customer data for overall top customers
    if all(col in df_customers_master.columns for col in ['customer_id', 'total_spent', 'orders_count', 'aov']):
        top_customers = df_customers_master.nlargest(10, 'total_spent')[['customer_id', 'total_spent', 'orders_count', 'aov']].copy()
        st.write("These are the top customers based on their *total lifetime spending* across all available master data.")
        st.dataframe(top_customers.set_index('customer_id'), use_container_width=True)
    else:
        st.warning("Customer ID, total_spent, orders_count, or aov columns missing for Top Customers analysis.")
        
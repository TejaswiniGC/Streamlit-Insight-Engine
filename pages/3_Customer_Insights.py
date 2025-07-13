import streamlit as st
import pandas as pd
from utils.data_loader import load_ecommerce_data, load_customer_data, get_filtered_data
from utils.plot_utils import plot_bar_chart, plot_time_series
from utils.kpi_calculations import format_kpi_number
import plotly.express as px

st.set_page_config(layout="wide", page_title="Customer Insights", page_icon=":material/groups:")

css_file_path = "styles.css"

# Check if the file exists before trying to read it
try:
    with open(css_file_path) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except FileNotFoundError:
    st.error(f"Could not find {css_file_path}.")

st.header(":blue[:material/groups: Customer Insights]")

st.markdown("""
Explore customer demographics, acquisition trends, and lifetime value.
This page uses the complete customer master data for accurate lifetime metrics and imputes customer type.
""")

# Load both datasets
df_orders = load_ecommerce_data() # This is your merged_orderdata
df_customers_master = load_customer_data() # This is complete customer table

# Ensure 'signup_date' is datetime in df_customers_master if it exists
if not df_customers_master.empty and 'signup_date' in df_customers_master.columns:
    df_customers_master['signup_date'] = pd.to_datetime(df_customers_master['signup_date'], errors='coerce')
    df_customers_master.dropna(subset=['signup_date'], inplace=True) # Remove rows with invalid signup dates

# Ensure 'order_date' is datetime in df_orders if it exists
if not df_orders.empty and 'order_date' in df_orders.columns:
    df_orders['order_date'] = pd.to_datetime(df_orders['order_date'], errors='coerce')
    df_orders.dropna(subset=['order_date'], inplace=True) # Remove rows with invalid order dates


# --- Sidebar Filters ---
st.sidebar.header(":blue[:material/groups: Apply Filters]")

# Determine available min/max dates for the signup date filter
min_date_available_customers = pd.Timestamp.now().date() - pd.Timedelta(days=365) # Default if no data
max_date_available_customers = pd.Timestamp.now().date() # Default if no data

if not df_customers_master.empty and 'signup_date' in df_customers_master.columns and not df_customers_master['signup_date'].dropna().empty:
    valid_signup_dates = df_customers_master['signup_date'].dropna()
    if not valid_signup_dates.empty:
        min_date_available_customers = valid_signup_dates.min().date()
        max_date_available_customers = valid_signup_dates.max().date()
elif not df_orders.empty and 'order_date' in df_orders.columns and not df_orders['order_date'].dropna().empty:
    # Fallback to order dates if signup dates are not available
    valid_order_dates = df_orders['order_date'].dropna()
    if not valid_order_dates.empty:
        min_date_available_customers = valid_order_dates.min().date()
        max_date_available_customers = valid_order_dates.max().date()


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
        start_date, end_date = min_date_available_customers, max_date_available_customers # Revert
        st.info("Displaying data from **all available customer signup dates** due to invalid date range selection.")
    else:
        st.info(f"Customer signups filtered from **{start_date.strftime('%Y-%m-%d')}** to **{end_date.strftime('%Y-%m-%d')}**")
else:
    st.warning("Please select both a start and end date for filtering. Displaying data from **all available customer signup dates**.")


# Initial filtering of customers by signup date
df_filtered_customers_by_signup = pd.DataFrame()
if not df_customers_master.empty and 'signup_date' in df_customers_master.columns:
    df_filtered_customers_by_signup = df_customers_master[
        (df_customers_master['signup_date'].dt.date >= start_date) &
        (df_customers_master['signup_date'].dt.date <= end_date)
    ].copy()
else:
    st.warning("Customer master data or 'signup_date' column missing for filtering customer acquisitions. Displaying all customers.")
    df_filtered_customers_by_signup = df_customers_master.copy() # Use all customers if signup_date is an issue


# Filter df_orders based on the customer IDs present in df_filtered_customers_by_signup
df_filtered_orders = pd.DataFrame()
if not df_filtered_customers_by_signup.empty and not df_orders.empty:
    customer_ids_in_filtered_customers = df_filtered_customers_by_signup['customer_id'].unique()
    df_filtered_orders = df_orders[df_orders['customer_id'].isin(customer_ids_in_filtered_customers)].copy()
else:
    df_filtered_orders = pd.DataFrame()


# Imputed Customer Type filter
selected_imputed_type = 'All'
if 'imputed_customer_type' in df_filtered_customers_by_signup.columns and not df_filtered_customers_by_signup['imputed_customer_type'].dropna().empty:
    unique_imputed_types = ['All'] + sorted(df_filtered_customers_by_signup['imputed_customer_type'].dropna().unique().tolist())
    selected_imputed_type = st.sidebar.selectbox("Filter by Customer Type", unique_imputed_types)
    if selected_imputed_type != 'All':
        df_filtered_customers_by_signup = df_filtered_customers_by_signup[df_filtered_customers_by_signup['imputed_customer_type'] == selected_imputed_type]
        if 'customer_id' in df_filtered_orders.columns: # Re-filter orders
            filtered_customer_ids = df_filtered_customers_by_signup['customer_id'].unique()
            df_filtered_orders = df_filtered_orders[df_filtered_orders['customer_id'].isin(filtered_customer_ids)]


# Regional Filters for Customers
selected_state_customer = 'All'
if 'state' in df_filtered_customers_by_signup.columns and not df_filtered_customers_by_signup['state'].dropna().empty:
    unique_states_customers = ['All'] + sorted(df_filtered_customers_by_signup['state'].dropna().unique().tolist())
    selected_state_customer = st.sidebar.selectbox("Filter Customers by State", unique_states_customers)
    if selected_state_customer != 'All':
        df_filtered_customers_by_signup = df_filtered_customers_by_signup[df_filtered_customers_by_signup['state'] == selected_state_customer]
        if 'customer_id' in df_filtered_orders.columns: # Re-filter orders
            filtered_customer_ids = df_filtered_customers_by_signup['customer_id'].unique()
            df_filtered_orders = df_filtered_orders[df_filtered_orders['customer_id'].isin(filtered_customer_ids)]

selected_city_customer = 'All'
if 'city' in df_filtered_customers_by_signup.columns and not df_filtered_customers_by_signup['city'].dropna().empty:
    current_cities_customers = df_filtered_customers_by_signup['city'].dropna().unique().tolist()
    unique_cities_customers = ['All'] + sorted(current_cities_customers)
    selected_city_customer = st.sidebar.selectbox("Filter Customers by City", unique_cities_customers)
    if selected_city_customer != 'All':
        df_filtered_customers_by_signup = df_filtered_customers_by_signup[df_filtered_customers_by_signup['city'] == selected_city_customer]
        if 'customer_id' in df_filtered_orders.columns: # Re-filter orders
            filtered_customer_ids = df_filtered_customers_by_signup['customer_id'].unique()
            df_filtered_orders = df_filtered_orders[df_filtered_orders['customer_id'].isin(filtered_customer_ids)]


# --- Main Content Area ---
if df_filtered_orders.empty and df_filtered_customers_by_signup.empty:
    st.warning("No data available for the selected filters. Please adjust your date range or other filters.")
else:
    # --- Customer KPIs ---
    st.write("**Customer Key Performance Indicators (Lifetime)**")

    total_customers = df_filtered_customers_by_signup['customer_id'].nunique() if 'customer_id' in df_filtered_customers_by_signup.columns else 0
    total_lifetime_spent = df_filtered_customers_by_signup['total_spent'].sum() if 'total_spent' in df_filtered_customers_by_signup.columns else 0

    avg_lifetime_orders = df_filtered_customers_by_signup['orders_count'].mean() if 'orders_count' in df_filtered_customers_by_signup.columns else 0
    avg_lifetime_aov = df_filtered_customers_by_signup['aov'].mean() if 'aov' in df_filtered_customers_by_signup.columns else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Active Customers", f"{format_kpi_number(int(total_customers))}")
    col2.metric("Total Revenue", f"₹ {format_kpi_number(total_lifetime_spent)}")
    col3.metric("Avg. Orders/Customer", f"{format_kpi_number(avg_lifetime_orders)}")
    col4.metric("AOV/Customer", f"₹ {format_kpi_number(avg_lifetime_aov)}")

    st.markdown("---")

    # --- Customer Acquisition Trend ---
    st.write("#### Customer Acquisition Trend")
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
    st.write("#### Customer Type Distribution")
    if 'imputed_customer_type' in df_filtered_customers_by_signup.columns and not df_filtered_customers_by_signup['imputed_customer_type'].dropna().empty:
        imputed_customer_type_dist = df_filtered_customers_by_signup['imputed_customer_type'].value_counts().reset_index()
        imputed_customer_type_dist.columns = ['Imputed Customer Type', 'Count']

        fig_imputed_customer_type = px.pie(imputed_customer_type_dist,
                                   values='Count',
                                   names='Imputed Customer Type',
                                   title='Customer Distribution',
                                   hole=0.4)
        fig_imputed_customer_type.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig_imputed_customer_type, use_container_width=True)
    else:
        st.info("Imputed customer type data not available or empty for customer demographics.")

    st.markdown("---")

    # --- Customer Return Behavior (Order Count Distribution) ---
    #st.write("#### Customer Return Behavior: Orders per Customer")
    if 'orders_count' in df_filtered_customers_by_signup.columns and not df_filtered_customers_by_signup['orders_count'].dropna().empty:
        order_count_distribution = df_filtered_customers_by_signup['orders_count'].value_counts().sort_index().reset_index()
        order_count_distribution.columns = ['Number of Orders', 'Number of Customers']

        order_count_distribution['Order Group'] = order_count_distribution['Number of Orders'].apply(
            lambda x: '1 (First-time Buyer)' if x == 1
            else ('2 (Second-time Buyer)' if x == 2
            else f'3+ (Repeat Buyer)') # Group all orders >=3
        )

        # Aggregate the grouped data
        grouped_order_count_dist = order_count_distribution.groupby('Order Group')['Number of Customers'].sum().reset_index()

        # Define a specific order for the groups to ensure '1', '2', '3+' appears correctly
        order_categories = ['1 (First-time Buyer)', '2 (Second-time Buyer)', '3+ (Repeat Buyer)']
        grouped_order_count_dist['Order Group'] = pd.Categorical(grouped_order_count_dist['Order Group'], categories=order_categories, ordered=True)
        grouped_order_count_dist = grouped_order_count_dist.sort_values('Order Group')
        grouped_order_count_dist['Formatted_Customers'] = grouped_order_count_dist['Number of Customers'].apply(format_kpi_number)

        if not grouped_order_count_dist.empty:
            fig_return_behavior = px.bar(
                grouped_order_count_dist,
                x='Order Group',
                y='Number of Customers',
                title='Customer Return Behavior',
                labels={'Order Group': 'Number of Orders Made', 'Number of Customers': 'Count of Customers'},
                color='Number of Customers', 
                text='Formatted_Customers' 
            )
            fig_return_behavior.update_traces(texttemplate='%{text}', textposition='outside')
            fig_return_behavior.update_layout(uniformtext_minsize=8, uniformtext_mode='hide', 
                                              coloraxis_showscale=False,
                                              yaxis=dict(range=[0, grouped_order_count_dist['Number of Customers'].max() * 1.1])) 
            st.plotly_chart(fig_return_behavior, use_container_width=True)
        else:
            st.info("No order count data available for customer return behavior analysis.")
    else:
        st.warning("Orders count column ('orders_count') not found in customer master data or no data available for analysis.")

    st.markdown("---")

    # --- Customers by State ---
    if 'state' in df_filtered_customers_by_signup.columns and not df_filtered_customers_by_signup['state'].dropna().empty:
        customers_by_state = df_filtered_customers_by_signup.groupby('state')['customer_id'].nunique().nlargest(10).reset_index()
        customers_by_state.columns = ['State', 'Number of Customers']
        if not customers_by_state.empty:
            fig_cust_state = plot_bar_chart(customers_by_state, 'State', 'Number of Customers', 'Top 10 Customers base by State', 'State', 'Number of Customers')
            st.plotly_chart(fig_cust_state, use_container_width=True)
        else:
            st.info("No customer data available for states with current filters.")
    else:
        st.warning("State column not found in customer master data or no data available for analysis with current filters.")

    st.markdown("---")

    # --- Customers by City ---
    if 'city' in df_filtered_customers_by_signup.columns and not df_filtered_customers_by_signup['city'].dropna().empty:
        customers_by_city = df_filtered_customers_by_signup.groupby('city')['customer_id'].nunique().nlargest(10).reset_index()
        customers_by_city.columns = ['City', 'Number of Customers']
        if not customers_by_city.empty:
            fig_cust_city = plot_bar_chart(customers_by_city, 'City', 'Number of Customers', 'Top 10 Customers base by City', 'City', 'Number of Customers')
            st.plotly_chart(fig_cust_city, use_container_width=True)
        else:
            st.info("No customer data available for cities with current filters.")
    else:
        st.warning("City column not found in customer master data or no data available for analysis with current filters.")

    st.markdown("---")

    # --- Top Customers by Lifetime Value ---
    st.write("#### Top Customers by Lifetime Value")
    # Ensure using the *filtered* customer data for consistency with other displayed metrics on the page
    # If you truly want ALL-TIME top customers regardless of the signup date filter, revert to df_customers_master here.
    if all(col in df_filtered_customers_by_signup.columns for col in ['customer_id', 'total_spent', 'orders_count', 'aov']):
        top_customers = df_filtered_customers_by_signup.nlargest(10, 'total_spent')[['customer_id', 'total_spent', 'orders_count', 'aov']].copy()
        st.write("These are the top customers based on their *total lifetime spending* within the selected signup date range and filters.")
        st.dataframe(top_customers.set_index('customer_id').style.format({
            'total_spent': '₹ {:.2f}',
            'aov': '₹ {:.2f}'
        }), use_container_width=True)
    else:
        st.warning("Customer ID, total_spent, orders_count, or aov columns missing for Top Customers analysis.")
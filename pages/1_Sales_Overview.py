import streamlit as st
import pandas as pd
from utils.data_loader import load_ecommerce_data, get_filtered_data
from utils.kpi_calculations import calculate_sales_kpis, get_daily_revenue_trend, format_kpi_number
from utils.plot_utils import plot_time_series, plot_bar_chart # Ensure plot_utils is correct
import plotly.express as px
from datetime import date # Import date for date inputs

st.set_page_config(layout="wide", page_title="Sales Overview", page_icon=":material/finance_mode:", initial_sidebar_state="expanded")

css_file_path = "styles.css" 

# Check if the file exists before trying to read it
try:
    with open(css_file_path) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except FileNotFoundError:
    st.error(f"Could not find {css_file_path}.")

st.header(":blue[:material/finance_mode: Sales Overview]")

st.markdown("""
This section provides a high-level view of your sales performance, including key metrics, trends,
and breakdowns by various dimensions. Use the filters on the sidebar to analyze specific periods or segments.
""")

df = load_ecommerce_data()

# --- Sidebar Filters ---
st.sidebar.header(":blue[:material/finance_mode: Apply Filters]")

if not df.empty:
    # Ensure 'order_date' is datetime
    if 'order_date' in df.columns:
        df['order_date'] = pd.to_datetime(df['order_date'])
    else:
        st.error("Missing 'order_date' column in e-commerce data.")
        st.stop()

    # Determine available min/max dates
    valid_order_dates = df['order_date'].dropna()
    if not valid_order_dates.empty:
        min_date_available = date(2025, 7, 13)
        max_date_available = valid_order_dates.max().date()
    else:
        # Fallback if no valid dates are found
        min_date_available = date(2023, 1, 1) # A reasonable default if no data
        max_date_available = date.today()
    
    # Date Range Filter (single box)
    date_range = st.sidebar.date_input(
        "Order Date Range",
        value=(min_date_available, max_date_available),
        min_value=min_date_available,
        max_value=max_date_available
    )

    # Initialize df_filtered_by_date for cascading filters
    df_filtered = pd.DataFrame()
    if len(date_range) == 2:
        start_date, end_date = date_range
        if start_date > end_date:
            st.sidebar.error("Error: Start date cannot be after end date.")
            df_filtered = df.copy() # Revert to full data if invalid range
            st.info("Displaying data from **all available dates** due to invalid date range selection.")
        else:
            df_filtered = get_filtered_data(df, start_date, end_date) # Assuming get_filtered_data handles date filtering
            st.info(f"Displaying data from **{start_date.strftime('%Y-%m-%d')}** to **{end_date.strftime('%Y-%m-%d')}**")
    else:
        st.sidebar.warning("Please select both a start and end date for filtering. Displaying data from **all available dates**.")
        df_filtered = df.copy()

    # --- Apply additional filters sequentially ---

    # Product Name filter
    if 'product_name' in df_filtered.columns and not df_filtered['product_name'].dropna().empty:
        unique_products = ['All'] + sorted(df_filtered['product_name'].dropna().unique().tolist())
        selected_product = st.sidebar.selectbox("Product Name", unique_products)
        if selected_product != 'All':
            df_filtered = df_filtered[df_filtered['product_name'] == selected_product]

    # City filter
    if 'customer_city' in df_filtered.columns and not df_filtered['customer_city'].dropna().empty:
        unique_cities = ['All'] + sorted(df_filtered['customer_city'].dropna().unique().tolist())
        selected_city = st.sidebar.selectbox("City", unique_cities)
        if selected_city != 'All':
            df_filtered = df_filtered[df_filtered['customer_city'] == selected_city]

    # State filter
    if 'customer_state' in df_filtered.columns and not df_filtered['customer_state'].dropna().empty:
        unique_states = ['All'] + sorted(df_filtered['customer_state'].dropna().unique().tolist())
        selected_state = st.sidebar.selectbox("State", unique_states)
        if selected_state != 'All':
            df_filtered = df_filtered[df_filtered['customer_state'] == selected_state]

    # Order Channel filter (already existing, but placed in new sequential order)
    if 'order_channel' in df_filtered.columns and not df_filtered['order_channel'].dropna().empty:
        unique_channels = ['All'] + sorted(df_filtered['order_channel'].dropna().unique().tolist())
        selected_channel = st.sidebar.selectbox("Order Channel", unique_channels)
        if selected_channel != 'All':
            df_filtered = df_filtered[df_filtered['order_channel'] == selected_channel]
    
    # Referring Sites filter
    if 'cleaned_referring_site' in df_filtered.columns and not df_filtered['cleaned_referring_site'].dropna().empty:
        unique_referring_sites = ['All'] + sorted(df_filtered['cleaned_referring_site'].dropna().unique().tolist())
        selected_referring_site = st.sidebar.selectbox("Referring Site", unique_referring_sites)
        if selected_referring_site != 'All':
            df_filtered = df_filtered[df_filtered['cleaned_referring_site'] == selected_referring_site]

    if 'discount_applied' in df_filtered.columns and not df_filtered['discount_applied'].dropna().empty:
        unique_discount_codes = ['All'] + sorted(df_filtered['discount_applied'].dropna().unique().tolist())
        selected_discount_codes = st.sidebar.selectbox("Discount Code", unique_discount_codes)
        if selected_discount_codes != "All":
            df_filtered = df_filtered[df_filtered['discount_applied'] == selected_discount_codes]

    # --- Main Content Area ---
    if df_filtered.empty:
        st.warning("No data available for the selected filters. Please adjust your date range or other filters.")
    else:
        # --- Display KPIs ---
        st.write("**Key Performance Indicators**")
        kpis = calculate_sales_kpis(df_filtered)

        col1, col2, col3 = st.columns(3)
        col4, col5, col6 = st.columns(3) 

        with col1:
            st.metric("Total Revenue", f"₹ {format_kpi_number(kpis['total_revenue'])}")
        with col2:
            st.metric("Total Orders", f"{format_kpi_number(kpis['total_orders'])}")
        with col3:
            st.metric("Avg Order Value", f"₹ {format_kpi_number(kpis['average_order_value'])}") # Shortened label
        with col4:
            st.metric("Total Discount Amt", f"₹ {format_kpi_number(kpis['total_discount_amount'])}") # Shortened label
        with col5:
            st.metric("Total Shipping Cost", f"₹ {format_kpi_number(kpis['total_shipping_cost'])}") # Shortened label
        with col6:
            st.metric("Total Tax Amt", f"₹ {format_kpi_number(kpis['total_tax_amount'])}") # Shortened label
       

        st.markdown("---")

        # --- Revenue and Orders Trend Over Time ---
        st.write("#### Sales Trends Over Time")
        
        orders_for_trend = df_filtered.drop_duplicates(subset=['order_id']).copy()

        revenue_trend_data = orders_for_trend.groupby(orders_for_trend['order_date'].dt.date)['total_order_value'].sum().reset_index()
        revenue_trend_data.columns = ['Date', 'Revenue']
        revenue_trend_data['Date'] = pd.to_datetime(revenue_trend_data['Date'])
        revenue_trend_data = revenue_trend_data.sort_values('Date')

        orders_trend_data = orders_for_trend.groupby(orders_for_trend['order_date'].dt.date)['order_id'].nunique().reset_index()
        orders_trend_data.columns = ['Date', 'Orders']
        orders_trend_data['Date'] = pd.to_datetime(orders_trend_data['Date'])
        orders_trend_data = orders_trend_data.sort_values('Date')

        if not revenue_trend_data.empty:
            col_trend_1, col_trend_2 = st.columns(2)
            with col_trend_1:
                fig_revenue_trend = plot_time_series(revenue_trend_data, 'Date', 'Revenue', 'Daily Revenue Trend', 'Revenue (₹)')
                st.plotly_chart(fig_revenue_trend, use_container_width=True)
            with col_trend_2:
                fig_orders_trend = plot_time_series(orders_trend_data, 'Date', 'Orders', 'Daily Orders Trend', 'Number of Orders')
                st.plotly_chart(fig_orders_trend, use_container_width=True)
        else:
            st.info("Not enough data to display sales trends.")

        st.markdown("---")

        # --- Sales Breakdowns ---
        #st.subheader("Sales Breakdowns")
        
        col_breakdown1, col_breakdown2 = st.columns(2)

        # Revenue by Order Channel
        with col_breakdown1:
            if 'order_channel' in df_filtered.columns:
                channel_revenue = df_filtered.drop_duplicates(subset=['order_id']).groupby('order_channel')['total_order_value'].sum().reset_index()
                if not channel_revenue.empty:
                    fig_channel = plot_bar_chart(channel_revenue, 'order_channel', 'total_order_value', 'Revenue by Order Channel', 'Order Channel', 'Revenue (₹)')
                    st.plotly_chart(fig_channel, use_container_width=True)
                else:
                    st.info("No data for Order Channel breakdown.")
            else:
                st.warning("Column 'order_channel' not found for breakdown. Please verify its presence.")
        
        # Orders by Payment Status
        with col_breakdown2:
            if 'order_status_from_tag' in df_filtered.columns:
                fulfillment_status_sales = df_filtered.drop_duplicates(subset=['order_id']).groupby('order_status_from_tag')['total_order_value'].sum().reset_index()
                if not fulfillment_status_sales.empty:
                    fig_fulfillment = plot_bar_chart(fulfillment_status_sales, 'order_status_from_tag', 'total_order_value', 'Revenue by Order Status', 'Order Status', 'Revenue (₹)')
                    st.plotly_chart(fig_fulfillment, use_container_width=True)
                else:
                    st.info("No data for Extracted Fulfillment Status breakdown.")
            else:
                st.warning("Column 'order_status_from_tag' not found. Please check `utils/data_loader.py` for status extraction logic.")

        st.markdown("---")

        #st.write("#### Top Referring Sites by Revenue")
        if 'cleaned_referring_site' in df_filtered.columns: 
            referring_sites_data = df_filtered.drop_duplicates(subset=['order_id'])
            
            if not referring_sites_data.empty:
                # Group by the CLEANED column
                top_sites = referring_sites_data.groupby('cleaned_referring_site')['total_order_value'].sum().nlargest(10).reset_index()
                fig_referring_sites = plot_bar_chart(top_sites, 'cleaned_referring_site', 'total_order_value', 'Top 10 Referring Sites by Revenue', 'Referring Site', 'Revenue (₹)', orientation='h')
                st.plotly_chart(fig_referring_sites, use_container_width=True)
            else:
                st.info("No data for Referring Sites breakdown or all referring sites are empty/null/filtered out.")
        else:
            st.warning("Column 'cleaned_referring_site' not found. Please check `utils/data_loader.py` for referring site cleaning logic.")

        #st.write("#### Discount Codes Usage and Total Discount Amount")
        discount_data = df_filtered[
            (df_filtered['discount_applied'].notna()) &
            (df_filtered['discount_applied'] != '') &
            (df_filtered['discount_applied'].apply(lambda x: isinstance(x, str)))
        ].copy()

        if not discount_data.empty:
            # Create a unique orders dataframe to accurately sum order-level discount amounts
            # Ensure 'order_id', 'discount_applied', and 'discount_amount' are present
            unique_discount_orders = discount_data.drop_duplicates(subset=['order_id']).copy()

            # Group by discount_applied (which we're assuming is the code) and sum the discount_amount
            discount_summary = unique_discount_orders.groupby('discount_applied').agg(
                total_discount_amount=('discount_amount', 'sum'),
                number_of_uses=('order_id', 'nunique') # Count unique orders that used this discount
            ).reset_index()

            # Sort for better visualization (e.g., by total discount amount)
            discount_summary = discount_summary.sort_values('total_discount_amount', ascending=False)

            if not discount_summary.empty:
                fig_discount_codes = px.bar(
                    discount_summary.head(10), # Display top 10 as a bar chart
                    x='discount_applied',
                    y='number_of_uses',
                    color='total_discount_amount', # Color by total discount amount
                    title='Top 10 Discount Codes by Number of Orders Used',
                    labels={'discount_applied': 'Discount Code',
                            'number_of_uses': 'Number of Orders Used',
                            'total_discount_amount': 'Total Discount Amount (₹)'},
                    hover_data={
                        'discount_applied': True,
                        'number_of_uses': True,
                        'total_discount_amount': ':.2f' # Format total_discount_amount on hover
                    },
                )
                fig_discount_codes.update_layout(xaxis_title="Discount Code", yaxis_title="Number of Orders Used", coloraxis_showscale=False,)
                st.plotly_chart(fig_discount_codes, use_container_width=True)

                st.write("**All Discount Codes**")
                # Display all as a table (scrollable)
                st.dataframe(
                    discount_summary.style.format({
                        'total_discount_amount': '₹ {:.2f}'
                    }),
                    use_container_width=True,
                    height=300, # Set a fixed height to make it scrollable
                    hide_index=True
                )
            else:
                st.info("No discount code data to display for the selected filters.")
        else:
            st.info("No discount codes found or applied in the filtered data.")

else:
    st.error("Cannot load sales data. Please check the `utils/data_loader.py` file for configuration and potential BigQuery connection issues.")
    st.info("If data loading fails, the dashboard cannot display any insights. Ensure your BigQuery project, dataset, and table IDs are correct and your GCP authentication is set up via `gcloud auth application-default login`.")
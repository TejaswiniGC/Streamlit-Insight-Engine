import streamlit as st
import pandas as pd
from utils.data_loader import load_ecommerce_data, get_filtered_data 
from utils.plot_utils import plot_bar_chart, plot_time_series
from utils.kpi_calculations import format_kpi_number
import plotly.express as px

st.set_page_config(layout="wide", page_title="Product Performance", page_icon=":material/yard:")

css_file_path = "styles.css" 

# Check if the file exists before trying to read it
try:
    with open(css_file_path) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except FileNotFoundError:
    st.error(f"Could not find {css_file_path}.")

st.header(":blue[:material/yard: Product Performance Overview]")

st.markdown("""
This section provides deep insights into your product catalog's performance,
highlighting top sellers, popular categories, and stock levels.
""")

# Load the single, prepared dataframe
df = load_ecommerce_data()

# --- Sidebar Filters ---
st.sidebar.header(":blue[:material/yard: Apply Filters]")

if not df.empty:
    valid_order_dates = df['order_date'].dropna()
    if not valid_order_dates.empty:
        min_date_available = valid_order_dates.min().date()
        max_date_available = valid_order_dates.max().date()
    else:
        min_date_available = pd.Timestamp.now().date() - pd.Timedelta(days=365)
        max_date_available = pd.Timestamp.now().date()
    
    date_range = st.sidebar.date_input(
        "Select Order Date Range",
        value=(min_date_available, max_date_available),
        min_value=min_date_available,
        max_value=max_date_available
    )

    df_filtered = pd.DataFrame()

    if len(date_range) == 2:
        start_date, end_date = date_range
        if start_date > end_date:
            st.sidebar.error("Error: Start date cannot be after end date.")
            df_filtered = df.copy() 
            st.info("Displaying data from **all available dates** due to invalid date range selection.")
        else:
            df_filtered = get_filtered_data(df, start_date, end_date)
            st.info(f"Displaying data from **{start_date.strftime('%Y-%m-%d')}** to **{end_date.strftime('%Y-%m-%d')}**")
    else:
        st.warning("Please select both a start and end date for filtering. Displaying data from **all available dates**.")
        df_filtered = df.copy()

    if 'product_name' in df_filtered.columns and not df_filtered['product_name'].dropna().empty:
        unique_product_names = ['All'] + sorted(df_filtered['product_name'].dropna().unique().tolist())
        selected_product_name = st.sidebar.selectbox("Filter by Product Name", unique_product_names)
        if selected_product_name != 'All':
            df_filtered = df_filtered[df_filtered['product_name'] == selected_product_name]

    # Product Compound Tag Filter (NEW for this page) - filter by the exact tag combination
    if 'product_tags_compound' in df_filtered.columns and not df_filtered['product_tags_compound'].dropna().empty:
        unique_compound_tags = ['All'] + sorted(df_filtered['product_tags_compound'].dropna().unique().tolist())
        selected_compound_tag = st.sidebar.selectbox("Filter by Product Tag Combination", unique_compound_tags)
        if selected_compound_tag != 'All':
            df_filtered = df_filtered[df_filtered['product_tags_compound'] == selected_compound_tag]
            
    # --- Main Content Area ---
    if df_filtered.empty: 
        st.warning("No data available for the selected filters. Please adjust your date range or other filters.")
    else:
        # --- Product KPIs ---
        st.write("**Product Key Performance Indicators**")
        
        total_products_sold = df_filtered['quantity'].sum() if 'quantity' in df_filtered.columns else 0
        unique_orders_for_product = df_filtered.drop_duplicates(subset=['order_id'])
        total_product_revenue = unique_orders_for_product['total_order_value'].sum() if 'total_order_value' in unique_orders_for_product.columns else 0
        unique_products_sold = df_filtered['product_sku'].nunique() if 'product_sku' in df_filtered.columns else 0
        avg_product_price = total_product_revenue / total_products_sold if total_products_sold > 0 else 0
        
        col1, col2, col3, col4 = st.columns(4) # Added one more column for new KPI
        col1.metric("Total Product Units Sold", f"{format_kpi_number(int(total_products_sold))}")
        col2.metric("Total Product Revenue", f"₹ {format_kpi_number(total_product_revenue)}")
        col3.metric("Unique Products Sold", f"{format_kpi_number(unique_products_sold)}")
        col4.metric("Avg. Price per Unit", f"₹ {format_kpi_number(avg_product_price)}")

        st.markdown("---")

        # --- Top/Bottom Performing Products ---
        # st.subheader("Top Performing Products")

        # Top Products by Revenue
        if all(col in df_filtered.columns for col in ['product_name', 'line_item_revenue']): 
            top_products_revenue = df_filtered.groupby('product_name')['line_item_revenue'].sum().nlargest(10).reset_index()
            
            if not top_products_revenue.empty:
                fig_top_products_revenue = plot_bar_chart(
                    top_products_revenue, 
                    'product_name', 
                    'line_item_revenue', 
                    'Top 10 Products by Revenue', 
                    'Product Name', 
                    'Revenue (₹)', 
                    orientation='h'
                )
                st.plotly_chart(fig_top_products_revenue, use_container_width=True)
            else:
                st.info("No data for Top Products by Revenue.")
        else:
            st.warning("Product name or line_item_revenue columns missing for product revenue analysis.")

        # Top Products by Quantity
        if all(col in df_filtered.columns for col in ['product_name', 'quantity']):
            top_products_quantity = df_filtered.groupby('product_name')['quantity'].sum().nlargest(10).reset_index()
            
            if not top_products_quantity.empty:
                fig_top_products_quantity = plot_bar_chart(
                    top_products_quantity, 
                    'product_name', 
                    'quantity', 
                    'Top 10 Products by Quantity Sold', 
                    'Product Name', 
                    'Quantity Sold', 
                    orientation='h'
                )
                st.plotly_chart(fig_top_products_quantity, use_container_width=True)
            else:
                st.info("No data for Top Products by Quantity.")
        else:
            st.warning("Product name or quantity columns missing for product quantity analysis.")

        st.markdown("---")

        # --- Product Performance by Compound Tags ---
        st.write("#### Product Performance by Tags")

        if 'product_tags_compound' in df_filtered.columns and not df_filtered['product_tags_compound'].dropna().empty:
            if 'line_item_revenue' in df_filtered.columns: 
                col_compound_tag_perf1, col_compound_tag_perf2 = st.columns(2)

                # Revenue by Product Compound Tag
                with col_compound_tag_perf1:
                    compound_tag_revenue = df_filtered.groupby('product_tags_compound')['line_item_revenue'].sum().nlargest(15).reset_index() 
                    if not compound_tag_revenue.empty:
                        fig_compound_tag_revenue = plot_bar_chart(
                            compound_tag_revenue.sort_values(by='line_item_revenue', ascending=False),
                            'product_tags_compound', 
                            'line_item_revenue', 
                            'Top Product Tag Combinations by Revenue', 
                            'Tag Combination', 
                            'Revenue (₹)',
                            orientation='h'
                        )
                        st.plotly_chart(fig_compound_tag_revenue, use_container_width=True)
                    else:
                        st.info("No data for Revenue by Product Tag Combination.")
                
                # Quantity Sold by Product Compound Tag
                with col_compound_tag_perf2:
                    compound_tag_quantity = df_filtered.groupby('product_tags_compound')['quantity'].sum().nlargest(15).reset_index() 
                    if not compound_tag_quantity.empty:
                        fig_compound_tag_quantity = plot_bar_chart(
                            compound_tag_quantity.sort_values(by='quantity', ascending=False),
                            'product_tags_compound', 
                            'quantity', 
                            'Top Product Tag Combinations by Quantity Sold', 
                            'Tag Combination', 
                            'Quantity Sold',
                            orientation='h'
                        )
                        st.plotly_chart(fig_compound_tag_quantity, use_container_width=True)
                    else:
                        st.info("No data for Quantity Sold by Product Tag Combination.")

                # Product Compound Tag Revenue Mix (Donut Chart)
                # st.write("#### Product Tag Combination Revenue ")
                if not compound_tag_revenue.empty: 
                    fig_donut_compound_tags = px.pie(
                        compound_tag_revenue,
                        values='line_item_revenue',
                        names='product_tags_compound',
                        title='Percentage of Revenue by Product Tag',
                        hole=0.4 
                    )
                    fig_donut_compound_tags.update_traces(textposition='inside', textinfo='percent+label')
                    st.plotly_chart(fig_donut_compound_tags, use_container_width=True)
                else:
                    st.info("No data to show Product Tag Combination Revenue Mix.")

            else:
                st.warning("Line_item_revenue column missing for product tag combination breakdown.")
        else:
            st.info("Product compound tags column is missing or empty for tag analysis.")
        
        st.markdown("---")

        if 'product_tags_compound' in df.columns and not df['product_tags_compound'].empty:
            if 'quantity' in df.columns:
                compound_tag_quantity = df.groupby('product_tags_compound')['quantity'].sum().reset_index()
                if not compound_tag_quantity.empty:
                    # st.subheader("Product Quantity Mix by Tag Combination")
                    fig_donut_compound_tags_quantity = px.pie(
                    compound_tag_quantity,
                    values='quantity',  
                    names='product_tags_compound',
                    title='Percentage of Quantity sold by Product Tag',
                    hole=0.4
                    )
                    fig_donut_compound_tags_quantity.update_traces(textposition='inside', textinfo='percent+label')
                    st.plotly_chart(fig_donut_compound_tags_quantity, use_container_width=True)
                else:
                   st.info("No data to show Product Tag Combination Quantity Mix.")
            else:
                st.warning("Line_item_quantity column missing for product tag quantity combination breakdown.")
        else:
           st.info("Product compound tags column is missing or empty for tag analysis.")
        st.markdown("---")

        # --- Product Performance by INDIVIDUAL Tags (Corrected Logic) ---
        st.write("#### Product Performance by Individual Tags")
        st.info("Note: A product can have multiple tags, so the sum of revenue/quantity for individual tags may exceed total product revenue/quantity as a product's value is counted for each of its tags.")

        if 'product_tags_list' in df_filtered.columns and not df_filtered['product_tags_list'].dropna().empty and 'line_item_revenue' in df_filtered.columns:
            
            individual_tag_df = df_filtered.copy()
            individual_tag_df = individual_tag_df.explode('product_tags_list')
            individual_tag_df.rename(columns={'product_tags_list': 'individual_product_tag'}, inplace=True)
            
            individual_tag_df = individual_tag_df[individual_tag_df['individual_product_tag'] != 'unknown tag']
            individual_tag_df = individual_tag_df[individual_tag_df['individual_product_tag'].str.strip() != '']

            if not individual_tag_df.empty:
                col_individual_tag_perf1, col_individual_tag_perf2 = st.columns(2)

                # Revenue by Individual Product Tag
                with col_individual_tag_perf1:
                    #st.write("### Revenue by Individual Product Tag")
                    individual_tag_revenue = individual_tag_df.groupby('individual_product_tag')['line_item_revenue'].sum().nlargest(15).reset_index() 
                    if not individual_tag_revenue.empty:
                        fig_individual_tag_revenue = plot_bar_chart(
                            individual_tag_revenue.sort_values(by='line_item_revenue', ascending=False),
                            'individual_product_tag', 
                            'line_item_revenue', 
                            'Top Individual Product Tags by Revenue', 
                            'Individual Tag', 
                            'Revenue (₹)',
                            orientation='h'
                        )
                        st.plotly_chart(fig_individual_tag_revenue, use_container_width=True)
                    else:
                        st.info("No data for Revenue by Individual Product Tag.")
                
                # Quantity Sold by Individual Product Tag
                with col_individual_tag_perf2:
                    # st.write("### Quantity Sold by Individual Product Tag")
                    individual_tag_quantity = individual_tag_df.groupby('individual_product_tag')['quantity'].sum().nlargest(15).reset_index() 
                    if not individual_tag_quantity.empty:
                        fig_individual_tag_quantity = plot_bar_chart(
                            individual_tag_quantity.sort_values(by='quantity', ascending=False),
                            'individual_product_tag', 
                            'quantity', 
                            'Top Individual Product Tags by Quantity Sold', 
                            'Individual Tag', 
                            'Quantity Sold',
                            orientation='h'
                        )
                        st.plotly_chart(fig_individual_tag_quantity, use_container_width=True)
                    else:
                        st.info("No data for Quantity Sold by Individual Product Tag.")
            else:
                st.info("No valid individual product tags found in the filtered data.")
        else:
            st.warning("Product tags list or line_item_revenue column missing for individual tag analysis.")

        st.markdown("---")

        # --- Product Trends ---
        st.write("#### Product Sales Trends")
        
        # Daily Product Revenue Trend
        if all(col in df_filtered.columns for col in ['order_date', 'line_item_revenue']):
            daily_product_revenue = df_filtered.copy()
            daily_product_revenue_trend = daily_product_revenue.groupby(daily_product_revenue['order_date'].dt.date)['line_item_revenue'].sum().reset_index()
            daily_product_revenue_trend.columns = ['Date', 'Revenue']
            daily_product_revenue_trend['Date'] = pd.to_datetime(daily_product_revenue_trend['Date'])
            daily_product_revenue_trend = daily_product_revenue_trend.sort_values('Date')

            if not daily_product_revenue_trend.empty:
                fig_prod_revenue_trend = plot_time_series(daily_product_revenue_trend, 'Date', 'Revenue', 'Daily Product Revenue Trend', 'Product Revenue (₹)')
                st.plotly_chart(fig_prod_revenue_trend, use_container_width=True)
            else:
                st.info("No data to show daily product revenue trend.")
        else:
            st.warning("Order date or line_item_revenue columns missing for product revenue trend.")

        # Daily Quantity Sold Trend
        if all(col in df_filtered.columns for col in ['order_date', 'quantity']):
            daily_quantity_sold_trend = df_filtered.groupby(df_filtered['order_date'].dt.date)['quantity'].sum().reset_index()
            daily_quantity_sold_trend.columns = ['Date', 'Quantity Sold']
            daily_quantity_sold_trend['Date'] = pd.to_datetime(daily_quantity_sold_trend['Date'])
            daily_quantity_sold_trend = daily_quantity_sold_trend.sort_values('Date')

            if not daily_quantity_sold_trend.empty:
                fig_qty_trend = plot_time_series(daily_quantity_sold_trend, 'Date', 'Quantity Sold', 'Daily Quantity Sold Trend', 'Units Sold')
                st.plotly_chart(fig_qty_trend, use_container_width=True)
            else:
                st.info("No data to show daily quantity sold trend.")
        else:
            st.warning("Order date or quantity columns missing for product quantity trend.")

        st.markdown("---")

        # --- Stock Level Analysis ---
        st.write("#### Stock Level Insights")
        if all(col in df_filtered.columns for col in ['product_name', 'stock_available']):

            latest_stock = df_filtered.drop_duplicates(subset=['product_sku'], keep='last')[['product_name', 'product_sku', 'stock_available']].copy()
            latest_stock['stock_available'] = latest_stock['stock_available'].astype(int)

            low_stock_threshold = 20

            low_stock_products = latest_stock[latest_stock['stock_available'] <= low_stock_threshold].sort_values('stock_available')

            if not low_stock_products.empty:
                st.write(f"**Products with Low Stock (<= {low_stock_threshold} units)**")
                st.dataframe(low_stock_products, hide_index=True, use_container_width=True)
            else:
                st.info(f"No products found with stock <= {low_stock_threshold} units in the filtered data.")
        else:
            st.warning("Product name, product SKU, or stock available columns missing for stock analysis.")


else:
    st.error("Cannot load product data. Please check the `utils/data_loader.py` file for configuration and potential BigQuery connection issues.")
    st.info("If data loading fails, the dashboard cannot display any insights. Ensure your BigQuery project, dataset, and table IDs are correct and your GCP authentication is set up via `gcloud auth application-default login`.")
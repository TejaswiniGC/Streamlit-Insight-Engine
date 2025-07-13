import streamlit as st
import pandas as pd
from utils.data_loader import load_ecommerce_data, get_filtered_data
from utils.plot_utils import plot_bar_chart, plot_time_series
from utils.kpi_calculations import format_kpi_number
import plotly.express as px
from datetime import date

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
    # Ensure order_date is datetime type
    if 'order_date' in df.columns:
        df['order_date'] = pd.to_datetime(df['order_date'], errors='coerce')
        df.dropna(subset=['order_date'], inplace=True)

    valid_order_dates = df['order_date'].dropna()
    if not valid_order_dates.empty:
        # Using the actual min/max dates from data, if available, otherwise default
        min_date_available_data = valid_order_dates.min().date()
        max_date_available_data = valid_order_dates.max().date()
        # Set a fixed start date for consistency as per previous instructions, but respect data limits
        min_date_display = date(2025, 7, 13) # Fixed display start date
        min_date_to_use = max(min_date_display, min_date_available_data)
    else:
        min_date_to_use = pd.Timestamp.now().date() - pd.Timedelta(days=365)
        max_date_available_data = pd.Timestamp.now().date()

    date_range = st.sidebar.date_input(
        "Select Order Date Range",
        value=(min_date_to_use, max_date_available_data),
        min_value=min_date_to_use,
        max_value=max_date_available_data
    )

    df_filtered = pd.DataFrame()

    if len(date_range) == 2:
        start_date, end_date = date_range
        if start_date > end_date:
            st.sidebar.error("Error: Start date cannot be after end date.")
            df_filtered = df.copy() # Revert to full data if invalid date range
            st.info("Displaying data from **all available dates** due to invalid date range selection.")
        else:
            df_filtered = get_filtered_data(df, start_date, end_date)
            st.info(f"Displaying data from **{start_date.strftime('%Y-%m-%d')}** to **{end_date.strftime('%Y-%m-%d')}**")
    else:
        st.warning("Please select both a start and end date for filtering. Displaying data from **all available dates**.")
        df_filtered = df.copy() # Revert to full data if incomplete date range

    if 'product_name' in df_filtered.columns and not df_filtered['product_name'].dropna().empty:
        unique_product_names = ['All'] + sorted(df_filtered['product_name'].dropna().unique().tolist())
        selected_product_name = st.sidebar.selectbox("Filter by Product Name", unique_product_names)
        if selected_product_name != 'All':
            df_filtered = df_filtered[df_filtered['product_name'] == selected_product_name]

    # Product Compound Tag Filter
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
        # Use line_item_revenue for product-level revenue calculation
        total_product_revenue = df_filtered['line_item_revenue'].sum() if 'line_item_revenue' in df_filtered.columns else 0
        unique_products_sold = df_filtered['product_sku'].nunique() if 'product_sku' in df_filtered.columns else 0
        avg_product_price = total_product_revenue / total_products_sold if total_products_sold > 0 else 0

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Product Units Sold", f"{format_kpi_number(int(total_products_sold))}")
        col2.metric("Total Product Revenue", f"₹ {format_kpi_number(total_product_revenue)}")
        col3.metric("Unique Products Sold", f"{format_kpi_number(unique_products_sold)}")
        col4.metric("Avg. Price per Unit", f"₹ {format_kpi_number(avg_product_price)}")

        st.markdown("---")

        # --- Top/Bottom Performing Products ---
        # Top Products by Revenue
        if all(col in df_filtered.columns for col in ['product_name', 'line_item_revenue']):
            top_products_revenue = df_filtered.groupby('product_name')['line_item_revenue'].sum().nlargest(10).reset_index()

            if not top_products_revenue.empty:
                top_products_revenue['Formatted_Revenue'] = top_products_revenue['line_item_revenue'].apply(lambda x: f"₹ {format_kpi_number(x)}")

                fig_top_products_revenue = px.bar(
                    top_products_revenue,
                    x='line_item_revenue',
                    y='product_name',
                    title='Top 10 Products by Revenue',
                    labels={'product_name': 'Product Name', 'line_item_revenue': 'Revenue (₹)'},
                    orientation='h',
                    text='Formatted_Revenue'
                )
                fig_top_products_revenue.update_traces(textposition='outside')
                fig_top_products_revenue.update_layout(
                    yaxis={'categoryorder':'total ascending'},
                    xaxis=dict(range=[0, top_products_revenue['line_item_revenue'].max() * 1.15])
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
                top_products_quantity['Formatted_Quantity'] = top_products_quantity['quantity'].apply(format_kpi_number)

                fig_top_products_quantity = px.bar(
                    top_products_quantity,
                    x='quantity',
                    y='product_name',
                    title='Top 10 Products by Quantity Sold',
                    labels={'product_name': 'Product Name', 'quantity': 'Quantity Sold'},
                    orientation='h',
                    text='Formatted_Quantity'
                )
                fig_top_products_quantity.update_traces(textposition='outside')
                fig_top_products_quantity.update_layout(
                    yaxis={'categoryorder':'total ascending'},
                    xaxis=dict(range=[0, top_products_quantity['quantity'].max() * 1.15])
                )
                st.plotly_chart(fig_top_products_quantity, use_container_width=True)
            else:
                st.info("No data for Top Products by Quantity.")
        else:
            st.warning("Product name or quantity columns missing for product quantity analysis.")

        st.markdown("---")

        # --- Product Performance by Compound Tags ---
        st.write("#### Product Performance by Tags (Combinations)")

        if 'product_tags_compound' in df_filtered.columns and not df_filtered['product_tags_compound'].dropna().empty:
            if 'line_item_revenue' in df_filtered.columns:
                col_compound_tag_perf1, col_compound_tag_perf2 = st.columns(2)

                # Revenue by Product Compound Tag
                with col_compound_tag_perf1:
                    compound_tag_revenue = df_filtered.groupby('product_tags_compound')['line_item_revenue'].sum().nlargest(15).reset_index()
                    if not compound_tag_revenue.empty:
                        compound_tag_revenue['Formatted_Revenue'] = compound_tag_revenue['line_item_revenue'].apply(lambda x: f"₹ {format_kpi_number(x)}")

                        fig_compound_tag_revenue = px.bar(
                            compound_tag_revenue.sort_values(by='line_item_revenue', ascending=False),
                            x='line_item_revenue',
                            y='product_tags_compound',
                            title='Top Product Tag Combinations by Revenue',
                            labels={'product_tags_compound': 'Tag Combination', 'line_item_revenue': 'Revenue (₹)'},
                            orientation='h',
                            text='Formatted_Revenue'
                        )
                        fig_compound_tag_revenue.update_traces(textposition='outside')
                        fig_compound_tag_revenue.update_layout(
                            yaxis={'categoryorder':'total ascending'},
                            xaxis=dict(range=[0, compound_tag_revenue['line_item_revenue'].max() * 1.15])
                        )
                        st.plotly_chart(fig_compound_tag_revenue, use_container_width=True)
                    else:
                        st.info("No data for Revenue by Product Tag Combination.")

                # Quantity Sold by Product Compound Tag
                with col_compound_tag_perf2:
                    compound_tag_quantity = df_filtered.groupby('product_tags_compound')['quantity'].sum().nlargest(15).reset_index()
                    if not compound_tag_quantity.empty:
                        compound_tag_quantity['Formatted_Quantity'] = compound_tag_quantity['quantity'].apply(format_kpi_number)

                        fig_compound_tag_quantity = px.bar(
                            compound_tag_quantity.sort_values(by='quantity', ascending=False),
                            x='quantity',
                            y='product_tags_compound',
                            title='Top Product Tag Combinations by Quantity Sold',
                            labels={'product_tags_compound': 'Tag Combination', 'quantity': 'Quantity Sold'},
                            orientation='h',
                            text='Formatted_Quantity'
                        )
                        fig_compound_tag_quantity.update_traces(textposition='outside')
                        fig_compound_tag_quantity.update_layout(
                            yaxis={'categoryorder':'total ascending'},
                            xaxis=dict(range=[0, compound_tag_quantity['quantity'].max() * 1.15])
                        )
                        st.plotly_chart(fig_compound_tag_quantity, use_container_width=True)
                    else:
                        st.info("No data for Quantity Sold by Product Tag Combination.")

                # Product Compound Tag Revenue Mix (Donut Chart)
                if not compound_tag_revenue.empty:
                    fig_donut_compound_tags = px.pie(
                        compound_tag_revenue,
                        values='line_item_revenue',
                        names='product_tags_compound',
                        title='Percentage of Revenue by Product Tag Combination',
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

        # Quantity Mix by Product Compound Tag (Donut Chart)
        if 'product_tags_compound' in df_filtered.columns and not df_filtered['product_tags_compound'].dropna().empty:
             if 'quantity' in df_filtered.columns:
                 compound_tag_quantity_mix = df_filtered.groupby('product_tags_compound')['quantity'].sum().reset_index()
                 if not compound_tag_quantity_mix.empty:
                     fig_donut_compound_tags_quantity = px.pie(
                         compound_tag_quantity_mix,
                         values='quantity',
                         names='product_tags_compound',
                         title='Percentage of Quantity Sold by Product Tag Combination',
                         hole=0.4
                     )
                     fig_donut_compound_tags_quantity.update_traces(textposition='inside', textinfo='percent+label')
                     st.plotly_chart(fig_donut_compound_tags_quantity, use_container_width=True)
                 else:
                     st.info("No data to show Product Tag Combination Quantity Mix.")
             else:
                 st.warning("Quantity column missing for product tag quantity combination breakdown.")
        # No 'else' needed here, as the initial 'if' for compound tags covers the missing/empty case.

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
        if all(col in df_filtered.columns for col in ['product_name', 'stock_available', 'product_sku']):

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
    st.info("If data loading fails, the dashboard cannot display any insights. Ensure your BigQuery project, dataset, and table IDs are correct and your GCP authentication is set up via `gcloud auth application-default-login`.")
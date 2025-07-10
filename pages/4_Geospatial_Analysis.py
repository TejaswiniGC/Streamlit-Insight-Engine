import streamlit as st
import pandas as pd
from utils.data_loader import load_ecommerce_data, get_filtered_data
from utils.plot_utils import plot_bar_chart
from utils.kpi_calculations import format_kpi_number
import plotly.express as px # For map visualization

st.set_page_config(layout="wide", page_title="Geospatial Analysis", page_icon="🗺️")

css_file_path = "styles.css" 

# Check if the file exists before trying to read it
try:
    with open(css_file_path) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except FileNotFoundError:
    st.error(f"Could not find {css_file_path}.")

st.header(":blue[🗺️ Geospatial Sales Analysis]")

st.markdown("""
This section provides insights into sales distribution across different geographical regions,
leveraging both location names and precise latitude/longitude data.
""")

# Load data (this will use the cached data from data_loader.py)
df = load_ecommerce_data()

# --- Sidebar Filters ---
st.sidebar.header(":blue[🗺️ Apply Filters]")

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

    if 'geography_state' in df_filtered.columns and not df_filtered['geography_state'].dropna().empty:
        # Filter states based on selected country
        current_states = df_filtered['geography_state'].dropna().unique().tolist()
        unique_states = ['All'] + sorted(current_states)
        selected_state = st.sidebar.selectbox("Filter by State", unique_states)
        if selected_state != 'All':
            df_filtered = df_filtered[df_filtered['geography_state'] == selected_state]

    if 'geography_city' in df_filtered.columns and not df_filtered['geography_city'].dropna().empty:
        # Filter cities based on selected country/state
        current_cities = df_filtered['geography_city'].dropna().unique().tolist()
        unique_cities = ['All'] + sorted(current_cities)
        selected_city = st.sidebar.selectbox("Filter by City", unique_cities)
        if selected_city != 'All':
            df_filtered = df_filtered[df_filtered['geography_city'] == selected_city]


    # --- Main Content Area ---
    if df_filtered.empty:
        st.warning("No data available for the selected filters. Please adjust your date range or geographical filters.")
    else:
        # --- Geospatial KPIs ---
        st.write("**Geospatial KPI**")
        
        unique_orders_for_geo = df_filtered.drop_duplicates(subset=['order_id'])
        total_geo_revenue = unique_orders_for_geo['total_order_value'].sum() if 'total_order_value' in unique_orders_for_geo.columns else 0
        total_geo_orders = df_filtered['order_id'].nunique() if 'order_id' in df_filtered.columns else 0
        unique_states = df_filtered['geography_state'].nunique() if 'geography_state' in df_filtered.columns else 0
        unique_cities = df_filtered['geography_city'].nunique() if 'geography_city' in df_filtered.columns else 0

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Revenue", f"₹ {format_kpi_number(total_geo_revenue)}")
        col2.metric("Total Orders", f"{format_kpi_number(total_geo_orders)}")
        col3.metric("Unique States", f"{format_kpi_number(unique_states)}")
        col4.metric("Unique Cities", f"{format_kpi_number(unique_cities)}")

        st.markdown("---")

        # --- Sales Distribution Map ---
        st.write("#### Sales Distribution Map")
        st.info("The map visualizes sales volume by location. Larger circles indicate higher revenue. Zoom in to see more detail.")

        map_data = df_filtered.dropna(subset=['shipping_address_latitude', 'shipping_address_longitude', 'line_item_revenue']).copy()
        
        if not map_data.empty:
            aggregated_map_data = map_data.groupby(['shipping_address_latitude', 'shipping_address_longitude', 'geography_city']).agg(
                total_revenue=('line_item_revenue', 'sum'),
                total_quantity=('quantity', 'sum'),
                order_count=('order_id', 'nunique')
            ).reset_index()

            aggregated_map_data['tooltip_text'] = aggregated_map_data.apply(
                lambda row: f"City: {row['geography_city']}<br>Revenue: ₹{row['total_revenue']:,.2f}<br>Orders: {row['order_count']}<br>Quantity: {row['total_quantity']}", axis=1
            )

            # Define a sensible center for the map (e.g., average lat/lon)
            # Or use a specific city like Delhi/Mumbai if most sales are from India
            center_lat = aggregated_map_data['shipping_address_latitude'].mean() if not aggregated_map_data['shipping_address_latitude'].empty else 20.5937 # Approx India center
            center_lon = aggregated_map_data['shipping_address_longitude'].mean() if not aggregated_map_data['shipping_address_longitude'].empty else 78.9629 # Approx India center

            fig_map = px.scatter_mapbox(
                aggregated_map_data,
                lat="shipping_address_latitude",
                lon="shipping_address_longitude",
                size="total_revenue", # Size by revenue
                color="total_revenue", # Color by revenue
                hover_name="geography_city", # Name shown on hover
                hover_data={"tooltip_text": True, "total_revenue": False, "shipping_address_latitude":False, "shipping_address_longitude":False}, # Show custom tooltip text
                zoom=4, # Adjust zoom level as needed
                height=500,
                mapbox_style="carto-positron", # or "open-street-map", "stamen-terrain", "stamen-toner"
                center={"lat": center_lat, "lon": center_lon},
                color_continuous_scale=px.colors.sequential.Plasma # Or other color scales
            )
            # Customizing hovertemplate to use our pre-formatted text
            fig_map.update_traces(hovertemplate='%{customdata[0]}')
            st.plotly_chart(fig_map, use_container_width=True)
        else:
            st.warning("No valid latitude/longitude data or revenue for map visualization in the filtered dataset.")

        st.markdown("---")

        # --- Performance by State ---
        if 'geography_state' in df_filtered.columns:
            #st.write("#### Performance by State")
            state_revenue = df_filtered.groupby('geography_state')['line_item_revenue'].sum().nlargest(10).reset_index()
            state_orders = df_filtered.groupby('geography_state')['order_id'].nunique().nlargest(10).reset_index()

            col_state1, col_state2 = st.columns(2)
            with col_state1:
                if not state_revenue.empty:
                    fig_state_rev = plot_bar_chart(state_revenue, 'geography_state', 'line_item_revenue', 'Revenue by State', 'State', 'Revenue (₹)')
                    st.plotly_chart(fig_state_rev, use_container_width=True)
                else:
                    st.info("No data for Revenue by State.")
            with col_state2:
                if not state_orders.empty:
                    fig_state_ord = plot_bar_chart(state_orders, 'geography_state', 'order_id', 'Orders by State', 'State', 'Number of Orders')
                    st.plotly_chart(fig_state_ord, use_container_width=True)
                else:
                    st.info("No data for Orders by State.")
        else:
            st.info("Geography_state column not available for analysis.")

        st.markdown("---")

        # --- Performance by City ---
        if 'geography_city' in df_filtered.columns:
            #st.subheader("Performance by City")
            city_revenue = df_filtered.groupby('geography_city')['line_item_revenue'].sum().nlargest(10).reset_index()
            city_orders = df_filtered.groupby('geography_city')['order_id'].nunique().nlargest(10).reset_index()

            col_city1, col_city2 = st.columns(2)
            with col_city1:
                if not city_revenue.empty:
                    fig_city_rev = plot_bar_chart(city_revenue, 'geography_city', 'line_item_revenue', 'Revenue by City', 'City', 'Revenue (₹)')
                    st.plotly_chart(fig_city_rev, use_container_width=True)
                else:
                    st.info("No data for Revenue by City.")
            with col_city2:
                if not city_orders.empty:
                    fig_city_ord = plot_bar_chart(city_orders, 'geography_city', 'order_id', 'Orders by City', 'City', 'Number of Orders')
                    st.plotly_chart(fig_city_ord, use_container_width=True)
                else:
                    st.info("No data for Orders by City.")
        else:
            st.info("Geography_city column not available for analysis.")


else:
    st.error("Cannot load geospatial data. Please check the `utils/data_loader.py` file for configuration and potential BigQuery connection issues.")
    st.info("If data loading fails, the dashboard cannot display any insights. Ensure your BigQuery project, dataset, and table IDs are correct and your GCP authentication is set up via `gcloud auth application-default login`.")
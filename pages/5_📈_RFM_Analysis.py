import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
# Assuming these are correctly set up and return DFs with necessary columns
from utils.data_loader import load_ecommerce_data, load_customer_data, calculate_rfm 
# Assuming format_kpi_number is available for general formatting if needed elsewhere
from utils.kpi_calculations import format_kpi_number 

st.set_page_config(
    layout="wide", 
    page_title="RFM Analysis", 
    page_icon="📈",
    initial_sidebar_state="expanded" 
)

css_file_path = "styles.css" 

# Check if the file exists before trying to read it
try:
    with open(css_file_path) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except FileNotFoundError:
    st.error(f"Could not find {css_file_path}.")

st.title("📈 Customer RFM Analysis")

st.markdown("""
Understand your customers based on their **Recency** (how recently they purchased),
**Frequency** (how often they purchase), and **Monetary** (how much they spend).
This analysis segments your customers into actionable groups.
""")

# Load data
df_orders = load_ecommerce_data()
df_customers_master = load_customer_data()

# Calculate RFM - this function is cached
# Make sure calculate_rfm outputs 'Recency', 'Frequency', 'Monetary' (raw values) 
# in addition to 'R_Score', 'F_Score', 'M_Score', 'RFM_Segment'
df_customers_with_rfm = calculate_rfm(df_orders, df_customers_master)

if df_customers_with_rfm.empty or 'RFM_Segment' not in df_customers_with_rfm.columns:
    st.error("RFM analysis could not be performed. Please ensure order and customer data are loaded correctly and contain necessary columns (customer_id, order_date, total_order_value).")
    st.stop() # Stop execution if data is not ready

# --- Sidebar Filters ---
st.sidebar.header("RFM Filters")

# Filter by RFM Segment
unique_segments = ['All'] + sorted(df_customers_with_rfm['RFM_Segment'].dropna().unique().tolist())
selected_segment = st.sidebar.selectbox("Select RFM Segment", unique_segments)

df_filtered_rfm = df_customers_with_rfm.copy()
if selected_segment != 'All':
    df_filtered_rfm = df_filtered_rfm[df_filtered_rfm['RFM_Segment'] == selected_segment]

# --- Main Content ---

st.subheader("RFM Segments Overview")

if not df_filtered_rfm.empty:
    segment_counts = df_filtered_rfm['RFM_Segment'].value_counts().reset_index()
    segment_counts.columns = ['RFM Segment', 'Number of Customers']
    
    fig_segments = px.pie(segment_counts, 
                            values='Number of Customers', 
                            names='RFM Segment', 
                            title=f'Distribution of Customers by RFM Segment ({selected_segment if selected_segment != "All" else "All Segments"})',
                            hole=0.4)
    fig_segments.update_traces(textposition='inside', textinfo='percent+label')
    st.plotly_chart(fig_segments, use_container_width=True)

    st.markdown("---")

    st.subheader("RFM Score Distributions")
    col1, col2, col3 = st.columns(3)

    # Recency Distribution
    with col1:
        fig_r = px.histogram(df_filtered_rfm, x='R_Score', nbins=5, title='Recency Score Distribution',
                             labels={'R_Score': 'Recency Score (1-5, 5=Most Recent)'},
                             color_discrete_sequence=px.colors.sequential.Viridis)
        st.plotly_chart(fig_r, use_container_width=True)

    # Frequency Distribution
    with col2:
        fig_f = px.histogram(df_filtered_rfm, x='F_Score', nbins=5, title='Frequency Score Distribution',
                             labels={'F_Score': 'Frequency Score (1-5, 5=Most Frequent)'},
                             color_discrete_sequence=px.colors.sequential.Plasma)
        st.plotly_chart(fig_f, use_container_width=True)

    # Monetary Distribution
    with col3:
        fig_m = px.histogram(df_filtered_rfm, x='M_Score', nbins=5, title='Monetary Score Distribution',
                             labels={'M_Score': 'Monetary Score (1-5, 5=Highest Spend)'},
                             color_discrete_sequence=px.colors.sequential.Cividis)
        st.plotly_chart(fig_m, use_container_width=True)

    st.markdown("---")

    st.subheader("Average RFM Values per Segment")
    if selected_segment == 'All': # Only show this table if 'All' segments are selected
        segment_averages = df_customers_with_rfm.groupby('RFM_Segment').agg(
            Avg_Recency=('Recency', 'mean'), # 'Recency' should be raw days
            Avg_Frequency=('Frequency', 'mean'), # 'Frequency' should be raw count of orders
            Avg_Monetary=('Monetary', 'mean'), # 'Monetary' should be raw total spend
            Customer_Count=('customer_id', 'nunique')
        ).reset_index().round(2)
        segment_averages = segment_averages.sort_values('Customer_Count', ascending=False)
        st.dataframe(segment_averages, use_container_width=True, hide_index=True)
        st.caption("Note: 'Recency' is in days, 'Frequency' is number of orders, 'Monetary' is total spend.")
    else:
        st.info("Select 'All' segments to see the average RFM values across all segments.")

    st.markdown("---")

    st.subheader("Customers in Selected Segment")

    # --- ACTION: Add a "Proposed Action" column for business owners ---
    # This dictionary maps segments to simple proposed actions
    segment_actions = {
        'Champions': "Reward them. They can be early adopters for new products.",
        'Loyal Customers': "Engage them with loyalty programs and exclusive offers.",
        'Potential Loyalists': "Offer incentives for repeat purchases and engagement.",
        'New Customers': "Provide excellent onboarding and welcome offers.",
        'Promising': "Nurture them with personalized recommendations.",
        'Need Attention': "Re-engage with special offers or surveys to understand their needs.",
        'About to Sleep': "Reach out with compelling offers to prevent churn.",
        'At Risk': "Win them back with strong retention campaigns and personalized outreach.",
        'Can\'t Lose Them': "Prioritize high-touch re-engagement and win-back strategies.",
        'Hibernating': "Send personalized reactivation campaigns or surveys.",
        'Lost': "Consider a last-ditch effort or focus on new customer acquisition.",
        'Other': "Review manually, or refine RFM segmentation rules." # Acknowledge 'Other'
    }

    if not df_filtered_rfm.empty:
        # Create a copy to avoid SettingWithCopyWarning when adding new columns
        df_display = df_filtered_rfm.copy()

        # Add the 'Proposed Action' column
        df_display['Proposed_Action'] = df_display['RFM_Segment'].map(segment_actions).fillna("No specific action defined for this segment.")

        st.write(f"Displaying top 20 customers in the **'{selected_segment}'** segment (sorted by Monetary value):")
        
        # --- ACTION: Corrected display_cols using the actual RFM values (Recency, Frequency, Monetary) ---
        display_cols = [
            'customer_id', 
            'first_name', 
            'email', 
            'Recency',        # Raw Recency (days)
            'Frequency',      # Raw Frequency (orders count)
            'Monetary',       # Raw Monetary (total spend)
            'R_Score', 
            'F_Score', 
            'M_Score', 
            'RFM_Segment',
            'Proposed_Action' # New column for actions
        ] 
        
        # Ensure selected columns exist in the DataFrame before displaying
        available_cols = [col for col in display_cols if col in df_display.columns]

        # Use .nlargest(20, 'Monetary') to get customers with highest spend within the filtered segment
        st.dataframe(df_display[available_cols].nlargest(20, 'Monetary'), use_container_width=True, hide_index=True)
        
        st.caption("""
            **Column Explanations:**
            - **Recency:** Days since last purchase (lower is better)
            - **Frequency:** Total number of orders (higher is better)
            - **Monetary:** Total amount spent (higher is better)
            - **R/F/M_Score:** Segment score from 1-5 (5 is best)
            - **RFM_Segment:** Categorical segment name
            - **Proposed_Action:** Suggested business action based on segment
        """)

    else:
        st.info("No customers found for the selected segment and filters.")

else:
    st.info("No data available for RFM analysis after applying filters.")
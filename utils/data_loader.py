import streamlit as st
import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account
import os, re, gspread, json
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from streamlit_gsheets import GSheetsConnection
from tldextract import extract

# --- Configuration Constants ---
PROJECT_ID = "second-impact-388206"
DATASET_ID = "dashboard_data"
ORDERS_TABLE_ID = "orders"
PRODUCTS_TABLE_ID = "products"
CUSTOMER_TABLE_ID = "customers"

RETURNS_SHEET_URL = "https://docs.google.com/spreadsheets/d/1NL2TWlA2nyz04ZSy5U3S8c_tHHr1iCzD5NOQH6SKDc4/edit"
RETURNS_WORKSHEET_NAME = "Sheet1"

# --- Cached Client Initializations ---

@st.cache_resource(ttl=3600)
def get_bigquery_client_cached():
    try:
        creds_bq = st.secrets["connections.bigquery"]
        client = bigquery.Client(credentials=service_account.Credentials.from_service_account_info(creds_bq))
        return client
    except Exception as e:
        st.error(f"Failed to initialize BigQuery client: {e}")
        st.stop()
        return None

@st.cache_resource(ttl=3600)
def get_gsheets_client_cached():
    try:
        creds_gs = st.secrets["connections.gsheets_returns"]
        gc = gspread.service_account_from_dict(creds_gs)
        return gc
    except Exception as e:
        st.error(f"Failed to initialize Google Sheets client: {e}")
        st.stop()
        return None

# --- Data Loading Functions (Individual Tables) ---

@st.cache_data(ttl=3600, show_spinner="Fetching returned products data from Google Sheet...")
def load_returned_products_data():
    """
    Fetches the returned products data from a Google Sheet using direct gspread.
    Caches the result.
    """
    df_returns = pd.DataFrame()
    try:
        gc = get_gsheets_client_cached()
        if gc is None:
            st.warning("Google Sheets client not available. Cannot load returned products data.")
            return pd.DataFrame()

        spreadsheet = gc.open_by_url(RETURNS_SHEET_URL)
        worksheet = spreadsheet.worksheet(RETURNS_WORKSHEET_NAME)
        data = worksheet.get_all_values()

        if data:
            df_returns = pd.DataFrame(data[1:], columns=data[0])
        else:
            st.warning("Google Sheet is empty or contains no data.")
            return pd.DataFrame()

        required_renames = {
            'Date': 'return_date',
            'Product Name': 'product_name',
            'Quantity': 'returned_quantity',
            'Comments': 'return_comments'
        }

        columns_to_rename = {col_old: col_new for col_old, col_new in required_renames.items() if col_old in df_returns.columns}
        df_returns = df_returns.rename(columns=columns_to_rename)

        if 'return_date' in df_returns.columns:
            df_returns['return_date'] = pd.to_datetime(df_returns['return_date'], errors='coerce')
            df_returns.dropna(subset=['return_date'], inplace=True)
        else:
            st.warning("Column 'return_date' (original 'Date') not found after renaming. Date conversion skipped.")

        if 'returned_quantity' in df_returns.columns:
            df_returns['returned_quantity'] = pd.to_numeric(df_returns['returned_quantity'], errors='coerce')
            df_returns.dropna(subset=['returned_quantity'], inplace=True)
        else:
            st.warning("Column 'returned_quantity' (original 'Quantity') not found after renaming. Quantity conversion skipped.")

        final_required_columns = ['return_date', 'product_name', 'returned_quantity', 'return_comments']
        missing_final_columns = [col for col in final_required_columns if col not in df_returns.columns]

        if missing_final_columns:
            st.error(f"❌ After processing, required columns are still missing: {missing_final_columns}. Please verify your Google Sheet data and renaming logic.")
            return pd.DataFrame()

    except Exception as e:
        st.error(f"❌ Error loading returned products data from Google Sheet: {e}")
        st.warning("Please ensure the RETURNS_SHEET_URL and RETURNS_WORKSHEET_NAME are valid and the sheet is shared with the service account email.")
        st.info("Returned products data could not be loaded. Please check Google Sheet connection and sheet configuration (.streamlit/secrets.toml and sheet sharing).")
        df_returns = pd.DataFrame()

    return df_returns

@st.cache_data(ttl=3600, show_spinner="Fetching customer data from BigQuery...")
def load_customer_data():
    """
    Fetches the customers table from Google BigQuery with new columns.
    Caches the result for 1 hour.
    """
    try:
        client = get_bigquery_client_cached()
        if client is None:
            st.warning("BigQuery client not available. Cannot load customer data.")
            return pd.DataFrame()

        table_ref = f"{PROJECT_ID}.{DATASET_ID}.{CUSTOMER_TABLE_ID}"
        query = f"SELECT * FROM `{table_ref}`"
        df_customers = client.query(query).to_dataframe()

        date_cols_cust = ['signup_date', 'updated_at']
        for col in date_cols_cust:
            if col in df_customers.columns:
                df_customers[col] = pd.to_datetime(df_customers[col], errors='coerce')

        numeric_cols_cust = ['total_spent', 'orders_count', 'aov']
        for col in numeric_cols_cust:
            if col in df_customers.columns:
                df_customers[col] = pd.to_numeric(df_customers[col], errors='coerce')

        if 'marketing_opt_in' in df_customers.columns:
            df_customers['marketing_opt_in'] = df_customers['marketing_opt_in'].astype(bool)

        if 'orders_count' in df_customers.columns:
            df_customers['imputed_customer_type'] = df_customers['orders_count'].apply(
                lambda x: 'Returning Customer' if pd.notna(x) and x > 1 else 'New/One-Time Customer'
            )
        else:
            df_customers['imputed_customer_type'] = 'Unknown (Orders Count Missing)'

        return df_customers
    except Exception as e:
        st.error(f"Error loading customer data from BigQuery: {e}")
        st.warning(f"Please ensure your `CUSTOMER_TABLE_ID` '{CUSTOMER_TABLE_ID}' is correct and permissions are set.")
        st.info("Also, verify your Google Cloud authentication (via secrets) and BigQuery permissions for the specified table.")
        return pd.DataFrame()

@st.cache_data(ttl=3600, show_spinner="Fetching and merging orders and products data from BigQuery...")
def load_ecommerce_data():
    """
    Fetches orders and products data, unnest arrays, and merges them to create
    a line-item level DataFrame. This version handles product_tags and product_sku
    as repeated fields in the products table by unnesting them.
    """
    try:
        client = get_bigquery_client_cached()
        if client is None:
            st.warning("BigQuery client not available. Cannot load order and product data.")
            return pd.DataFrame()

        query = f"""
        SELECT
            o.order_date,
            o.updated_at AS order_updated_at,
            o.order_id,
            o.order_number,
            o.customer_id,
            o.email AS customer_email,
            unnested_orders.product_sku AS order_product_sku, -- Renamed to avoid confusion
            unnested_orders.product_id AS order_product_id,   -- Renamed to avoid confusion
            unnested_orders.quantity,
            o.cross_product_linkage,
            o.total_order_value,
            o.discount_applied,
            o.discount_amount,
            o.tax_amount,
            o.payment_status,
            o.fulfillment_status,
            o.shipping_method,
            o.shipping_cost,
            o.referring_site,
            o.return_refund_status,
            o.order_channel,
            o.customer_type,
            o.order_status_from_tag,
            o.geography_country,
            o.geography_state,
            o.geography_city,
            o.geography_postal_code,
            o.shipping_address_latitude,
            o.shipping_address_longitude,
            p.product_name,
            p.product_status,
            p.product_type,
            p.price,
            p.product_created_at,
            p.updated_at AS product_updated_at,
            p.stock_available,
            p.individual_product_tag,
            p.product_sku_single AS product_sku, -- Use the unnested product_sku for the final result
            p.shipping_weight
        FROM
            `{PROJECT_ID}.{DATASET_ID}.{ORDERS_TABLE_ID}` AS o,
            UNNEST(ARRAY(SELECT AS STRUCT sku AS product_sku, id AS product_id, quantity AS quantity FROM UNNEST(o.product_sku) AS sku WITH OFFSET sku_pos JOIN UNNEST(o.product_ids) AS id WITH OFFSET id_pos ON sku_pos = id_pos JOIN UNNEST(o.quantities) AS quantity WITH OFFSET qty_pos ON sku_pos = qty_pos)) AS unnested_orders
        LEFT JOIN
            (
                SELECT
                    product_id,
                    product_sku_single, -- The unnested single SKU
                    product_name,
                    product_status,
                    product_type,
                    price,
                    product_created_at,
                    updated_at,
                    stock_available,
                    individual_product_tag,
                    shipping_weight
                FROM
                    `{PROJECT_ID}.{DATASET_ID}.{PRODUCTS_TABLE_ID}`,
                    UNNEST(product_tags) AS individual_product_tag, -- Unnesting the tags
                    UNNEST(product_sku) AS product_sku_single -- UNNESTING PRODUCT_SKU HERE
            ) AS p
        ON
            unnested_orders.product_sku = p.product_sku_single -- JOIN on the unnested SKU
        """

        df = client.query(query).to_dataframe()

        # --- Type Conversions ---
        date_cols = [
            'order_date', 'order_updated_at', 'product_created_at', 'product_updated_at'
        ]
        for col in date_cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')

        numeric_cols = [
            'order_number', 'quantity', 'total_order_value', 'discount_amount',
            'tax_amount', 'shipping_cost', 'shipping_address_latitude',
            'shipping_address_longitude', 'price', 'stock_available', 'shipping_weight'
        ]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # --- Feature Engineering ---
        if 'quantity' in df.columns and 'price' in df.columns:
            df['line_item_revenue'] = df['quantity'] * df['price']
        else:
            df['line_item_revenue'] = 0
            st.warning("Could not calculate 'line_item_revenue' from 'quantity' and 'price'. Check BigQuery unnesting.")

        if 'order_status_from_tag' in df.columns:
            df['extracted_status'] = df['order_status_from_tag'].fillna('Other/Unknown')
        else:
            df['extracted_status'] = 'N/A (Status Tag Missing)'

        if 'referring_site' in df.columns:
            df['cleaned_referring_site'] = df['referring_site'].apply(advanced_clean_referring_site)
        else:
            df['cleaned_referring_site'] = 'N/A (Site Data Missing)'

        if 'individual_product_tag' in df.columns:
            df['product_tags_list'] = df['individual_product_tag'].apply(lambda x: [x] if pd.notna(x) and x else [])
            df['product_tags_compound'] = df['individual_product_tag'].fillna('Unknown Tag')
        else:
            df['product_tags_list'] = [()] * len(df)
            df['product_tags_compound'] = "N/A (Tags Missing)"

        if 'customer_type' in df.columns:
            df['imputed_customer_type'] = df['customer_type'].fillna('Unknown')
        else:
            df['imputed_customer_type'] = 'N/A (Customer Type Missing)'

        return df

    except Exception as e:
        st.error(f"Error loading and merging data from BigQuery: {e}")
        st.warning(f"Please ensure `ORDERS_TABLE_ID` ('{ORDERS_TABLE_ID}') and `PRODUCTS_TABLE_ID` ('{PRODUCTS_TABLE_ID}') are correct and accessible.")
        st.info("Verify your BigQuery authentication, table schemas, and permissions.")
        return pd.DataFrame()

# --- Helper Functions (Remains the same) ---

def advanced_clean_referring_site(url):
    if pd.isna(url) or not isinstance(url, str) or not url.strip():
        return "Direct/Unknown"
    url_lower = url.lower()
    if url_lower.startswith("android-app://"):
        if "com.google.android.gm" in url_lower: return "Google Mail App"
        elif "com.google.android.googlequicksearchbox" in url_lower: return "Google Search App"
        elif "com.facebook.katana" in url_lower: return "Facebook App"
        elif "com.instagram.android" in url_lower: return "Instagram App"
        return "Other Mobile App"
    url_lower = re.sub(r'^\d+', '', url_lower)
    if not (url_lower.startswith("http://") or url_lower.startswith("https://")):
        url_lower = "http://" + url_lower
    try:
        if "theaffordableorganicstore.com" in url_lower or "affordableorganicstore.company.site" in url_lower:
            if "/apps/track" in url_lower or "/cart" in url_lower or "/my-account" in url_lower or "/shop/" in url_lower or "/search" in url_lower or "/collections/" in url_lower or "/products/" in url_lower or "/home/cart-taos/" in url_lower or "/pages/" in url_lower: return "The Affordable Organic Store (Internal)"
            if "utm_source=facebook" in url_lower or "fbclid=" in url_lower or "gad_source=1" in url_lower or "campaign_id=" in url_lower: return "The Affordable Organic Store (Paid Ads)"
            return "The Affordable Organic Store"
        if "instagram.com" in url_lower: return "Instagram"
        if "facebook.com" in url_lower: return "Facebook"
        if "t.co" in url_lower: return "Twitter"
        if "youtube.com" in url_lower or "youtu.be" in url_lower: return "YouTube"
        if "linkedin.com" in url_lower: return "LinkedIn"
        if "reddit.com" in url_lower: return "Reddit"
        if "meta.com" in url_lower: return "Meta"
        if "google.com" in url_lower:
            if "googleads.g.doubleclick.net" in url_lower or "googlesyndication.com" in url_lower: return "Google Ads"
            query_params = parse_qs(urlparse(url_lower).query)
            if 'q' in query_params or 's' in query_params: return "Google Search"
            return "Google Direct"
        if "brave.com" in url_lower: return "Brave"
        if "bing.com" in url_lower: return "Bing"
        if "ecosia.org" in url_lower: return "Ecosia"
        if "chatgpt.com" in url_lower: return "ChatGPT"
        if "shopify.com" in url_lower: return "Shopify Platform"
        if "webinvoke.paytmpayments.com" in url_lower: return "Webinvoke"
        if "l.wl.co" in url_lower: return "WL Link"
        if "links.rediff.com" in url_lower: return "Rediff Links"
        if "idevaffiliate.com" in url_lower: return "iDevAffiliate"
        extracted = extract(url_lower)
        if extracted.domain: return extracted.domain.replace('-', ' ').title()
        parsed_url = urlparse(url_lower)
        domain = parsed_url.netloc
        if not domain:
            if re.match(r'^[a-f0-9]{32}$', url_lower): return "Internal ID/Tracker"
            return "Other (No Domain)"
        domain = re.sub(r'^(www|m|l)\.', '', domain)
        parts = domain.split('.')
        if len(parts) >= 2: return parts[-2].replace('-', ' ').title()
        return "Other (Generic Domain Fallback)"
    except Exception as e:
        return "Other (Error)"

def get_filtered_data(df, start_date, end_date):
    if not df.empty and 'order_date' in df.columns:
        df_filtered = df[(df['order_date'].dt.date >= start_date) & (df['order_date'].dt.date <= end_date)]
        return df_filtered
    return pd.DataFrame()

@st.cache_data(ttl=3600, show_spinner="Calculating RFM scores...")
def calculate_rfm(df_orders_line_item: pd.DataFrame, df_customers_master: pd.DataFrame) -> pd.DataFrame:
    required_order_cols = ['customer_id', 'order_date', 'order_id', 'total_order_value']
    if not all(col in df_orders_line_item.columns for col in required_order_cols):
        st.warning(f"Order data is missing one or more required columns for RFM calculation: {required_order_cols}. Skipping RFM calculation.")
        return df_customers_master

    df_orders_rfm_agg = df_orders_line_item.groupby(['customer_id', 'order_id']).agg(
        order_date=('order_date', 'first'),
        total_order_value=('total_order_value', 'first')
    ).reset_index()

    df_orders_rfm = df_orders_rfm_agg.dropna(subset=['customer_id', 'order_date', 'total_order_value']).copy()
    if df_orders_rfm.empty:
        st.warning("No valid aggregated order data after dropping NaNs for RFM calculation. Returning original customer master.")
        return df_customers_master

    max_order_date = df_orders_rfm['order_date'].max()
    analysis_date = max_order_date + pd.Timedelta(days=1) if pd.notna(max_order_date) else pd.Timestamp.now()

    rfm_df = df_orders_rfm.groupby('customer_id').agg(
        Recency=('order_date', lambda date: (analysis_date - date.max()).days),
        Frequency=('order_id', 'nunique'),
        Monetary=('total_order_value', 'sum')
    ).reset_index()

    rfm_df['R_Score'] = rfm_df['Recency'].rank(method='first', ascending=False).astype(int)
    rfm_df['F_Score'] = rfm_df['Frequency'].rank(method='first', ascending=True).astype(int)
    rfm_df['M_Score'] = rfm_df['Monetary'].rank(method='first', ascending=True).astype(int)

    rfm_df['R_Score'] = pd.qcut(rfm_df['R_Score'], 5, labels=[1, 2, 3, 4, 5], duplicates='drop').astype(int)
    rfm_df['F_Score'] = pd.qcut(rfm_df['F_Score'], 5, labels=[1, 2, 3, 4, 5], duplicates='drop').astype(int)
    rfm_df['M_Score'] = pd.qcut(rfm_df['M_Score'], 5, labels=[1, 2, 3, 4, 5], duplicates='drop').astype(int)

    rfm_df['RFM_Score'] = rfm_df['R_Score'].astype(str) + rfm_df['F_Score'].astype(str) + rfm_df['M_Score'].astype(str)

    def rfm_segment(row):
        if row['R_Score'] >= 4 and row['F_Score'] >= 4 and row['M_Score'] >= 4:
            return 'Champions'
        elif row['R_Score'] >= 4 and row['F_Score'] >= 3:
            return 'Loyal Customers'
        elif row['R_Score'] >= 3 and row['F_Score'] >= 3 and row['M_Score'] >= 3:
            return 'Potential Loyalists'
        elif row['R_Score'] >= 3 and row['F_Score'] < 3 and row['M_Score'] < 3:
            return 'Needs Attention'
        elif row['R_Score'] <= 2 and row['F_Score'] >= 4:
            return 'At Risk'
        elif row['R_Score'] <= 2 and row['F_Score'] <= 2 and row['M_Score'] <= 2:
            return 'Churned'
        elif row['R_Score'] >= 4 and row['F_Score'] <=2:
            return 'New Customers'
        else:
            return 'Other'

    rfm_df['RFM_Segment'] = rfm_df.apply(rfm_segment, axis=1)

    df_customers_master_with_rfm = df_customers_master.merge(rfm_df, on='customer_id', how='left')

    if 'Recency' in df_customers_master_with_rfm.columns:
        max_recency_val = df_customers_master_with_rfm['Recency'].max() if not df_customers_master_with_rfm['Recency'].empty else 365
        df_customers_master_with_rfm['Recency'] = df_customers_master_with_rfm['Recency'].fillna(max_recency_val + 30)
    else:
        df_customers_master_with_rfm['Recency'] = 0

    df_customers_master_with_rfm['Frequency'] = df_customers_master_with_rfm['Frequency'].fillna(0)
    df_customers_master_with_rfm['Monetary'] = df_customers_master_with_rfm['Monetary'].fillna(0)

    df_customers_master_with_rfm['R_Score'] = df_customers_master_with_rfm['R_Score'].fillna(1).astype(int)
    df_customers_master_with_rfm['F_Score'] = df_customers_master_with_rfm['F_Score'].fillna(1).astype(int)
    df_customers_master_with_rfm['M_Score'] = df_customers_master_with_rfm['M_Score'].fillna(1).astype(int)
    df_customers_master_with_rfm['RFM_Score'] = df_customers_master_with_rfm['RFM_Score'].fillna('111')
    df_customers_master_with_rfm['RFM_Segment'] = df_customers_master_with_rfm['RFM_Segment'].fillna('New/Inactive')

    return df_customers_master_with_rfm
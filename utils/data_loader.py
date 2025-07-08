import streamlit as st
import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account
import os, re, gspread, json # Removed unused json, re-added for clarity if needed elsewhere
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from streamlit_gsheets import GSheetsConnection # This might be conflicting with direct gspread
from tldextract import extract 

# --- Configuration Constants ---
PROJECT_ID = "second-impact-388206"
DATASET_ID = "dashboard_data"
TABLE_ID = "merged_orders"
CUSTOMER_TABLE_ID = "customers"

RETURNS_SHEET_URL = "https://docs.google.com/spreadsheets/d/1NL2TWlA2nyz04ZSy5U3S8c_tHHr1iCzD5NOQH6SKDc4/edit"
RETURNS_WORKSHEET_NAME = "Sheet1"

# --- Cached Client Initializations ---

@st.cache_resource(ttl=3600) # Cache the BigQuery client object
def get_bigquery_client_cached():
    try:
        # Access the entire secret dictionary for the BigQuery connection
        # Streamlit automatically converts the TOML structure into an accessible object/dict
        creds_bq = st.secrets["connections.bigquery"]
        client = bigquery.Client(credentials=service_account.Credentials.from_service_account_info(creds_bq))
        return client
    except Exception as e:
        st.error(f"Failed to initialize BigQuery client: {e}")
        st.stop() # Stop the app if crucial client cannot be initialized
        return None # Should not be reached

@st.cache_resource(ttl=3600) # Cache the gspread client object
def get_gsheets_client_cached():
    try:
        # Access the entire secret dictionary for the Google Sheets connection
        # No need for .token or json.loads. Pass the secret object directly.
        creds_gs = st.secrets["connections.gsheets_returns"]
        gc = gspread.service_account_from_dict(creds_gs)
        return gc
    except Exception as e:
        st.error(f"Failed to initialize Google Sheets client: {e}")
        st.stop() # Stop the app if crucial client cannot be initialized
        return None # Should not be reached

# --- Data Loading Functions ---

@st.cache_data(ttl=3600, show_spinner="Fetching returned products data from Google Sheet...")
def load_returned_products_data():
    """
    Fetches the returned products data from a Google Sheet using direct gspread.
    Caches the result.
    """
    df_returns = pd.DataFrame() 
    try:
        gc = get_gsheets_client_cached() # Get the cached gspread client
        if gc is None: # If client initialization failed
            st.warning("Google Sheets client not available. Cannot load returned products data.")
            return pd.DataFrame()

        spreadsheet = gc.open_by_url(RETURNS_SHEET_URL)
        worksheet = spreadsheet.worksheet(RETURNS_WORKSHEET_NAME)
        data = worksheet.get_all_values()

        if data:
            df_returns = pd.DataFrame(data[1:], columns=data[0])
        else:
            st.warning("Google Sheet is empty or contains no data.")
            return pd.DataFrame() # Return empty if no data

        # --- UPDATED RENAMING CODE ---
        required_renames = {
            'Date': 'return_date',
            'Product Name': 'product_name',
            'Quantity': 'returned_quantity',
            'Comments': 'return_comments'
        }

        columns_to_rename = {col_old: col_new for col_old, col_new in required_renames.items() if col_old in df_returns.columns}
        df_returns = df_returns.rename(columns=columns_to_rename)

        # 2. Convert 'return_date' column to datetime objects
        if 'return_date' in df_returns.columns:
            df_returns['return_date'] = pd.to_datetime(df_returns['return_date'], errors='coerce')
            df_returns.dropna(subset=['return_date'], inplace=True)
        else:
            st.warning("Column 'return_date' (original 'Date') not found after renaming. Date conversion skipped.")

        # 3. Convert 'returned_quantity' to numeric
        if 'returned_quantity' in df_returns.columns:
            df_returns['returned_quantity'] = pd.to_numeric(df_returns['returned_quantity'], errors='coerce')
            df_returns.dropna(subset=['returned_quantity'], inplace=True)
        else:
            st.warning("Column 'returned_quantity' (original 'Quantity') not found after renaming. Quantity conversion skipped.")

        # --- END OF UPDATED RENAMING CODE ---

        # Finally, check if all the *now renamed* required columns exist
        final_required_columns = ['return_date', 'product_name', 'returned_quantity', 'return_comments']
        missing_final_columns = [col for col in final_required_columns if col not in df_returns.columns]

        if missing_final_columns:
            st.error(f"❌ After processing, required columns are still missing: {missing_final_columns}. Please verify your Google Sheet data and renaming logic.")
            return pd.DataFrame() # Return empty DataFrame if essential columns are missing

    except Exception as e:
        st.error(f"❌ Error loading returned products data from Google Sheet: {e}")
        st.warning("Please ensure the RETURNS_SHEET_URL and RETURNS_WORKSHEET_NAME are valid and the sheet is shared with the service account email.")
        st.info("Returned products data could not be loaded. Please check Google Sheet connection and sheet configuration (.streamlit/secrets.toml and sheet sharing).")
        df_returns = pd.DataFrame()

    return df_returns

@st.cache_data(ttl=3600, show_spinner="Fetching customer data from BigQuery...")
def load_customer_data():
    """
    Fetches the customers_data table from Google BigQuery.
    Caches the result for 1 hour.
    """
    try:
        client = get_bigquery_client_cached() # Get the cached BigQuery client
        if client is None: # If client initialization failed
            st.warning("BigQuery client not available. Cannot load customer data.")
            return pd.DataFrame()

        table_ref = f"{PROJECT_ID}.{DATASET_ID}.{CUSTOMER_TABLE_ID}"
        query = f"SELECT * FROM `{table_ref}`"
        df_customers = client.query(query).to_dataframe()

        # Convert relevant columns based on provided schema
        date_cols_cust = ['signup_date', 'updated_at'] 
        for col in date_cols_cust:
            if col in df_customers.columns:
                df_customers[col] = pd.to_datetime(df_customers[col], errors='coerce')
        
        numeric_cols_cust = ['total_spent', 'orders_count']
        for col in numeric_cols_cust:
            if col in df_customers.columns:
                df_customers[col] = pd.to_numeric(df_customers[col], errors='coerce')

        # Calculate AOV for customers table (lifetime AOV)
        if 'total_spent' in df_customers.columns and 'orders_count' in df_customers.columns:
            df_customers['aov'] = df_customers.apply(
                lambda row: row['total_spent'] / row['orders_count'] if pd.notna(row['orders_count']) and row['orders_count'] > 0 else 0,
                axis=1
            )
        else:
            df_customers['aov'] = 0

        # --- Impute customer_type based on orders_count, handling NaN/0 explicitly ---
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

@st.cache_data(ttl=3600, show_spinner="Fetching fresh order data from BigQuery...")
def load_ecommerce_data():
    """
    Fetches the merged_orderdata table from Google BigQuery and performs initial type conversions.
    Caches the result for 1 hour.
    """
    try:
        client = get_bigquery_client_cached() # Get the cached BigQuery client
        if client is None: # If client initialization failed
            st.warning("BigQuery client not available. Cannot load order data.")
            return pd.DataFrame()

        table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"
        query = f"SELECT * FROM `{table_ref}`"
        df = client.query(query).to_dataframe()

        # Convert date columns to datetime objects for proper plotting and filtering
        date_cols_order = ['order_date', 'updated_at', 'cancelled_at', 'product_created_at']
        for col in date_cols_order:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')

        # Convert numeric columns
        numeric_cols_order = [
            'order_number', 'quantity', 'total_order_value', 'discount_amount', 
            'tax_amount', 'shipping_cost', 'shipping_address_latitude', 
            'shipping_address_longitude', 'price', 'stock_available', 'shipping_weight'
        ]
        for col in numeric_cols_order:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # --- Calculate line_item_revenue EARLY ---
        if 'quantity' in df.columns and 'price' in df.columns:
            df['line_item_revenue'] = df['quantity'] * df['price']
        else:
            df['line_item_revenue'] = df['total_order_value'] 
            st.warning("Price or quantity columns not found in order data. 'line_item_revenue' is estimated from 'total_order_value' which might be less accurate for per-product analysis.")

        # --- Extract Status from order_tags ---
        if 'order_tags' in df.columns:
            df['extracted_status_from_tags'] = df['order_tags'].apply(extract_status_from_tags)
            df['extracted_status_from_tags'] = df['extracted_status_from_tags'].fillna('Other/Unknown')
        else:
            df['extracted_status_from_tags'] = 'N/A (Tags Missing)'

        # --- Clean Referring Site URLs ---
        if 'referring_site' in df.columns:
            df['cleaned_referring_site'] = df['referring_site'].apply(advanced_clean_referring_site)
        else:
            df['cleaned_referring_site'] = 'N/A (Site Data Missing)'

        # --- Process Product Tags ---
        if 'product_tags' in df.columns:
            df[['product_tags_list', 'product_tags_compound']] = df['product_tags'].apply(
                lambda x: pd.Series(process_product_tags(x))
            )
            # IMPORTANT: Convert lists to tuples or strings to make them hashable for caching
            df['product_tags_list'] = df['product_tags_list'].apply(lambda x: tuple(x) if isinstance(x, list) else ())
        else:
            df['product_tags_list'] = [()] * len(df) # Use empty tuple
            df['product_tags_compound'] = "N/A (Tags Missing)"

        return df

    except Exception as e:
        st.error(f"Error loading order data from BigQuery: {e}")
        st.warning("Please ensure your `PROJECT_ID`, `DATASET_ID`, and `TABLE_ID` in `utils/data_loader.py` are correct.")
        st.info("Also, verify your Google Cloud authentication (via secrets) and BigQuery permissions for the specified table.")
        return pd.DataFrame()

# --- Helper Functions (No changes needed for caching, as they process dataframes) ---

def extract_status_from_tags(tags_string):
    """
    Extracts the status (e.g., 'processing', 'fulfilled') from a string
    like "status:processing, other_tag".
    """
    if pd.isna(tags_string) or not isinstance(tags_string, str):
        return None

    match = re.search(r'status:([a-zA-Z0-9_]+)', tags_string)
    if match:
        return match.group(1)
    return None

def advanced_clean_referring_site(url):
    """
    Cleans a referring site URL to extract a recognizable source name using
    a combination of specific rules and tldextract for robust domain parsing.
    """
    if pd.isna(url) or not isinstance(url, str) or not url.strip():
        return "Direct/Unknown"

    url_lower = url.lower() # Work with lowercase for easier matching

    # --- Step 1: Specific App Schemes and Non-Standard Prefixes ---
    if url_lower.startswith("android-app://"):
        if "com.google.android.gm" in url_lower:
            return "Google Mail App"
        elif "com.google.android.googlequicksearchbox" in url_lower:
            return "Google Search App"
        elif "com.facebook.katana" in url_lower:
            return "Facebook App"
        elif "com.instagram.android" in url_lower:
            return "Instagram App"
        return "Other Mobile App"
    
    # Remove leading numbers/non-protocol characters if present (e.g., '99https://')
    url_lower = re.sub(r'^\d+', '', url_lower) 
    
    # Prepend a dummy protocol if missing, to help urlparse and tldextract
    if not (url_lower.startswith("http://") or url_lower.startswith("https://")):
        url_lower = "http://" + url_lower 

    try:
        # --- Step 2: Specific Keyword/Domain Mappings (Prioritize these) ---
        # Your own store's domain variations
        if "theaffordableorganicstore.com" in url_lower or "affordableorganicstore.company.site" in url_lower:
            # Check for internal paths that might be clearer as "Internal Navigation"
            if "/apps/track" in url_lower or "/cart" in url_lower or "/my-account" in url_lower or "/shop/" in url_lower or "/search" in url_lower or "/collections/" in url_lower or "/products/" in url_lower or "/home/cart-taos/" in url_lower or "/pages/" in url_lower:
                return "The Affordable Organic Store (Internal)"
            
            # Handle Google Ads/Facebook Ads campaign URLs specifically for your site
            if "utm_source=facebook" in url_lower or "fbclid=" in url_lower or "gad_source=1" in url_lower or "campaign_id=" in url_lower:
                return "The Affordable Organic Store (Paid Ads)"
            
            return "The Affordable Organic Store" # Standardized main store name

        # Social Media
        if "instagram.com" in url_lower: # Catches l.instagram.com, instagram.com, etc.
            return "Instagram"
        if "facebook.com" in url_lower: # Catches l.facebook.com, m.facebook.com, lm.facebook.com, facebook.com, etc.
            return "Facebook"
        if "t.co" in url_lower: 
            return "Twitter"
        if "youtube.com" in url_lower or "youtu.be" in url_lower:
            return "YouTube"
        if "linkedin.com" in url_lower:
            return "LinkedIn"
        if "reddit.com" in url_lower:
            return "Reddit"
        if "meta.com" in url_lower:
            return "Meta"

        # Search Engines
        if "google.com" in url_lower:
            # Check if it's explicitly an ads domain or syndication
            if "googleads.g.doubleclick.net" in url_lower or "googlesyndication.com" in url_lower:
                return "Google Ads"
            
            # Check for organic search if relevant query parameters exist (e.g., 'q' or 's')
            query_params = parse_qs(urlparse(url_lower).query)
            if 'q' in query_params or 's' in query_params:
                return "Google Search"
            
            # If it's a direct Google URL without specific search/ads indicators
            return "Google Direct"
        
        if "brave.com" in url_lower:
            return "Brave"
        if "bing.com" in url_lower:
            return "Bing"
        if "ecosia.org" in url_lower:
            return "Ecosia"

        # Other Known Platforms/Services
        if "chatgpt.com" in url_lower:
            return "ChatGPT"
        if "shopify.com" in url_lower:
            return "Shopify Platform"
        if "webinvoke.paytmpayments.com" in url_lower:
            return "Webinvoke" 
        if "l.wl.co" in url_lower:
            return "WL Link"
        if "links.rediff.com" in url_lower:
            return "Rediff Links"
        if "idevaffiliate.com" in url_lower:
            return "iDevAffiliate"

        # --- Step 3: Use tldextract for robust generic domain extraction ---
        extracted = extract(url_lower)
        
        # Prioritize the domain if it's available from tldextract
        if extracted.domain:
            return extracted.domain.replace('-', ' ').title()
        
        # --- Fallback for URLs not handled by tldextract (e.g., malformed, internal IDs) ---
        parsed_url = urlparse(url_lower)
        domain = parsed_url.netloc

        if not domain: # If urlparse couldn't get a domain or it's just malformed text
            if re.match(r'^[a-f0-9]{32}$', url_lower):
                return "Internal ID/Tracker"
            return "Other (No Domain)"
        
        domain = re.sub(r'^(www|m|l)\.', '', domain) 
        parts = domain.split('.')
        if len(parts) >= 2:
            return parts[-2].replace('-', ' ').title() 
        
        return "Other (Generic Domain Fallback)"

    except Exception as e:
        # print(f"Error cleaning URL '{url}': {e}") # Uncomment for debugging
        return "Other (Error)"

def process_product_tags(tags_string):
    """
    Cleans, normalizes, and returns a sorted list of individual tags
    and a compound hyphen-separated string of tags.
    """
    if pd.isna(tags_string) or not isinstance(tags_string, str) or not tags_string.strip():
        return [], "Unknown Tag"

    cleaned_tags = [tag.strip().lower() for tag in tags_string.split(',') if tag.strip()]
    
    cleaned_tags.sort()

    compound_tag = "-".join(cleaned_tags) if cleaned_tags else "Unknown Tag"

    return cleaned_tags, compound_tag

def get_filtered_data(df, start_date, end_date):
    """Filters the DataFrame by order_date within the given range."""
    if not df.empty and 'order_date' in df.columns:
        df_filtered = df[(df['order_date'].dt.date >= start_date) & (df['order_date'].dt.date <= end_date)]
        return df_filtered
    return pd.DataFrame()

@st.cache_data(ttl=3600, show_spinner="Calculating RFM scores...")
def calculate_rfm(df_orders: pd.DataFrame, df_customers_master: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates RFM scores (Recency, Frequency, Monetary) for each customer
    based on order data and merges them into the customer master data.
    """
    # Ensure essential columns exist for RFM calculation
    required_order_cols = ['customer_id', 'order_date', 'total_order_value', 'order_id']
    if not all(col in df_orders.columns for col in required_order_cols):
        st.warning(f"Order data is missing one or more required columns for RFM calculation: {required_order_cols}. Skipping RFM calculation.")
        return df_customers_master # Return original if essential columns are missing

    # Drop NaNs for RFM calculation relevant columns
    df_orders_rfm = df_orders.dropna(subset=required_order_cols).copy()
    if df_orders_rfm.empty:
        st.warning("No valid order data after dropping NaNs for RFM calculation. Returning original customer master.")
        return df_customers_master

    # Determine the analysis date: one day after the latest order in the dataset
    max_order_date = df_orders_rfm['order_date'].max()
    analysis_date = max_order_date + pd.Timedelta(days=1) if pd.notna(max_order_date) else pd.Timestamp.now() # Use Timestamp for consistency

    # Calculate RFM metrics
    rfm_df = df_orders_rfm.groupby('customer_id').agg(
        Recency=('order_date', lambda date: (analysis_date - date.max()).days),
        Frequency=('order_id', 'nunique'), # Count unique orders
        Monetary=('total_order_value', 'sum') # Sum of total order value
    ).reset_index()

    rfm_df['R_Score'] = rfm_df['Recency'].rank(method='first', ascending=False).astype(int)

    rfm_df['F_Score'] = rfm_df['Frequency'].rank(method='first', ascending=True).astype(int)

    rfm_df['M_Score'] = rfm_df['Monetary'].rank(method='first', ascending=True).astype(int)

    # Normalize ranks to 1-5 scale (assuming at least 5 unique values or categories after rank)
    # This is a common way to scale ranks to a fixed number of bins (like 5)
    rfm_df['R_Score'] = pd.qcut(rfm_df['R_Score'], 5, labels=[1, 2, 3, 4, 5], duplicates='drop').astype(int)
    rfm_df['F_Score'] = pd.qcut(rfm_df['F_Score'], 5, labels=[1, 2, 3, 4, 5], duplicates='drop').astype(int)
    rfm_df['M_Score'] = pd.qcut(rfm_df['M_Score'], 5, labels=[1, 2, 3, 4, 5], duplicates='drop').astype(int)

    # Create RFM Score (combined R, F, M score for segmentation)
    rfm_df['RFM_Score'] = rfm_df['R_Score'].astype(str) + rfm_df['F_Score'].astype(str) + rfm_df['M_Score'].astype(str)

    # --- RFM Segmentation (common approach) ---
    def rfm_segment(row):
        if row['R_Score'] >= 4 and row['F_Score'] >= 4 and row['M_Score'] >= 4:
            return 'Champions' # Bought recently, buy often, spend a lot
        elif row['R_Score'] >= 4 and row['F_Score'] >= 3:
            return 'Loyal Customers' # Buy often, fairly recently
        elif row['R_Score'] >= 3 and row['F_Score'] >= 3 and row['M_Score'] >= 3:
            return 'Potential Loyalists' # Average scores, good potential
        elif row['R_Score'] >= 3 and row['F_Score'] < 3 and row['M_Score'] < 3:
            return 'Needs Attention' # Recent but low frequency/monetary
        elif row['R_Score'] <= 2 and row['F_Score'] >= 4:
            return 'At Risk' # Used to buy often, but not recently
        elif row['R_Score'] <= 2 and row['F_Score'] <= 2 and row['M_Score'] <= 2:
            return 'Churned' # Haven't bought recently, don't buy often, don't spend much
        elif row['R_Score'] >= 4 and row['F_Score'] <=2: # Catch new customers (high recency, low freq/monetary)
            return 'New Customers'
        else:
            return 'Other' # Catch-all for less common combinations

    rfm_df['RFM_Segment'] = rfm_df.apply(rfm_segment, axis=1)

    # Merge RFM data into the master customer DataFrame
    df_customers_master_with_rfm = df_customers_master.merge(rfm_df, on='customer_id', how='left')
    
    if 'Recency' in df_customers_master_with_rfm.columns:
        max_recency_val = df_customers_master_with_rfm['Recency'].max() if not df_customers_master_with_rfm['Recency'].empty else 365 # Default if no recency exists
        df_customers_master_with_rfm['Recency'] = df_customers_master_with_rfm['Recency'].fillna(max_recency_val + 30) # Assign high recency
    else:
        df_customers_master_with_rfm['Recency'] = 0 

    df_customers_master_with_rfm['Frequency'] = df_customers_master_with_rfm['Frequency'].fillna(0)
    df_customers_master_with_rfm['Monetary'] = df_customers_master_with_rfm['Monetary'].fillna(0)

    # Fill scores with 1 for customers with no orders (lowest score)
    df_customers_master_with_rfm['R_Score'] = df_customers_master_with_rfm['R_Score'].fillna(1).astype(int)
    df_customers_master_with_rfm['F_Score'] = df_customers_master_with_rfm['F_Score'].fillna(1).astype(int)
    df_customers_master_with_rfm['M_Score'] = df_customers_master_with_rfm['M_Score'].fillna(1).astype(int)
    df_customers_master_with_rfm['RFM_Score'] = df_customers_master_with_rfm['RFM_Score'].fillna('111') # Lowest RFM Score
    df_customers_master_with_rfm['RFM_Segment'] = df_customers_master_with_rfm['RFM_Segment'].fillna('New/Inactive') # Customers with no orders

    return df_customers_master_with_rfm

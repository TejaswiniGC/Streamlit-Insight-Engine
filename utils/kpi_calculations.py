import pandas as pd

def calculate_sales_kpis(df):
    """
    Calculates key sales performance indicators from the filtered DataFrame.
    Correctly handles total_order_value, discount, tax, and shipping amounts
    by using unique order IDs to avoid duplication.
    """
    if df.empty:
        return {
            "total_revenue": 0,
            "total_orders": 0,
            "average_order_value": 0,
            "total_discount_amount": 0,
            "total_tax_amount": 0,
            "total_shipping_cost": 0
        }

    # Ensure 'order_id' is present before proceeding
    if 'order_id' not in df.columns:
        raise ValueError("DataFrame must contain 'order_id' column for KPI calculations.")

    # Create a DataFrame with unique orders to correctly sum order-level metrics
    # Drop duplicates based on 'order_id' to get one row per unique order
    unique_orders_df = df.drop_duplicates(subset=['order_id'])

    # Calculate KPIs that are per-order (e.g., total_order_value, discount, tax, shipping)
    total_orders = unique_orders_df['order_id'].nunique() # This will be the same as len(unique_orders_df)
    total_revenue = unique_orders_df['total_order_value'].sum()
    average_order_value = total_revenue / total_orders if total_orders > 0 else 0

    # CORRECTED: Calculate discount, tax, and shipping from unique orders
    # These amounts are typically associated with the entire order, not individual line items
    total_discount_amount = unique_orders_df['discount_amount'].sum()
    total_tax_amount = unique_orders_df['tax_amount'].sum()
    total_shipping_cost = unique_orders_df['shipping_cost'].sum()


    return {
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "average_order_value": average_order_value,
        "total_discount_amount": total_discount_amount,
        "total_tax_amount": total_tax_amount,
        "total_shipping_cost": total_shipping_cost
    }

def get_daily_revenue_trend(df):
    """
    Calculates daily revenue trend, handling duplicate order IDs.
    """
    if df.empty:
        return pd.DataFrame()

    # Ensure 'order_date' and 'total_order_value' are present
    if 'order_date' not in df.columns or 'total_order_value' not in df.columns:
        raise ValueError("DataFrame must contain 'order_date' and 'total_order_value' columns for daily revenue trend.")

    unique_orders_daily = df.drop_duplicates(subset=['order_id']).copy()

    # Ensure 'order_date' is datetime before converting to date
    unique_orders_daily['order_date'] = pd.to_datetime(unique_orders_daily['order_date'], errors='coerce')
    unique_orders_daily.dropna(subset=['order_date'], inplace=True) # Drop rows where date conversion failed

    unique_orders_daily['order_day'] = unique_orders_daily['order_date'].dt.date

    daily_revenue = unique_orders_daily.groupby('order_day')['total_order_value'].sum().reset_index()
    daily_revenue.columns = ['Date', 'Revenue']
    daily_revenue = daily_revenue.sort_values('Date')
    return daily_revenue

def format_kpi_number(number):
    """
    Formats a large number into a human-readable string with K, M, B suffixes.
    Handles NaN values and ensures numerical operations before string formatting.
    """
    if pd.isna(number):
        return "N/A"

    try:
        num = float(number)
    except (ValueError, TypeError):
        return str(number)

    sign = "-" if num < 0 else ""
    abs_num = abs(num)

    if abs_num >= 1_000_000_000:
        return f"{sign}{abs_num / 1_000_000_000:.2f}B"
    elif abs_num >= 1_000_000:
        return f"{sign}{abs_num / 1_000_000:.2f}M"
    elif abs_num >= 1_000:
        if abs_num % 1000 == 0:
            return f"{sign}{int(abs_num / 1_000)}K"
        else:
            return f"{sign}{abs_num / 1_000:.1f}K"
    else:
        if abs_num == int(abs_num):
            return f"{sign}{int(abs_num):,}"
        else:
            return f"{sign}{abs_num:,.2f}"
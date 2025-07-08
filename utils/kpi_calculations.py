import pandas as pd

def calculate_sales_kpis(df):
    """
    Calculates key sales performance indicators from the filtered DataFrame.
    Assumes total_order_value in df is duplicated per product line item within an order.
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

    total_orders = df['order_id'].nunique()

    unique_orders_df = df.drop_duplicates(subset=['order_id'])

    total_revenue = unique_orders_df['total_order_value'].sum()
    
    average_order_value = total_revenue / total_orders if total_orders > 0 else 0

    total_discount_amount = df['discount_amount'].sum()
    total_tax_amount = df['tax_amount'].sum()
    total_shipping_cost = df['shipping_cost'].sum()


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

    unique_orders_daily = df.drop_duplicates(subset=['order_id']).copy()
    
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

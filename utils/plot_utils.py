import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
# import streamlit as st # Only uncomment if you use st.error/st.warning within this utility file

def plot_time_series(df, x_col, y_col, title, y_axis_title):
    """
    Generates an interactive line chart for time series data using Plotly,
    with a lightly shaded area below the line.
    Assumes df has datetime objects in x_col.
    """
    if df.empty:
        return None

    # Ensure x_col is datetime, if not already
    if not pd.api.types.is_datetime64_any_dtype(df[x_col]):
        try:
            df[x_col] = pd.to_datetime(df[x_col])
        except Exception as e:
            # If you want Streamlit warnings/errors here, uncomment 'import streamlit as st'
            # print(f"Error converting '{x_col}' to datetime in plot_time_series: {e}")
            return None

    fig = px.line(df, x=x_col, y=y_col,
                  title=title,
                  labels={x_col: "Date", y_col: y_axis_title},
                  template="plotly_white",
                  line_shape="linear" # Ensures a straight line connection
                 )

    # Set line color and fill color via update_traces
    fig.update_traces(
        fill='tozeroy',
        fillcolor='rgba(173, 216, 230, 0.3)', # Light blue with transparency
        line_color=px.colors.sequential.Blues[7] # Choose a distinct dark blue for the line
    )

    fig.update_xaxes(
        rangeselector=dict(
            buttons=list([
                dict(count=1, label="1m", step="month", stepmode="backward"),
                dict(count=6, label="6m", step="month", stepmode="backward"),
                dict(count=1, label="YTD", step="year", stepmode="todate"),
                dict(count=1, label="1y", step="year", stepmode="backward"),
                dict(step="all")
            ])
        ),
        rangeslider=dict(visible=False), # As per your request to hide it
        type="date"
    )

    fig.update_layout(hovermode="x unified")
    return fig

def plot_bar_chart(df, x_col, y_col, title, x_axis_title, y_axis_title, orientation='v'):
    """
    Generates an interactive bar chart using Plotly, with a blue gradient
    within each single bar, ranging from dark blue to a distinct light blue (not white).
    """
    if df.empty:
        return None

    # Force the gradient_within_bar logic for all bar charts as per new requirement
    gradient_within_bar = True

    # --- MODIFIED: Custom colorscale for the gradient within the bar ---
    # Define a custom list of blue colors using hex codes
    # This ensures the gradient stays within distinct blue shades and avoids white.
    custom_blue_colorscale = [
        '#87CEEB',
        "#5ABAE7",
        "#5ABAE7",
        "#41ADDF",
        "#0D7EB3",  
        "#054664",    
    ]
    colorscale = custom_blue_colorscale


    # Create a new DataFrame for the "gradient within bar" effect
    num_segments = 50 # Number of segments for the gradient (more segments = smoother but slower)
    gradient_dfs = []

    # Sort the original DataFrame based on y_col before processing,
    # to ensure bars are consistently ordered in the plot.
    if orientation == 'v':
        df_plot_order = df.sort_values(by=y_col, ascending=False)
    else: # 'h'
        df_plot_order = df.sort_values(by=y_col, ascending=True)


    for index, row in df_plot_order.iterrows():
        category = row[x_col]
        value = row[y_col]

        if value > 0:
            # Generate values for the gradient progression
            # Start slightly above 0 to avoid extremely dark/invisible first segment
            segment_cumulative_values = np.linspace(0.01 * value, value, num_segments)
            segment_lengths = np.diff(np.concatenate(([0], segment_cumulative_values)))

            temp_df = pd.DataFrame({
                x_col: [category] * num_segments,
                y_col: segment_lengths, # Each segment has a small length/height
                'gradient_value': segment_cumulative_values # This value determines the segment's color
            })
            gradient_dfs.append(temp_df)
        else:
            temp_df = pd.DataFrame({
                x_col: [category],
                y_col: [0],
                'gradient_value': [0]
            })
            gradient_dfs.append(temp_df)


    if not gradient_dfs:
        return None

    df_gradient = pd.concat(gradient_dfs).reset_index(drop=True)

    fig = go.Figure()

    original_categories_order = df_plot_order[x_col].tolist()


    for category in original_categories_order:
        df_cat_segments = df_gradient[df_gradient[x_col] == category].sort_values(by='gradient_value')

        original_total_value = df_plot_order.loc[df_plot_order[x_col] == category, y_col].iloc[0]

        custom_data_array = [original_total_value] * len(df_cat_segments)

        fig.add_trace(go.Bar(
            x=df_cat_segments[x_col] if orientation == 'v' else df_cat_segments[y_col],
            y=df_cat_segments[y_col] if orientation == 'v' else df_cat_segments[x_col],
            marker_color=df_cat_segments['gradient_value'], # Color each segment by its gradient_value
            marker_colorscale=colorscale, # Use the custom colorscale
            marker_line_width=0, # No lines between segments for a smooth look
            name=str(category),
            showlegend=False,
            orientation=orientation,
            customdata=custom_data_array,
            hovertemplate=
                f'<b>%{{x}}</b><br>{y_axis_title}: {original_total_value:,.2f}<extra></extra>'
                if orientation == 'v' else
                f'<b><b>%{{y}}</b><br>{y_axis_title}: {original_total_value:,.2f}<extra></extra>'
        ))

    # Define axis updates conditionally
    xaxis_update = {}
    yaxis_update = {}

    if orientation == 'h':
        yaxis_update = {'categoryorder': 'array', 'categoryarray': original_categories_order, 'title': x_axis_title}
        xaxis_update = {'title': y_axis_title}
    else: # orientation == 'v'
        xaxis_update = {'categoryorder': 'array', 'categoryarray': original_categories_order, 'title': x_axis_title}
        yaxis_update = {'title': y_axis_title}


    # Update layout for proper stacking and titles
    fig.update_layout(
        barmode='stack',
        title_text=title,
        template="plotly_white",
        hovermode="closest",
        xaxis=xaxis_update,
        yaxis=yaxis_update
    )

    return fig
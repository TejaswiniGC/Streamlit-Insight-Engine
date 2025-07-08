import streamlit as st
import pandas as pd
from utils.data_loader import load_ecommerce_data 

st.set_page_config(layout="wide", page_title="Raw Referring Sites Viewer", page_icon="🔍")

st.title("🔍 Raw Referring Sites Viewer")

st.markdown("""
This tool allows you to inspect the raw values of the 'referring_site' column
from your e-commerce data **before** any cleaning or standardization is applied.
This is useful for identifying patterns, inconsistencies, and new types of referring sites
that might need to be handled by the `clean_referring_site` function.
""")

# Load the raw e-commerce data
df_raw = load_ecommerce_data()

if df_raw.empty:
    st.error("E-commerce data could not be loaded. Please check your data source configuration.")
    st.stop()

if 'referring_site' not in df_raw.columns:
    st.error("The 'referring_site' column was not found in the loaded data.")
    st.stop()

st.subheader("Raw 'referring_site' Data Overview")

# Drop duplicates in referring_site to see unique raw values
unique_raw_sites = df_raw['referring_site'].dropna().astype(str).unique()

if unique_raw_sites.size > 0:
    st.write(f"Total unique raw referring sites: **{unique_raw_sites.size}**")
    
    st.info("Here are the top unique raw referring sites by their frequency:")
    
    # Calculate value counts of the raw referring_site column
    raw_site_counts = df_raw['referring_site'].dropna().astype(str).value_counts().reset_index()
    raw_site_counts.columns = ['Raw Referring Site', 'Count']
    
    st.dataframe(raw_site_counts, use_container_width=True)

    # Optional: Display all unique raw values if there aren't too many
    if unique_raw_sites.size < 500: # Limit for display to avoid overwhelming the page
        st.subheader("All Unique Raw Referring Sites (Sorted Alphabetically)")
        st.write(sorted(list(unique_raw_sites)))
    else:
        st.info("Too many unique raw referring sites to display all. Showing top frequencies above.")

    st.subheader("Search Raw Referring Sites")
    search_term = st.text_input("Enter a keyword to search for in raw referring sites (e.g., 'instagram', 'google', 'theaffordable')", "").lower()

    if search_term:
        filtered_raw_sites = [site for site in unique_raw_sites if search_term in site.lower()]
        if filtered_raw_sites:
            st.write(f"Found {len(filtered_raw_sites)} raw sites containing '{search_term}':")
            for site in sorted(filtered_raw_sites):
                st.write(f"- {site}")
        else:
            st.info(f"No raw referring sites found containing '{search_term}'.")
else:
    st.info("No raw 'referring_site' data available (or all values are missing/empty).")

st.markdown("---")
st.markdown("Once you identify patterns here, you can update the `clean_referring_site` function in `utils/data_loader.py` to standardize them.")

import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from dash import html
from scipy import stats
from database import fetch_data_from_sql
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv(override=True)

# Get main table
table_options = os.getenv("TABLE_OPTIONS", "").split(",")
default_table = os.getenv("MAIN_TABLE")

table_options_names = {
    "db_main": "Database Main",
    "budburst_date1": "Budburst Date 1",
    "budburst_detailed_all": "Budburst Detailed All",
    "biomass_2021_combined_fordb_052224": "Biomass",
    "leaf_traits_2016": "Leaf Traits",
    "dat_climdb": "Tree Climate Data",
    "dat_cgp_db": "Garden Temperatures"
}

def create_database_Table(num, selected_columns=None, row_count=20):
    if num is None or num < 0 or num >= len(table_options):
        return go.Figure()  # Return empty figure if index is invalid

    selected_table = table_options[num]
    table_name = table_options_names.get(selected_table, selected_table)   

    try:
        # Use the row_count parameter to limit the number of rows
        db_df = fetch_data_from_sql(f"SELECT TOP {row_count} * FROM [dbo].[{selected_table}]")
    except Exception as e:
        print(f"Error fetching data from table {selected_table}: {e}")
        return go.Figure()  # Return an empty figure if query fails

    # Filter selected columns
    if selected_columns:
        db_df = db_df[selected_columns]  # Show only selected columns

    # Calculate if horizontal scrolling is needed (if more than 15 columns)
    enable_scrolling = len(db_df.columns) > 15
    
    # Set fixed column width for better readability when scrolling
    column_width = 150 if enable_scrolling else None
    
    # Create the table figure
    fig = go.Figure(data=[go.Table(
        header=dict(
            values=db_df.columns,
            align='left',
            fill_color='#d1d1d1',
            font=dict(color='black', size=12),
            height=30
        ),
        cells=dict(
            values=db_df.values.T,
            align='left',
            fill_color='#f9f9f9',
            font=dict(color='black', size=11),
            height=25
        ),
        columnwidth=column_width 
    )])
    
    # Update layout with improved styling
    fig.update_layout(
        paper_bgcolor="#e5ecf6", 
        plot_bgcolor="#e5ecf6",
        margin={"t":40, "l":0, "r":0, "b":0},  
        height=min(600, 150 + len(db_df) * 25),  
        title={
            'text': f"Showing {len(db_df)} rows from {table_name}",
            'y':0.98,
            'x':0.5,
            'xanchor': 'center',
            'yanchor': 'top'
        },
        autosize=True
    )
    
    # Add horizontal scrolling settings when needed
    if enable_scrolling:
        total_width = len(db_df.columns) * 150
        fig.update_layout(
            width=total_width,
            xaxis=dict(
                rangeslider=dict(visible=True),
                automargin=True
            )
        )
    
    return fig
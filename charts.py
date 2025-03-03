import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from dash import html
from scipy import stats
from plotly.data import gapminder
from database import fetch_data_from_sql
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Get main table
table_options = os.getenv("TABLE_OPTIONS", "").split(",")

default_table = os.getenv("MAIN_TABLE")

gapminder_df = gapminder(datetimes=True, centroids=True, pretty_names=True)
gapminder_df["Year"] = gapminder_df.Year.dt.year

db_df = fetch_data_from_sql(f"SELECT TOP 20 * FROM [dbo].[{default_table}]")

def create_database_Table(num, selected_columns=None):
    """Generates a table figure dynamically based on the selected table index and columns."""
    if num is None or num < 0 or num >= len(table_options):
        return go.Figure()  # Return empty figure if index is invalid

    selected_table = table_options[num]
    
    try:
        db_df = fetch_data_from_sql(f"SELECT TOP 20 * FROM [dbo].[{selected_table}]")
    except Exception as e:
        print(f"Error fetching data from table {selected_table}: {e}")
        return go.Figure()  # Return an empty figure if query fails

    # Filter selected columns
    if selected_columns:
        db_df = db_df[selected_columns]  # Show only selected columns

    fig = go.Figure(data=[go.Table(
        header=dict(values=db_df.columns, align='left'),
        cells=dict(values=db_df.values.T, align='left'))])
    fig.update_layout(paper_bgcolor="#e5ecf6", margin={"t":0, "l":0, "r":0, "b":0}, height=700)
    
    return fig

# Stats page charts
def create_stats_chart(selected_column):
    if not selected_column:
         return px.histogram()
    
    if selected_column not in db_df.columns:
         raise ValueError(f"Column '{selected_column}' not found in data frame.")
    
    filtered_df = db_df[~db_df[selected_column].isna()].copy()

    fig = px.histogram(filtered_df, x=selected_column,
                      title=f"Distribution of {selected_column}")

    fig.update_layout(paper_bgcolor="#e5ecf6", height=600)
    return fig

def create_summary_statistics(selected_column):
    if not selected_column:
         return None
    if selected_column not in db_df.columns:
         raise ValueError(f"Column '{selected_column}' not found in data frame.")
    
    filtered_df = db_df[selected_column].dropna()

    mean_value = round(float(filtered_df.mean()), 2)
    median_value = round(float(filtered_df.median()), 0)
    std_value = round(float(filtered_df.std()), 2)
    min_value = round(float(filtered_df.min()), 0)
    max_value = round(float(filtered_df.max()), 0)
    num_obs = len(filtered_df)

    summary_statistics = {
        "columns" : ["Metric", "Value"],
        "data": [
            ["Mean", mean_value],
            ["Median", median_value],
            ["Standard Deviation", std_value],
            ["Minimum", min_value], 
            ["Maximum", max_value], 
            ["Number of observations", num_obs]
        ]
    }
    return summary_statistics

def create_summary_table(summary_stats): # create summary table 
        summary_table = html.Div([
            html.H4("Summary Statistics", style={"textAlign":"center", "fontSize":"24px", "marginBottom":"10px"}),
            html.Table([
                html.Thead(html.Tr([html.Th(col) for col in summary_stats["columns"]])),
                html.Tbody([
                    html.Tr([html.Td(value) for value in row]) for row in summary_stats["data"]
                ])
            ], style={
                "width": "70%",  
                "margin": "auto",  
                "borderCollapse": "collapse",  
                "borderRadius": "10px",  
                "overflow": "hidden",  
                "backgroundColor": "#f9f9f9"
            })
        ])
        return summary_table

def create_lr_chart(selected_column_1, selected_column_2):
    if not selected_column_1 or not selected_column_2:
        return px.scatter()
    
    if selected_column_1 not in db_df.columns or selected_column_2 not in db_df.columns:
        raise ValueError(f"One or more selected columns not found in data frame.")
    
    filtered_df = db_df[~(db_df[selected_column_1].isna() | db_df[selected_column_2].isna())].copy()
    
    x = filtered_df[selected_column_1]
    y = filtered_df[selected_column_2]
    slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
    
    x_range = np.linspace(x.min(), x.max(), 100)
    y_predicted = slope * x_range + intercept

    fig = px.scatter(filtered_df, x=selected_column_1, y=selected_column_2,
                    title=f"Linear Regression: {selected_column_2} vs {selected_column_1}")
    
    fig.add_scatter(x=x_range, y=y_predicted, mode='lines', name='Regression Line',
                   line=dict(color='red'))
    
    r_squared = r_value ** 2
    eq_text = f"y = {slope:.2f}x + {intercept:.2f}"
    r2_text = f"R² = {r_squared:.3f}"
    fig.update_layout(
        title=f"Linear Regression: {selected_column_2} vs {selected_column_1}<br><sub>{eq_text} | {r2_text}</sub>",
        paper_bgcolor="#e5ecf6",
        height=600,
        xaxis_title=selected_column_1,
        yaxis_title=selected_column_2,
        showlegend=True
    )
    
    return fig
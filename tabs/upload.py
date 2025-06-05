from dash import dcc, html, Input, Output, State, callback, dash_table, ctx
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
import dash
import pandas as pd
import io
import base64
from database import fetch_data_from_sql
from dotenv import load_dotenv
import os
import sqlalchemy
from sqlalchemy import create_engine

# Load environment variables
load_dotenv(override=True)

# Table Options
table_options = os.getenv("TABLE_OPTIONS").split(",")

# Database connection settings from environment variables
driver = "ODBC Driver 17 for SQL Server"
server = os.getenv("DB_SERVER")
database = os.getenv("DB_DATABASE")
username = os.getenv("DB_USERNAME")
password = os.getenv("DB_PASSWORD")

# SQL Alchemy connection string
connection_string = (
    f"mssql+pyodbc://{username}:{password}@{server}/{database}"
    f"?driver={driver}&Encrypt=yes&TrustServerCertificate=yes"
)

upload_layout = dcc.Tab(
    [
        # Store the tab's active state
        dcc.Store(id="upload-tab-active", data=False),
        html.Br(),
        html.H4("Upload CSV File to Database", style={"marginBottom": "20px"}),
        
        # Table selection
        html.Label("Select target table:", style={"fontWeight": "bold", "marginBottom": "5px", "fontSize": "16px"}),
        dcc.Dropdown(table_options, id="upload_table_dropdown", placeholder="Select a table"),
        
        html.Div([
            # File upload component
            html.Div([
                html.Label("Upload CSV file:", style={"fontWeight": "bold", "marginTop": "20px", "marginBottom": "10px"}),
                dcc.Upload(
                    id='upload-csv',
                    children=html.Div([
                        html.A('Drag and Drop or ', style={"textDecoration": "underline"}),
                        html.A('Select a CSV File')
                    ]),
                    style={
                        'width': '100%',
                        'height': '60px',
                        'lineHeight': '60px',
                        'borderWidth': '1px',
                        'borderStyle': 'dashed',
                        'borderRadius': '5px',
                        'textAlign': 'center',
                        'backgroundColor': '#f9f9f9',
                        'margin': '10px 0'
                    },
                    multiple=False
                ),
            ]),
            
            # Table structure information
            html.Div(id="table-structure-info", style={"marginTop": "20px"}),
            
            # Upload result or validation errors
            html.Div(id="upload-status", style={"marginTop": "20px"}),
            
            # CSV preview
            html.Div(id="csv-preview", style={"marginTop": "20px"}),
            
            # Upload button
            html.Div([
                html.Button("Upload to Database", 
                           id="upload-button", 
                           disabled=True,
                           style={"marginTop": "20px", 
                                 "padding": "10px 20px", 
                                 "backgroundColor": "#007bff", 
                                 "color": "white", 
                                 "border": "none", 
                                 "borderRadius": "4px",
                                 "cursor": "pointer"}
                          )
            ]),
            
            # Upload result
            html.Div(id="upload-result", style={"marginTop": "20px"})
            
        ], id="upload-container", style={"display": "none"})
    ],
    label="Tab 5",
    id="upload-tab",
    style={"padding": "15px"}
)

# Track tab selection state
@callback(
    Output('upload-tab-active', 'data'),
    [Input('main-tabs', 'value')]
)
def set_upload_tab_active(tab_value):
    return tab_value == 'upload-tab'

# Reset when tab is switched
@callback(
    [Output('upload_table_dropdown', 'value', allow_duplicate=True),
     Output('upload-csv', 'contents', allow_duplicate=True),
     Output('upload-button', 'disabled', allow_duplicate=True),
     Output('table-structure-info', 'children', allow_duplicate=True),
     Output('upload-status', 'children', allow_duplicate=True),
     Output('csv-preview', 'children', allow_duplicate=True),
     Output('upload-result', 'children', allow_duplicate=True),
     Output('upload-container', 'style', allow_duplicate=True)],
    [Input('upload-tab-active', 'data')],
    prevent_initial_call=True
)
def reset_upload_tab_data(is_active):
    if not is_active:
        # Reset all controls when leaving the tab
        return None, None, True, [], [], [], [], {"display": "none"}
    else:
        # Don't reset when entering the tab
        return [dash.no_update] * 8

# Callback to show upload container when table is selected
@callback(
    Output("upload-container", "style"),
    Input("upload_table_dropdown", "value")
)
def show_upload_container(selected_table):
    if selected_table:
        return {"display": "block"}
    return {"display": "none"}

# Callback to display table structure information
@callback(
    Output("table-structure-info", "children"),
    Input("upload_table_dropdown", "value")
)
def display_table_structure(selected_table):
    if not selected_table:
        return []
    
    try:
        # Get a sample row to determine columns and types
        sample_df = fetch_data_from_sql(f"SELECT TOP 1 * FROM [dbo].[{selected_table}]")
        
        # Get column details
        columns = sample_df.columns.tolist()
        dtypes = sample_df.dtypes.to_dict()
        
        # Create table structure information
        structure_info = [
            html.H5("Table Structure", style={"marginBottom": "10px"}),
            html.P(f"This table has {len(columns)} columns:", style={"marginBottom": "5px"}),
            html.Div([
                dash_table.DataTable(
                    data=[{"Column": col, "Data Type": str(dtypes[col])} for col in columns],
                    columns=[
                        {"name": "Column", "id": "Column"},
                        {"name": "Data Type", "id": "Data Type"}
                    ],
                    style_table={'overflowX': 'auto'},
                    style_cell={
                        'textAlign': 'left',
                        'padding': '8px',
                        'minWidth': '100px',
                    },
                    style_header={
                        'backgroundColor': '#d1d1d1',
                        'fontWeight': 'bold'
                    },
                )
            ])
        ]
        
        return structure_info
    except Exception as e:
        return html.Div([
            html.H5("Error Retrieving Table Structure", style={"color": "red"}),
            html.P(str(e))
        ])

# Function to parse CSV content
def parse_csv(contents):
    if contents is None:
        return None, None
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    
    try:
        df = pd.read_csv(io.StringIO(decoded.decode('utf-8')))
        return df, None
    except Exception as e:
        return None, f"Error parsing CSV: {str(e)}"

# Callback to validate CSV file and display preview
@callback(
    [Output("csv-preview", "children"),
     Output("upload-status", "children"),
     Output("upload-button", "disabled")],
    [Input("upload-csv", "contents"),
     Input("upload_table_dropdown", "value")],
    [State("upload-csv", "filename")]
)
def validate_and_preview_csv(contents, selected_table, filename):
    if contents is None or selected_table is None:
        return [], [], True
    
    try:
        # Get table structure from database
        sample_df = fetch_data_from_sql(f"SELECT TOP 1 * FROM [dbo].[{selected_table}]")
        table_columns = sample_df.columns.tolist()
        
        # Parse the uploaded CSV
        df, error = parse_csv(contents)
        if error:
            return [], html.Div([
                html.H5("Error", style={"color": "red"}),
                html.P(error)
            ]), True
        
        # Verify column count matches
        if len(df.columns) != len(table_columns):
            return get_preview_table(df), html.Div([
                html.H5("Validation Error", style={"color": "red"}),
                html.P(f"CSV file has {len(df.columns)} columns, but the database table has {len(table_columns)} columns."),
                html.P("Column counts must match to proceed.")
            ]), True
        
        # Check for consistent row lengths (all rows have same number of columns)
        if df.isnull().any(axis=1).sum() > 0:
            # Some rows have missing values, but we'll convert them to None/NULL on upload
            warning = html.Div([
                html.H5("Warning", style={"color": "orange"}),
                html.P(f"CSV file has some rows with missing values. These will be converted to NULL in the database."),
                html.P("Preview below shows data as it will be uploaded.")
            ])
        else:
            warning = html.Div([
                html.H5("Validation Successful", style={"color": "green"}),
                html.P(f"CSV file with {len(df)} rows is ready to upload to table '{selected_table}'.")
            ])
        
        return get_preview_table(df), warning, False
        
    except Exception as e:
        return [], html.Div([
            html.H5("Error", style={"color": "red"}),
            html.P(str(e))
        ]), True

# Helper function to create preview table
def get_preview_table(df):
    preview_rows = min(5, len(df))
    df_preview = df.head(preview_rows)
    
    return [
        html.H5("CSV Preview", style={"marginBottom": "10px"}),
        html.P(f"Showing first {preview_rows} of {len(df)} rows:", style={"marginBottom": "5px"}),
        dash_table.DataTable(
            data=df_preview.to_dict('records'),
            columns=[{"name": str(i), "id": str(i)} for i in df_preview.columns],
            style_table={'overflowX': 'auto'},
            style_cell={
                'textAlign': 'left',
                'padding': '8px',
                'minWidth': '100px',
                'maxWidth': '200px',
                'overflow': 'hidden',
                'textOverflow': 'ellipsis',
            },
            style_header={
                'backgroundColor': '#d1d1d1',
                'fontWeight': 'bold'
            },
            tooltip_delay=0,
            tooltip_duration=None,
            page_size=10,
        )
    ]
"""
# Callback to handle database upload
@callback(
    Output("upload-result", "children"),
    [Input("upload-button", "n_clicks")],
    [State("upload-csv", "contents"),
     State("upload_table_dropdown", "value"),
     State("upload-csv", "filename")]
)
def upload_to_database(n_clicks, contents, selected_table, filename):
    if n_clicks is None or contents is None or selected_table is None:
        raise PreventUpdate
    
    try:
        # Parse the uploaded CSV
        df, error = parse_csv(contents)
        if error:
            return html.Div([
                html.H5("Upload Error", style={"color": "red"}),
                html.P(error)
            ])
        
        # Get table structure
        sample_df = fetch_data_from_sql(f"SELECT TOP 1 * FROM [dbo].[{selected_table}]")
        table_columns = sample_df.columns.tolist()
        
        # Rename CSV columns to match database columns
        if len(df.columns) == len(table_columns):
            df.columns = table_columns
        
        # Create database connection
        engine = create_engine(connection_string, fast_executemany=True)
        
        # Upload data to the database
        with engine.begin() as connection:
            df.to_sql(selected_table, connection, if_exists='append', index=False, schema='dbo')
        
        return html.Div([
            html.H5("Upload Successful", style={"color": "green"}),
            html.P(f"Successfully uploaded {len(df)} rows to table '{selected_table}'.")
        ])
        
    except Exception as e:
        return html.Div([
            html.H5("Upload Error", style={"color": "red"}),
            html.P(str(e))
        ])
"""
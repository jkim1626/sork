import dash
from dash import dcc, html, Input, Output, State, callback, dash_table, ctx
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
import pandas as pd
from io import StringIO
import base64
from database import fetch_data_from_sql
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv(override=True)

# Table Options
table_options = os.getenv("TABLE_OPTIONS").split(",")

download_layout = dcc.Tab(
    [
        # Store the tab's active state
        dcc.Store(id="download-tab-active", data=False),
        html.Br(),
        html.H4("Download Data as CSV", style={"marginBottom": "20px"}),
        
        # Table selection
        html.Label("Select source table:", style={"fontWeight": "bold", "marginBottom": "5px", "fontSize": "16px"}),
        dcc.Dropdown(table_options, id="download_table_dropdown", placeholder="Select a table"),
        
        html.Div([
            # Row range selection
            html.Div([
                html.Label("Row Range Selection", style={"fontWeight": "bold", "marginTop": "20px", "marginBottom": "10px"}),
                html.Div([
                    html.Div([
                        html.Label("Start Row:"),
                        dcc.Input(
                            id="download-start-row",
                            type="number",
                            min=1,
                            value=1,
                            style={"width": "100px", "marginRight": "20px"}
                        ),
                    ], style={"display": "inline-block", "marginRight": "20px"}),
                    
                    html.Div([
                        html.Label("End Row:"),
                        dcc.Input(
                            id="download-end-row",
                            type="number",
                            min=1,
                            value=100,
                            style={"width": "100px"}
                        ),
                    ], style={"display": "inline-block", "marginRight": "20px"}),
                    
                    html.Div([
                        html.Label(""),  # Empty label for alignment
                        html.Button(
                            "Preview Data", 
                            id="preview-button",
                            style={
                                "marginTop": "22px",
                                "padding": "8px 15px",
                                "backgroundColor": "#6c757d",
                                "color": "white",
                                "border": "none",
                                "borderRadius": "4px",
                                "cursor": "pointer"
                            }
                        )
                    ], style={"display": "inline-block"})
                ]),
                
                # Row count info
                html.Div(id="download-row-info", style={"marginTop": "10px", "color": "#666"})
            ]),
            
            # Column selection
            html.Div([
                html.Label("Select columns to include:", style={"fontWeight": "bold", "marginTop": "20px", "marginBottom": "10px"}),
                html.Div([
                    html.Button("Select All", id="download-select-all-btn", n_clicks=0, 
                               style={"marginRight": "10px", "fontSize": "0.8em"}),
                    html.Button("Deselect All", id="download-deselect-all-btn", n_clicks=0, 
                               style={"fontSize": "0.8em"}),
                ], style={"marginBottom": "10px"}),
                html.Div(
                    dcc.Checklist(
                        id="download-columns",
                        options=[],
                        value=[],
                        inline=False,
                        labelStyle={"display": "block", "marginBottom": "3px"},
                        style={"maxHeight": "200px", "overflowY": "auto", "padding": "10px", "backgroundColor": "#f9f9f9", "borderRadius": "5px"}
                    )
                )
            ]),
            
            # Data preview
            html.Div([
                html.H5("Data Preview", style={"marginTop": "20px", "marginBottom": "10px"}),
                html.Div(id="download-preview")
            ]),
            
            # Download button
            html.Div([
                html.Button(
                    "Download CSV", 
                    id="download-button",
                    style={
                        "marginTop": "20px",
                        "padding": "10px 20px",
                        "backgroundColor": "#28a745",
                        "color": "white",
                        "border": "none",
                        "borderRadius": "4px",
                        "cursor": "pointer"
                    }
                ),
                dcc.Download(id="download-dataframe-csv"),
            ])
        ], id="download-container", style={"display": "none"})
    ],
    label="Tab 6",
    id="download-tab",
    style={"padding": "15px"}
)

# Track tab selection state
@callback(
    Output('download-tab-active', 'data'),
    [Input('main-tabs', 'value')]
)
def set_download_tab_active(tab_value):
    return tab_value == 'download-tab'

# Reset when tab is switched
@callback(
    [Output('download_table_dropdown', 'value', allow_duplicate=True),
     Output('download-start-row', 'value', allow_duplicate=True),
     Output('download-end-row', 'value', allow_duplicate=True),
     Output('download-columns', 'options', allow_duplicate=True),
     Output('download-columns', 'value', allow_duplicate=True),
     Output('download-row-info', 'children', allow_duplicate=True),
     Output('download-preview', 'children', allow_duplicate=True),
     Output('download-container', 'style', allow_duplicate=True)],
    [Input('download-tab-active', 'data')],
    prevent_initial_call=True
)
def reset_download_tab_data(is_active):
    if not is_active:
        # Reset all controls when leaving the tab
        return None, 1, 100, [], [], "", [], {"display": "none"}
    else:
        # Don't reset when entering the tab
        return [dash.no_update] * 8

# Callback to show download container when table is selected
@callback(
    Output("download-container", "style"),
    Input("download_table_dropdown", "value")
)
def show_download_container(selected_table):
    if selected_table:
        return {"display": "block"}
    return {"display": "none"}

# Callback to get columns and row info
@callback(
    [Output("download-columns", "options"),
     Output("download-columns", "value"),
     Output("download-row-info", "children"),
     Output("download-end-row", "max")],
    [Input("download_table_dropdown", "value")]
)
def update_column_options(selected_table):
    if not selected_table:
        return [], [], "", 100
    
    try:
        # Get a sample row to determine columns
        sample_df = fetch_data_from_sql(f"SELECT TOP 1 * FROM [dbo].[{selected_table}]")
        columns = sample_df.columns.tolist()
        column_options = [{'label': col, 'value': col} for col in columns]
        
        # Get total row count
        count_query = f"SELECT COUNT(*) AS row_count FROM [dbo].[{selected_table}]"
        count_df = fetch_data_from_sql(count_query)
        total_rows = count_df.iloc[0]['row_count']
        
        row_info = f"This table contains {total_rows} rows in total."
        
        # Return all columns selected by default
        return column_options, columns, row_info, total_rows
    except Exception as e:
        return [], [], f"Error: {str(e)}", 100

# Callback to handle select/deselect all columns
@callback(
    Output("download-columns", "value", allow_duplicate=True),
    [Input("download-select-all-btn", "n_clicks"),
     Input("download-deselect-all-btn", "n_clicks")],
    [State("download-columns", "options"),
     State("download-columns", "value")],
    prevent_initial_call=True
)
def handle_column_selection(select_all, deselect_all, options, current_values):
    triggered_id = ctx.triggered_id if ctx.triggered_id else 'no-id'
    
    if triggered_id == "download-select-all-btn":
        return [option["value"] for option in options]
    elif triggered_id == "download-deselect-all-btn":
        return []
    
    return current_values

# Callback to show data preview
@callback(
    Output("download-preview", "children"),
    [Input("preview-button", "n_clicks"),
     Input("download_table_dropdown", "value")],
    [State("download-start-row", "value"),
     State("download-end-row", "value"),
     State("download-columns", "value")]
)
def update_preview(n_clicks, selected_table, start_row, end_row, selected_columns):
    if not selected_table or not selected_columns:
        return html.P("Select a table, columns, and row range, then click 'Preview Data'.")
    
    # Default values if not provided
    if not start_row or start_row < 1:
        start_row = 1
    
    if not end_row or end_row < start_row:
        end_row = start_row + 99  # Default to 100 rows
    
    # Calculate offsets for SQL query
    row_count = end_row - start_row + 1
    offset = start_row - 1
    
    try:
        # Build the column list for the query
        column_list = ", ".join([f"[{col}]" for col in selected_columns])
        
        # Query with pagination
        query = f"""
        SELECT {column_list} 
        FROM [dbo].[{selected_table}]
        ORDER BY (SELECT NULL)
        OFFSET {offset} ROWS
        FETCH NEXT {min(row_count, 100)} ROWS ONLY
        """
        
        preview_df = fetch_data_from_sql(query)
        
        # Only show up to 10 rows in preview
        display_rows = min(10, len(preview_df))
        preview_df_display = preview_df.head(display_rows)
        
        return [
            html.P(f"Showing {display_rows} of {len(preview_df)} rows (from row {start_row} to {start_row + len(preview_df) - 1}):", 
                  style={"marginBottom": "5px"}),
            dash_table.DataTable(
                data=preview_df_display.to_dict('records'),
                columns=[{"name": str(i), "id": str(i)} for i in preview_df_display.columns],
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
    except Exception as e:
        return html.Div([
            html.P("Error generating preview:", style={"color": "red"}),
            html.Pre(str(e), style={"backgroundColor": "#f8d7da", "padding": "10px", "borderRadius": "5px"})
        ])

# Callback to download CSV data
@callback(
    Output("download-dataframe-csv", "data"),
    [Input("download-button", "n_clicks")],
    [State("download_table_dropdown", "value"),
     State("download-start-row", "value"),
     State("download-end-row", "value"),
     State("download-columns", "value")]
)
def download_csv(n_clicks, selected_table, start_row, end_row, selected_columns):
    if n_clicks is None or not selected_table or not selected_columns:
        raise PreventUpdate
    
    # Default values if not provided
    if not start_row or start_row < 1:
        start_row = 1
    
    if not end_row or end_row < start_row:
        end_row = start_row + 999  # Default to 1000 rows
    
    # Calculate offsets for SQL query
    row_count = end_row - start_row + 1
    offset = start_row - 1
    
    try:
        # Build the column list for the query
        column_list = ", ".join([f"[{col}]" for col in selected_columns])
        
        # Query with pagination
        query = f"""
        SELECT {column_list} 
        FROM [dbo].[{selected_table}]
        ORDER BY (SELECT NULL)
        OFFSET {offset} ROWS
        FETCH NEXT {row_count} ROWS ONLY
        """
        
        df = fetch_data_from_sql(query)
        
        # Return the data as a CSV download
        return dcc.send_data_frame(df.to_csv, f"{selected_table}_rows_{start_row}_to_{end_row}.csv", index=False)
    except Exception as e:
        # In case of error, we need to return something to prevent the callback from failing
        # But there's no good way to show errors in a download callback
        # So we'll return a small CSV with the error message
        error_df = pd.DataFrame({'Error': [str(e)]})
        return dcc.send_data_frame(error_df.to_csv, "error.csv", index=False)
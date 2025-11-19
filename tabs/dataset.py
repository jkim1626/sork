from dash import dcc, html, Input, Output, State, callback, ctx, ALL, MATCH, dash_table, ClientsideFunction
import dash_bootstrap_components as dbc
import dash
#from charts import create_database_Table
from dotenv import load_dotenv
from database import fetch_data_from_sql
from tabs.joins import joins_layout
import os
import pandas as pd
from pandas.api.types import is_numeric_dtype
import plotly.express as px
import json
import uuid
from cache_config import cache

# Load environment variables
load_dotenv(override=True)

@cache.memoize(timeout=3600)
def store_large_df(key, df_dict):
    print("Storing to cache with key:", key)
    cache.set(key, df_dict, timeout=3600)

# Table Options
table_options = os.getenv("TABLE_OPTIONS").split(",")

joins_layout_dataset = html.Div([
            # Left side - Join configuration
            html.Div([
                # First table selection
                html.Div([
                    html.Label("Step 1: Select first table", style={"fontWeight": "bold", "marginBottom": "5px"}),
                    dcc.Dropdown(
                        id="first-table-dropdown",
                        options=[{"label": table, "value": table} for table in table_options],
                        placeholder="Select first table"
                    ),
                ], style={"marginBottom": "15px"}),
                
                # Join type selection
                html.Div([
                    html.Label("Step 2: Select join type", style={"fontWeight": "bold", "marginBottom": "5px"}),
                    dcc.Dropdown(
                        id="join-type-dropdown",
                        options=[
                            {"label": "Inner Join", "value": "inner"},
                            {"label": "Left Join", "value": "left"},
                            {"label": "Right Join", "value": "right"},
                            {"label": "Full Outer Join", "value": "full"},
                        ],
                        placeholder="Select join type"
                    ),
                    html.Div([
                        html.Img(src="https://i.imgur.com/1sxnQ4j.png", style={"width": "100%", "marginTop": "10px"}),
                        html.P("Join visualization", style={"textAlign": "center", "color": "#666", "fontSize": "0.8em"})
                    ], id="join-visualization", style={"display": "none", "marginTop": "10px"})
                ], style={"marginBottom": "15px"}),
                
                # Second table selection
                html.Div([
                    html.Label("Step 3: Select second table", style={"fontWeight": "bold", "marginBottom": "5px"}),
                    dcc.Dropdown(
                        id="second-table-dropdown",
                        options=[{"label": table, "value": table} for table in table_options],
                        placeholder="Select second table"
                    ),
                ], style={"marginBottom": "15px"}),
                
                # Join key selection
                html.Div([
                    html.Label("Step 4: Select join keys", style={"fontWeight": "bold", "marginBottom": "5px"}),
                    html.Div([
                        html.Div([
                            html.Label("Key in first table:", style={"marginBottom": "5px"}),
                            dcc.Dropdown(id="first-table-key", placeholder="Select column")
                        ], style={"width": "48%"}),
                        html.Div([
                            html.Label("Key in second table:", style={"marginBottom": "5px"}),
                            dcc.Dropdown(id="second-table-key", placeholder="Select column")
                        ], style={"width": "48%"}),
                    ], style={"display": "flex", "justifyContent": "space-between"}),
                ], id="join-keys-div", style={"display": "none", "marginBottom": "15px"}),
                
                # Column selection
                html.Div([
                    html.Label("Step 5: Select columns to include", style={"fontWeight": "bold", "marginBottom": "5px"}),
                    html.Div([
                        html.Div([
                            html.Label("First table columns:", style={"marginBottom": "5px"}),
                            html.Button("Select All", id="first-table-select-all", n_clicks=0, 
                                       style={"marginLeft": "10px", "fontSize": "0.8em"}),
                            html.Button("Deselect All", id="first-table-deselect-all", n_clicks=0, 
                                       style={"marginLeft": "10px", "fontSize": "0.8em"})
                        ], style={"display": "flex", "alignItems": "center", "marginBottom": "5px"}),
                        dcc.Checklist(
                            id="first-table-columns",
                            options=[],
                            value=[],
                            style={"maxHeight": "150px", "overflowY": "auto", "padding": "10px", 
                                  "backgroundColor": "#f9f9f9", "borderRadius": "5px"}
                        )
                    ], style={"marginBottom": "10px"}),
                    html.Div([
                        html.Div([
                            html.Label("Second table columns:", style={"marginBottom": "5px"}),
                            html.Button("Select All", id="second-table-select-all", n_clicks=0, 
                                       style={"marginLeft": "10px", "fontSize": "0.8em"}),
                            html.Button("Deselect All", id="second-table-deselect-all", n_clicks=0, 
                                       style={"marginLeft": "10px", "fontSize": "0.8em"})
                        ], style={"display": "flex", "alignItems": "center", "marginBottom": "5px"}),
                        dcc.Checklist(
                            id="second-table-columns",
                            options=[],
                            value=[],
                            style={"maxHeight": "150px", "overflowY": "auto", "padding": "10px", 
                                  "backgroundColor": "#f9f9f9", "borderRadius": "5px"}
                        )
                    ])
                ], id="column-selection-div", style={"display": "none", "marginBottom": "15px"}),
                
                # Row limit
                html.Div([
                    html.Label("Step 6: Set row limit", style={"fontWeight": "bold", "marginBottom": "5px"}),
                    dcc.Input(
                        id="row-limit-input",
                        type="number",
                        min=1,
                        max=100000,
                        value=1000,
                        style={"width": "100px"}
                    ),
                ], id="row-limit-div", style={"display": "none", "marginBottom": "15px"}),
                
                # Execute join button
                html.Div([
                    html.Button(
                        "Execute Join",
                        id="execute-join-button",
                        style={
                            "backgroundColor": "#007bff",
                            "color": "white",
                            "border": "none",
                            "borderRadius": "4px",
                            "padding": "10px 20px",
                            "fontSize": "16px",
                            "cursor": "pointer"
                        }
                    )
                ], id="execute-button-div", style={"display": "none", "textAlign": "center", "marginTop": "20px"})
            ], style={"width": "40%", "padding": "20px", "backgroundColor": "#e5ecf6", "borderRadius": "10px"}),
            
            # Right side - Results
            html.Div([
                html.Div([
                    html.H5("Join Preview", style={"marginBottom": "15px"}),
                    html.Div(id="join-sql-query", style={"fontFamily": "monospace", "backgroundColor": "#f8f9fa", 
                                                          "padding": "10px", "borderRadius": "5px", 
                                                          "marginBottom": "15px", "overflowX": "auto"}),
                    dcc.Loading(
                        html.Div(id="join-results-table"),
                        type="circle"
                    ),
                    html.Div([
                        html.Div(id="join-results-stats", style={"marginTop": "15px", "color": "#666"}),
                        html.Button(
                            "Download CSV",
                            id="download-join-csv-button",
                            style={
                                "backgroundColor": "#28a745",
                                "color": "white",
                                "border": "none",
                                "borderRadius": "4px",
                                "padding": "5px 15px",
                                "marginTop": "15px"
                            }
                        ),
                        dcc.Download(id="download-join-csv"), 
                        html.Button(
                            "Save Dataset as Joined Dataset",
                            id="save-dataset-button",
                            style={
                                "backgroundColor": "#ffc107",
                                "color": "white",
                                "border": "none",
                                "borderRadius": "4px",
                                "padding": "5px 15px",
                                "marginLeft": "10px"
                            }
                        ),
                        html.Div(id="save-confirmation", style={"color": "#28a745", "marginTop": "10px"})
                    ])
                ], id="join-results-div", style={"display": "none"})
            ], style={"width": "55%", "marginLeft": "5%", "padding": "20px", "backgroundColor": "#f0f2f5", 
                      "borderRadius": "10px", "maxHeight": "800px", "overflowY": "auto"})
        ], style={"display": "flex", "justifyContent": "space-between", "marginTop": "20px"})


# Layout for Dataset Tab
dataset_layout = dcc.Tab(
    label="Tables",
    id="dataset-tab",
    style={"padding": "15px"},
    children=[
        # Store the tab's active state
        dcc.Store(id="dataset-tab-active", data=False),
        # Store joined dataset
        dcc.Store(id="joined-dataset-store", storage_type="local"),
        dcc.Store(id="cached-data-key"),

        html.Br(),
        html.H4("Table View and Figure Generation", style={"marginBottom": "20px"}),
        dcc.Dropdown(table_options, id="dataset_dropdown", placeholder="Table Options"),
        # Column checklist
        html.Div([
            html.Div([
                html.Label("Select columns to include:", style={"fontWeight": "bold", "marginBottom": "5px"}),
                html.Button("Select All", id="select_all_btn", n_clicks=0, style={"marginLeft": "10px", "fontSize": "0.8em"}),
                html.Button("Deselect All", id="deselect_all_btn", n_clicks=0, style={"marginLeft": "10px", "fontSize": "0.8em"}),
            ], style={"display": "flex", "alignItems": "center", "marginBottom": "5px"}),
            dcc.Checklist(id="options", options=[], value=[], inline=False,
                        labelStyle={"display": "block", "marginBottom": "3px"},
                        style={"maxHeight": "200px", "overflowY": "auto", "padding": "10px", "backgroundColor": "#f9f9f9", "borderRadius": "5px"}),
        ], id="columns_container", style={"display": "none", "marginBottom": "15px"}),
        # Row count input
        html.Div([
            html.Label("Number of rows to display:", style={"fontWeight": "bold"}),
            dcc.Input(id="row_count", type="number", min=1, max=1000, value=20,
                    style={"width": "100px", "margin": "10px 0"}),
            html.Span(id="max_rows_info", style={"marginLeft": "10px", "color": "#666", "fontSize": "0.9em"}),
        ], id="row_count_container", style={"display": "none"}),
        # Filtering usage info
        html.Div([
            html.P("Enter filtering queries for each column in the second row of the table. The displayed data will be used for figure generation."),
            html.P("Use operators like >, <, >=, <=, != for numerical columns. For text columns, use 'contains', 'startswith', 'endswith'.")
        ], id="filtering_usage_info", style={"display": "none"}),
        # Filter and selection counts
        html.Div([
            html.Span(id='filter_count_text', style={"marginRight": "20px", "fontWeight": "bold"}),
            html.Span(id='selected_count_text', style={"fontWeight": "bold", "marginRight": "12px"}),
            html.Button("Deselect All Rows", id="deselect_all_rows_btn", n_clicks=0,
                        style={"fontSize": "0.9em", "padding": "3px 8px", "backgroundColor": "#f0f0f0", "border": "1px solid #ccc", "borderRadius": "4px"})
        ], id="filter_selection_counts", style={"display": "none"}),
        # Placeholder message
        html.Div(id="placeholder_message", children=[
            html.H5(
                "Select a table name, columns, and number of rows to construct the table",
                style={"textAlign": "center", "marginTop": "50px", "color": "#666"}
            ),
            # Error message area
            html.Div(id="dataset-error-message", style={"color": "red", "marginTop": "20px", "fontWeight": "bold"})
        ]),
        # Data table
        html.Div(html.Div(id="dataset_container", style={"display": "none"}, children=[
            html.Div(
                dash_table.DataTable(
                    id='dataset_table',
                    data=[],
                    columns=[],
                    page_size=20,
                    filter_action='native',
                    sort_action='native',
                    row_selectable='multi',
                    selected_rows=[],
                    cell_selectable=True,
                    style_table={'overflowX': 'auto', 'marginTop': '8px'},
                    style_cell={
                        'padding': '4px 6px',
                        'fontSize': '12px',
                        'minWidth': '100px',
                        'whiteSpace': 'nowrap',
                        'overflow': 'hidden',
                        'textOverflow': 'ellipsis'
                    },
                    style_header={
                        'backgroundColor': '#f8f9fa',
                        'fontWeight': 'bold',
                        'padding': '10px',
                    },
                    style_cell_conditional=[
                        {'if': {'column_id': 'selection'}, 'width': '50px'}
                    ],
                    style_data_conditional=[
                        {'if': {'state': 'selected'}, 'backgroundColor': '#D2E3F6'},
                        {'if': {'state': 'active'}, 'border': 'inherit'}
                    ]
                ),
                style={"overflowX": "auto", "width": "100%"}
            )
        ]), style={"maxHeight": "800px", "overflowY": "auto", "backgroundColor": "#e5ecf6", "padding": "10px", "borderRadius": "5px", "border": "1px solid #d1d1d1"}),

        # Variable selectors for plotting
        html.Div([
            html.Label("Select variables to plot selected rows:", style={"fontWeight": "bold", "marginBottom": "5px"}),
            html.Div([
                html.Div([
                    html.Label("X-axis:", style={"marginRight": "5px"}),
                    dcc.Dropdown(id="x_variable_dropdown", options=[], placeholder="Select X variable", style={"width": "100%"}),
                ], style={"width": "45%", "display": "inline-block", "marginRight": "5%"}),
                html.Div([
                    html.Label("Y-axis:", style={"marginRight": "5px"}),
                    dcc.Dropdown(id="y_variable_dropdown", options=[], placeholder="Select Y variable", style={"width": "100%"}),
                ], style={"width": "45%", "display": "inline-block"}),
            ], style={"display": "flex", "alignItems": "center"}),
        ], id="variable_selector", style={"display": "none", "marginBottom": "15px"}),
        
        # Graph type explanation
        html.Div([
            html.Label("Graph types based on variable selection:", style={"fontWeight": "bold", "marginBottom": "5px"}),
            html.Ul([
                html.Li("Numerical + Numerical → Scatter plot"),
                html.Li("Numerical + Categorical → Bar chart (mean of numerical by category)"),
                html.Li("Categorical + Numerical → Bar chart (mean of numerical by category)"),
                html.Li("Categorical + Categorical → Bar chart and Heatmap"),
            ], style={"marginLeft": "20px", "fontSize": "0.9em"})
        ], id="graph_type_explanation", style={"display": "none", "marginBottom": "15px", "backgroundColor": "#f9f9f9", "padding": "10px", "borderRadius": "5px"}),
        
        # Generate figure button
        html.Div(html.Button("Generate Figure", id="generate_btn", n_clicks=0, disabled=True),
                id="generate_button_div", style={"display": "none", "textAlign": "center", "marginBottom": "15px"}),
        # Figure output
        html.Div(id="figure_div", style={"display": "none"}, children=[
            dcc.Loading(dcc.Graph(id="figure_graph"), type="default")
        ]),
        # Footer spacer
        html.Div(style={"height": "50px", "backgroundColor": "#e5ecf6", "width": "100%", "marginTop": "10px", "borderTop": "1px solid #d1d1d1", "borderRadius": "0 0 5px 5px"}),

        html.Br(),
        html.H4("Custom Table Joins", style={"marginBottom": "20px"}),
        # Placeholder message
        html.Div(
            html.H5("Select tables and join parameters to start", 
                   style={"textAlign": "center", "marginTop": "10px", "color": "#666"}),
            id="joins-placeholder"
        ),

        # Combine dataset and joins layouts
        # Main container for the join operation
        joins_layout_dataset,
        html.Div(id="join-error-message", style={"color": "red", "marginTop": "20px", "fontWeight": "bold"}),
    ]
)

# Callbacks

# Track tab selection state
@callback(
    Output('dataset-tab-active', 'data'),
    [Input('main-tabs', 'value')]  
)
def set_tab_active(tab_value):
    return tab_value == 'dataset-tab'

# Reset all components when tab is switched or table is changed
@callback(
    [Output('dataset_dropdown', 'value', allow_duplicate=True),
     Output('options', 'options', allow_duplicate=True),
     Output('options', 'value', allow_duplicate=True),
     Output('row_count', 'value', allow_duplicate=True),
     Output('x_variable_dropdown', 'value', allow_duplicate=True),
     Output('y_variable_dropdown', 'value', allow_duplicate=True),
     Output('figure_div', 'children', allow_duplicate=True), 
     Output('figure_div', 'style', allow_duplicate=True),
     Output('generate_btn', 'n_clicks', allow_duplicate=True)],
    [Input('dataset-tab-active', 'data')],
    prevent_initial_call=True
)
def reset_tab_data(is_active):
    if not is_active:
        # Reset all controls when leaving the tab
        return None, [], [], 20, None, None, [], {"display": "none"}, 0
    else:
        # Don't reset when entering the tab
        return [dash.no_update] * 9

# Handle table and column selection
@callback(
    [Output('options', 'options', allow_duplicate=True), 
     Output('options', 'value', allow_duplicate=True), 
     Output('columns_container', 'style')],
    [Input('dataset_dropdown', 'value')],
    prevent_initial_call=True
)
def update_column_options_on_table_change(selected_table):
    if selected_table is None:
        return [], [], {"display": "none"}
    try:
        sample_df = fetch_data_from_sql(f"SELECT TOP 1 * FROM [dbo].[{selected_table}]")
        cols = sample_df.columns.tolist()
        opts = [{'label': c, 'value': c} for c in cols]
        return opts, cols, {"display": "block", "marginBottom": "15px"}
    except Exception as e:
        print(f"Error fetching columns: {e}")
        return [], [], {"display": "none"}

# Reset dependent components when table changes
@callback(
    [Output('x_variable_dropdown', 'value', allow_duplicate=True), 
     Output('y_variable_dropdown', 'value', allow_duplicate=True),
     Output('figure_div', 'children', allow_duplicate=True), 
     Output('figure_div', 'style', allow_duplicate=True)],
    [Input('dataset_dropdown', 'value')],
    prevent_initial_call=True
)
def reset_dependent_components(selected_table):
    # Reset all dependent components when table changes
    return None, None, [], {"display": "none"}

# Handle Select All and Deselect All buttons
@callback(
    Output('options', 'value', allow_duplicate=True),
    [Input('select_all_btn', 'n_clicks'), 
     Input('deselect_all_btn', 'n_clicks')],
    [State('options', 'options'), State('options', 'value')],
    prevent_initial_call=True
)
def handle_select_buttons(select_all_clicks, deselect_all_clicks, current_options, current_values):
    trigger_id = ctx.triggered_id if ctx.triggered_id else 'no_trigger'
    
    if trigger_id == 'select_all_btn' and current_options:
        return [opt['value'] for opt in current_options]
    if trigger_id == 'deselect_all_btn':
        return []
    
    return dash.no_update

@callback(
    [Output('x_variable_dropdown', 'options'), Output('y_variable_dropdown', 'options')],
    Input('options', 'options')
)
def update_variable_dropdown_options(column_options):
    return column_options, column_options

@callback(
    [Output('max_rows_info', 'children'), Output('row_count', 'max')],
    Input('dataset_dropdown', 'value')
)
def update_row_count_info(selected_table):
    if selected_table is None:
        return "", 1000
    try:
        count_df = fetch_data_from_sql(f"SELECT COUNT(*) AS row_count FROM [dbo].[{selected_table}]")
        total = count_df.iloc[0]['row_count']
        return f"(Max: {total} rows available)", total
    except Exception as e:
        print(f"Error fetching row count: {e}")
        return "", 1000

@callback(
    [Output('dataset_table', 'data'), Output('dataset_table', 'columns'), Output('row_count_container', 'style'),
     Output('filtering_usage_info', 'style'), Output('filter_selection_counts', 'style'),
     Output('placeholder_message', 'style'), Output('dataset_container', 'style'),
     Output('variable_selector', 'style'), Output('generate_button_div', 'style'),
     Output('graph_type_explanation', 'style')],
    [Input('dataset_dropdown', 'value'), Input('options', 'value'), Input('row_count', 'value')],
    State('options', 'options')
)
def update_output(selected_table, selected_columns, row_count, column_options):
    no_display = {"display": "none"}
    if selected_table is None:
        return [], [], no_display, no_display, no_display, {"display": "block"}, no_display, no_display, no_display, no_display
    if not selected_columns:
        cols = [opt['value'] for opt in column_options]
    else:
        cols = selected_columns
    if row_count is None:
        row_count = 20
    try:
        cnt_df = fetch_data_from_sql(f"SELECT COUNT(*) AS row_count FROM [dbo].[{selected_table}]")
        total = cnt_df.iloc[0]['row_count']
        row_count = min(row_count, total)
    except:
        pass

    # Fetch data for DataTable (respect selected columns and row_count)
    try:
        cols_sql = ", ".join([f"[{c}]" for c in cols]) if cols else "*"
        query = f"SELECT TOP {row_count} {cols_sql} FROM [dbo].[{selected_table}]"
        df = fetch_data_from_sql(query)
        data = df.to_dict('records')
        columns = [{'name': c, 'id': c} for c in df.columns]
    except Exception as e:
        print(f"Error fetching table data for DataTable: {e}")
        data, columns = [], []

    return data, columns, {"display": "block", "margin": "10px 0"}, {"display": "block"}, {"display": "block"}, {"display": "none"}, {"display": "block"}, {"display": "block", "marginBottom": "15px"}, {"display": "block"}, {"display": "block", "marginBottom": "15px"}

# Display counts for filtered rows and checkbox selection
@callback(
    [Output('filter_count_text', 'children'), Output('selected_count_text', 'children')],
    [Input('dataset_table', 'derived_virtual_data'), Input('dataset_table', 'selected_rows'), Input('dataset_table', 'data')]
)
def update_table_counts(derived_virtual_data, selected_rows, raw_data):
    if derived_virtual_data is None:
        filtered_count = len(raw_data) if raw_data else 0
    else:
        filtered_count = len(derived_virtual_data)

    selected_count = len(selected_rows) if selected_rows else 0

    filter_text = f"Filtered rows: {filtered_count}"
    selected_text = f"Selected rows: {selected_count}"
    return filter_text, selected_text

# Deselect all rows from DataTable
@callback(
    Output('dataset_table', 'selected_rows'),
    Input('deselect_all_rows_btn', 'n_clicks'),
    prevent_initial_call=True
)
def deselect_all_rows(n_clicks):
    if not n_clicks or n_clicks == 0:
        return dash.no_update
    return []

@callback(
    Output('generate_btn', 'disabled'),
    Input('x_variable_dropdown', 'value'), Input('y_variable_dropdown', 'value')
)
def toggle_generate_button(x_var, y_var):
    return not (x_var and y_var)

@callback(
    [Output('figure_div', 'children', allow_duplicate=True), 
     Output('figure_div', 'style', allow_duplicate=True)],
    Input('generate_btn', 'n_clicks'),
    State('dataset_dropdown', 'value'),
    State('x_variable_dropdown', 'value'),
    State('y_variable_dropdown', 'value'),
    State('row_count', 'value'),
    # DataTable states to plot selected rows
    State('dataset_table', 'derived_virtual_data'), # data after filtering/sorting
    State('dataset_table', 'derived_virtual_selected_rows'), # indices of checkbox selected rows
    State('dataset_table', 'data'), # all raw data
    State('dataset_table', 'selected_rows'), # checkbox selected rows
    State('dataset_table', 'selected_cells'), # cell selections
    prevent_initial_call=True
)
def generate_figure(n_clicks, selected_table, x_var, y_var, row_count,
                    derived_virtual_data, derived_virtual_selected_rows,
                    raw_data, raw_selected_rows, selected_cells):
    if not n_clicks or n_clicks == 0 or selected_table is None or x_var is None or y_var is None:
        return [], {"display": "none"}
    
    # Generate different data frame if the joined one is stored
    
    df = None
    col1, col2 = x_var, y_var

    # uses data from filtered and checked rows
    if derived_virtual_selected_rows and len(derived_virtual_selected_rows) > 0:
        df = pd.DataFrame(derived_virtual_data).iloc[derived_virtual_selected_rows]

    # uses data from selecting check box rows
    elif raw_selected_rows and len(raw_selected_rows) > 0:
        df = pd.DataFrame(raw_data).iloc[raw_selected_rows]

    # uses filtered data
    elif derived_virtual_data and len(derived_virtual_data) > 0:
        df = pd.DataFrame(derived_virtual_data)
    
    # use all raw data
    elif raw_data and len(raw_data) > 0:
        df = pd.DataFrame(raw_data)
    
    # Fallback to fetch data from SQL
    else:
        if df is None:
            if selected_table:
                query = f"SELECT TOP {row_count} [{col1}], [{col2}] FROM [dbo].[{selected_table}]"
                df = fetch_data_from_sql(query)[[col1, col2]].dropna()
        else:
            return [], {"display": "none"}
    
    num1, num2 = is_numeric_dtype(df[col1]), is_numeric_dtype(df[col2])
    
    if num1 and num2:
        fig = px.scatter(df, x=col1, y=col2, title=f"{col1} vs {col2}")
        graph = dcc.Graph(figure=fig)
        return graph, {"display": "block"}
    if num1 and not num2:
        num, cat = col1, col2
    elif num2 and not num1:
        num, cat = col2, col1
    else:
        num = cat = None
    
    if num and cat:
        df_agg = df.groupby(cat)[num].mean().reset_index()
        fig = px.bar(df_agg, x=cat, y=num, title=f"Mean {num} by {cat}")
        graph = dcc.Graph(figure=fig)
        return graph, {"display": "block"}
    
    fig_bar = px.bar(df, x=col1, color=col2, barmode='group', title=f"{col1} by {col2}")
    fig_heat = px.density_heatmap(df, x=col1, y=col2, title=f"Heatmap of {col1} vs {col2}")
    graph1 = dcc.Graph(figure=fig_bar)
    graph2 = dcc.Graph(figure=fig_heat)
    return [graph1, graph2], {"display": "block"}

# Reset when tab is switched
@callback(
    [Output('first-table-dropdown', 'value', allow_duplicate=True),
     Output('join-type-dropdown', 'value', allow_duplicate=True),
     Output('second-table-dropdown', 'value', allow_duplicate=True),
     Output('first-table-key', 'value', allow_duplicate=True),
     Output('second-table-key', 'value', allow_duplicate=True),
     Output('first-table-columns', 'options', allow_duplicate=True),
     Output('first-table-columns', 'value', allow_duplicate=True),
     Output('second-table-columns', 'options', allow_duplicate=True),
     Output('second-table-columns', 'value', allow_duplicate=True),
     Output('row-limit-input', 'value', allow_duplicate=True),
     Output('join-results-div', 'style', allow_duplicate=True),
     Output('joins-placeholder', 'style', allow_duplicate=True),
     Output('join-error-message', 'children', allow_duplicate=True)],
    [Input('joins-tab-active', 'data')],
    prevent_initial_call=True
)
def reset_joins_tab_data(is_active):
    if not is_active:
        # Reset all controls when leaving the tab
        return (None, None, None, None, None, 
                [], [], [], [], 1000, 
                {"display": "none"}, {"display": "block"}, "")
    else:
        # Don't reset when entering the tab
        return [dash.no_update] * 13

# Update the join visualization based on join type
@callback(
    [Output('join-visualization', 'style'),
     Output('join-visualization', 'children')],
    [Input('join-type-dropdown', 'value')]
)
def update_join_visualization(join_type):
    if not join_type:
        return {"display": "none"}, []
    
    # Image URLs for different join types
    join_images = {
        "inner": "/assets/inner.png",
        "left": "/assets/left.png",
        "right": "/assets/right.png",
        "full": "/assets/outer.png"
    }
    
    # Join type descriptions
    join_descriptions = {
        "inner": "Returns rows when there is a match in both tables",
        "left": "Returns all rows from the left table, and matched rows from the right table",
        "right": "Returns all rows from the right table, and matched rows from the left table",
        "full": "Returns all rows when there is a match in either table"
    }
    
    return {"display": "block", "marginTop": "10px"}, [
        html.Img(src=join_images[join_type], style={"width": "100%", "marginTop": "10px"}),
        html.P(join_descriptions[join_type], style={"textAlign": "center", "color": "#666", "fontSize": "0.9em"})
    ]

# Get columns for both tables when selected
@callback(
    [Output('join-keys-div', 'style'),
     Output('column-selection-div', 'style'),
     Output('row-limit-div', 'style'),
     Output('execute-button-div', 'style'),
     Output('first-table-key', 'options'),
     Output('second-table-key', 'options'),
     Output('first-table-columns', 'options'),
     Output('second-table-columns', 'options')],
    [Input('first-table-dropdown', 'value'),
     Input('second-table-dropdown', 'value'),
     Input('join-type-dropdown', 'value')]
)
def update_column_options(first_table, second_table, join_type):
    # Don't display anything if any selection is missing
    if not first_table or not second_table or not join_type:
        return {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}, [], [], [], []
    
    # Get columns from both tables
    try:
        first_df = fetch_data_from_sql(f"SELECT TOP 1 * FROM [dbo].[{first_table}]")
        second_df = fetch_data_from_sql(f"SELECT TOP 1 * FROM [dbo].[{second_table}]")
        
        first_columns = first_df.columns.tolist()
        second_columns = second_df.columns.tolist()
        
        first_column_options = [{"label": col, "value": col} for col in first_columns]
        second_column_options = [{"label": col, "value": col} for col in second_columns]
        
        # Show all divs
        return ({"display": "block", "marginBottom": "15px"}, 
                {"display": "block", "marginBottom": "15px"},
                {"display": "block", "marginBottom": "15px"},
                {"display": "block", "textAlign": "center", "marginTop": "20px"},
                first_column_options,
                second_column_options,
                first_column_options,
                second_column_options)
    except Exception as e:
        print(f"Error getting columns: {e}")
        return {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}, [], [], [], []

# Handle column selection buttons
@callback(
    Output('first-table-columns', 'value'),
    [Input('first-table-select-all', 'n_clicks'),
     Input('first-table-deselect-all', 'n_clicks')],
    [State('first-table-columns', 'options'), 
     State('first-table-columns', 'value')]
)
def handle_first_table_column_selection(select_clicks, deselect_clicks, options, current_value):
    trigger_id = ctx.triggered_id if ctx.triggered_id else 'no-id'
    
    if trigger_id == 'first-table-select-all':
        return [option['value'] for option in options]
    elif trigger_id == 'first-table-deselect-all':
        return []
    
    return current_value

@callback(
    Output('second-table-columns', 'value'),
    [Input('second-table-select-all', 'n_clicks'),
     Input('second-table-deselect-all', 'n_clicks')],
    [State('second-table-columns', 'options'), 
     State('second-table-columns', 'value')]
)
def handle_second_table_column_selection(select_clicks, deselect_clicks, options, current_value):
    trigger_id = ctx.triggered_id if ctx.triggered_id else 'no-id'
    
    if trigger_id == 'second-table-select-all':
        return [option['value'] for option in options]
    elif trigger_id == 'second-table-deselect-all':
        return []
    
    return current_value

# Generate and execute the join
@callback(
    [Output('join-results-div', 'style'),
     Output('joins-placeholder', 'style'),
     Output('join-sql-query', 'children'),
     Output('join-results-table', 'children'),
     Output('join-results-stats', 'children'),
     Output('join-error-message', 'children')],
     Output('joined-dataset-store', 'data'),
    [Input('execute-join-button', 'n_clicks')],
    [State('first-table-dropdown', 'value'),
     State('join-type-dropdown', 'value'),
     State('second-table-dropdown', 'value'),
     State('first-table-key', 'value'),
     State('second-table-key', 'value'),
     State('first-table-columns', 'value'),
     State('second-table-columns', 'value'),
     State('row-limit-input', 'value')]
)
def execute_join(n_clicks, first_table, join_type, second_table, first_key, second_key, 
                 first_columns, second_columns, row_limit):
    if n_clicks is None or n_clicks == 0:
        return {"display": "none"}, {"display": "block"}, "", None, "", "", None
    
    # Validate inputs
    if not first_table or not join_type or not second_table or not first_key or not second_key:
        return {"display": "none"}, {"display": "block"}, "", None, "", "Please select all required fields", None
    
    if not first_columns and not second_columns:
        return {"display": "none"}, {"display": "block"}, "", None, "", "Please select at least one column from either table", None
    
    try:
        # Format column selections for SQL query
        first_cols = []
        if first_columns:
            for col in first_columns:
                if col != first_key:  # Avoid duplicate keys in the result
                    first_cols.append(f"t1.[{col}] AS [t1_{col}]")
                else:
                    first_cols.append(f"t1.[{col}]")  # Don't rename the join key
        
        second_cols = []
        if second_columns:
            for col in second_columns:
                if col != second_key or col == first_key:  # Avoid duplicate keys or columns with same name
                    second_cols.append(f"t2.[{col}] AS [t2_{col}]")
                else:
                    second_cols.append(f"t2.[{col}]")
        
        # Construct the SQL query
        columns = ", ".join(first_cols + second_cols)
        if not columns.strip():
            columns = "t1.[" + first_key + "], t2.[" + second_key + "]"
        
        sql_query = f"""
        SELECT TOP {row_limit} {columns}
        FROM [dbo].[{first_table}] AS t1
        {join_type.upper()} JOIN [dbo].[{second_table}] AS t2
        ON t1.[{first_key}] = t2.[{second_key}]
        """
        
        # Execute the query
        result_df = fetch_data_from_sql(sql_query)
        
        # Create stats information
        row_count = len(result_df)
        stats_text = f"Showing {row_count} rows"
        if row_count == row_limit:
            stats_text += f" (limited to {row_limit} rows)"
        stats_text += f" | {len(result_df.columns)} columns"
        
        # Create the table display
        table = dash_table.DataTable(
            data=result_df.head(1000).to_dict('records'),
            columns=[{'name': col, 'id': col} for col in result_df.columns],
            page_size=15,
            style_table={'overflowX': 'auto'},
            style_cell={
                'minWidth': '100px',
                'maxWidth': '300px',
                'overflow': 'hidden',
                'textOverflow': 'ellipsis'
            },
            style_header={
                'backgroundColor': 'rgb(230, 230, 230)',
                'fontWeight': 'bold'
            },
            style_data_conditional=[
                {
                    'if': {'row_index': 'odd'},
                    'backgroundColor': 'rgb(248, 248, 248)'
                }
            ],
            filter_action="native",
            sort_action="native"
        )
        
        # Format the SQL query for display
        formatted_query = html.Pre(sql_query, style={"margin": 0})

        # Convert dataframe to dict for storage
        dataset_dict = result_df.to_dict('records')
        data_key = str(uuid.uuid4())
        store_large_df(data_key, dataset_dict)
        
        return {"display": "block"}, {"display": "none"}, formatted_query, table, stats_text, "", data_key
    
    except Exception as e:
        error_message = str(e)
        return {"display": "none"}, {"display": "block"}, "", None, "", f"Error executing join: {error_message}", None

# Download the join results as CSV
@callback(
    Output('download-join-csv', 'data'),
    [Input('download-join-csv-button', 'n_clicks')],
    [State('first-table-dropdown', 'value'),
     State('join-type-dropdown', 'value'),
     State('second-table-dropdown', 'value'),
     State('first-table-key', 'value'),
     State('second-table-key', 'value'),
     State('first-table-columns', 'value'),
     State('second-table-columns', 'value'),
     State('row-limit-input', 'value')]
)
def download_join_results(n_clicks, first_table, join_type, second_table, first_key, second_key, 
                         first_columns, second_columns, row_limit):
    if n_clicks is None or n_clicks == 0:
        return dash.no_update
    
    try:
        # Format column selections for SQL query
        first_cols = []
        if first_columns:
            for col in first_columns:
                if col != first_key:  # Avoid duplicate keys in the result
                    first_cols.append(f"t1.[{col}] AS [t1_{col}]")
                else:
                    first_cols.append(f"t1.[{col}]")  # Don't rename the join key
        
        second_cols = []
        if second_columns:
            for col in second_columns:
                if col != second_key or col == first_key:  # Avoid duplicate keys or columns with same name
                    second_cols.append(f"t2.[{col}] AS [t2_{col}]")
                else:
                    second_cols.append(f"t2.[{col}]")
        
        # Construct the SQL query
        columns = ", ".join(first_cols + second_cols)
        if not columns.strip():
            columns = "t1.[" + first_key + "], t2.[" + second_key + "]"
        
        sql_query = f"""
        SELECT TOP {row_limit} {columns}
        FROM [dbo].[{first_table}] AS t1
        {join_type.upper()} JOIN [dbo].[{second_table}] AS t2
        ON t1.[{first_key}] = t2.[{second_key}]
        """
        
        # Execute the query
        result_df = fetch_data_from_sql(sql_query)
        
        # Generate a filename based on the tables being joined
        filename = f"{first_table}_{join_type}_join_{second_table}.csv"
        
        return dcc.send_data_frame(result_df.to_csv, filename, index=False)
    except Exception as e:
        # If there's an error, don't download anything
        print(f"Error during download: {e}")
        return dash.no_update
    


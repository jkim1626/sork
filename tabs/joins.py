import os
from dash import dcc, html, Input, Output, State, callback, callback_context, dash_table, ctx
import dash
from dotenv import load_dotenv
from database import fetch_data_from_sql
import pandas as pd

# Load environment variables
load_dotenv(override=True)

CORE_TABLES={
    "db_main": "Growth/Survival",
    "budburst_detailed_all": "All Budburst Stages",
    "biomass_2021_combined_fordb_052224": "Biomass",
    "leaf_traits_2016": "Leaf traits",
}

MATERNAL_TREE_TABLE="Valley oak maternal tree climate data BCM 2018_03_08"

GARDENS_TABLE="gardens_20152023prismmonthly"

# Create a layout for the joins tab
joins_layout = dcc.Tab(
    label="Table Joins",
    id="joins-tab",
    style={"padding": "15px"},
    children=[
        dcc.Store(id='joins-tab-active', data=False),
        dcc.Store(id='join-tab-full-data', data=None),  # Store full dataframe for filtering/sorting
        dcc.Store(id='join-total-count', data=0),  # Store total count of rows
        html.Div(
            [
                # Introduction section
                html.Div([
                    html.H4("Join Your Data", style={"marginBottom": "10px", "color": "#133817"}),
                    html.P(
                        "Automatically combines your garden dataset with maternal tree climate data and garden climate data. "
                        "All columns are selected by default. Please uncheck any you don't need.",
                        style={"color": "#666", "marginBottom": "20px", "fontSize": "0.95em"}
                    ),
                ], style={"marginBottom": "25px", "padding": "15px", "backgroundColor": "#f0f7f2", "borderRadius": "8px"}),

                # Step 1: Pick the core table
                html.Div([
                    html.H5("Step 1: Select Your Garden Dataset", style={"fontWeight": "bold", "marginBottom": "10px", "color": "#133817"}),
                    html.P("Choose the main dataset you want to work with:", style={"color": "#666", "marginBottom": "8px", "fontSize": "0.9em"}),
                    dcc.Dropdown(
                        id="join-tab-core-dropdown",
                        options=[{"label":value, "value":key} for key,value in CORE_TABLES.items()],
                        placeholder="Select a Garden Dataset..."
                    ),
                ], style={"marginBottom": "25px", "padding": "15px", "backgroundColor": "#ffffff", "borderRadius": "8px", "border": "1px solid #e0e0e0"}),

                # Step 2: Core table columns (in a card)
                html.Div([
                    html.Div([
                        html.H5("Garden Dataset Columns", style={"fontWeight": "bold", "marginBottom": "5px", "color": "#133817"}),
                        html.P("All columns are selected by default. Uncheck any you don't need.", 
                               style={"color": "#666", "fontSize": "0.85em", "marginBottom": "10px"}),
                        html.Div([
                            html.Button("Select All", id="join-select_all_btn", n_clicks=0, 
                                      style={"marginRight": "10px", "fontSize": "0.85em", "padding": "5px 12px", 
                                            "backgroundColor": "#007bff", "color": "white", "border": "none", "borderRadius": "4px", "cursor": "pointer"}),
                            html.Button("Deselect All", id="join-deselect_all_btn", n_clicks=0, 
                                      style={"fontSize": "0.85em", "padding": "5px 12px", 
                                            "backgroundColor": "#6c757d", "color": "white", "border": "none", "borderRadius": "4px", "cursor": "pointer"}),
                        ], style={"marginBottom": "10px"}),
                    ]),
                    dcc.Checklist(id="join-core-table-options", options=[], value=[], inline=False,
                                labelStyle={"display": "block", "marginBottom": "5px", "padding": "3px"},
                                style={"maxHeight": "250px", "overflowY": "auto", "padding": "10px", 
                                      "backgroundColor": "#f9f9f9", "borderRadius": "5px"}),
                ], id="join-table-columns-container", style={"display": "none", "marginBottom": "20px", 
                                                              "padding": "15px", "backgroundColor": "#ffffff", 
                                                              "borderRadius": "8px", "border": "1px solid #e0e0e0"}),

                # Step 3: Maternal tree table columns (in a card)
                html.Div([
                    html.Div([
                        html.H5("Maternal Tree Climate Data", style={"fontWeight": "bold", "marginBottom": "5px", "color": "#133817"}),
                        html.P("Climate data from the original tree locations. Automatically matched by Accession and Locality.", 
                               style={"color": "#666", "fontSize": "0.85em", "marginBottom": "10px"}),
                        html.Div([
                            html.Button("Select All", id="join-select_all_btn-2", n_clicks=0, 
                                      style={"marginRight": "10px", "fontSize": "0.85em", "padding": "5px 12px", 
                                            "backgroundColor": "#007bff", "color": "white", "border": "none", "borderRadius": "4px", "cursor": "pointer"}),
                            html.Button("Deselect All", id="join-deselect_all_btn-2", n_clicks=0, 
                                      style={"fontSize": "0.85em", "padding": "5px 12px", 
                                            "backgroundColor": "#6c757d", "color": "white", "border": "none", "borderRadius": "4px", "cursor": "pointer"}),
                        ], style={"marginBottom": "10px"}),
                    ]),
                    dcc.Checklist(id="join-tree-table-options", options=[], value=[], inline=False,
                                labelStyle={"display": "block", "marginBottom": "5px", "padding": "3px"},
                                style={"maxHeight": "250px", "overflowY": "auto", "padding": "10px", 
                                      "backgroundColor": "#f9f9f9", "borderRadius": "5px"}),
                ], id="join-tree-table-columns-container", style={"display": "none", "marginBottom": "20px",
                                                                    "padding": "15px", "backgroundColor": "#ffffff", 
                                                                    "borderRadius": "8px", "border": "1px solid #e0e0e0"}),

                # Step 4: Garden climate variables (in a card)
                html.Div([
                    html.Div([
                        html.H5("Garden Climate Data", style={"fontWeight": "bold", "marginBottom": "5px", "color": "#133817"}),
                        html.P("Monthly climate data from garden sites. Automatically matched by Site (and Year, if available).", 
                               style={"color": "#666", "fontSize": "0.85em", "marginBottom": "10px"}),
                        html.Div([
                            html.Button("Select All", id="join-select_all_btn-3", n_clicks=0, 
                                      style={"marginRight": "10px", "fontSize": "0.85em", "padding": "5px 12px", 
                                            "backgroundColor": "#007bff", "color": "white", "border": "none", "borderRadius": "4px", "cursor": "pointer"}),
                            html.Button("Deselect All", id="join-deselect_all_btn-3", n_clicks=0, 
                                      style={"fontSize": "0.85em", "padding": "5px 12px", 
                                            "backgroundColor": "#6c757d", "color": "white", "border": "none", "borderRadius": "4px", "cursor": "pointer"}),
                        ], style={"marginBottom": "10px"}),
                    ]),
                    dcc.Checklist(id="join-garden-table-options", options=[], value=[], inline=False,
                                labelStyle={"display": "block", "marginBottom": "5px", "padding": "3px"},
                                style={"maxHeight": "250px", "overflowY": "auto", "padding": "10px", 
                                      "backgroundColor": "#f9f9f9", "borderRadius": "5px"}),
                ], id="join-garden-table-columns-container", style={"display": "none", "marginBottom": "20px",
                                                                     "padding": "15px", "backgroundColor": "#ffffff", 
                                                                     "borderRadius": "8px", "border": "1px solid #e0e0e0"}),

                # Join preview section (shows before execution)
                html.Div([
                    html.H5("Join Preview", style={"fontWeight": "bold", "marginBottom": "10px", "color": "#133817"}),
                    html.Div(id="join-tab-preview", style={"padding": "10px", "backgroundColor": "#f8f9fa", 
                                                           "borderRadius": "5px", "color": "#666", "fontSize": "0.9em"}),
                ], id="join-tab-preview-container", style={"display": "none", "marginBottom": "20px",
                                                           "padding": "15px", "backgroundColor": "#ffffff", 
                                                           "borderRadius": "8px", "border": "1px solid #e0e0e0"}),

                # Execute button
                html.Div([
                    html.Button(
                        "Join Data & View Results",
                        id="join-tab-execute-button",
                        style={
                            "backgroundColor": "#28a745",
                            "color": "white",
                            "border": "none",
                            "borderRadius": "6px",
                            "padding": "12px 30px",
                            "fontSize": "16px",
                            "fontWeight": "bold",
                            "cursor": "pointer",
                            "boxShadow": "0 2px 4px rgba(0,0,0,0.1)"
                        }
                    )
                ], id="join-tab-execute-button-div", style={"display": "none", "textAlign": "center", "marginTop": "20px", "marginBottom": "20px"}),
                
                # Error message div
                html.Div([
                    html.Div([
                        html.Strong("⚠️ Please select at least one data source", style={"color": "#dc3545"}),
                        html.P("You need to select at least one column from either Maternal Tree Data or Garden Climate Data to proceed.", 
                               style={"color": "#666", "marginTop": "5px", "marginBottom": "0", "fontSize": "0.9em"})
                    ])
                ], id="join-tab-execute-error", style={"display": "none", "textAlign": "center", "marginTop": "20px",
                                                       "padding": "15px", "backgroundColor": "#fff3cd", 
                                                       "borderRadius": "8px", "border": "1px solid #ffc107"}),
                
                # Join execution div - only shows after successful execution
                dcc.Loading(children=[
                    html.Div([
                    html.H4("Results", style={"marginBottom": "15px", "color": "#133817"}),
                    html.Div([
                        html.Strong("SQL Query:", style={"display": "block", "marginBottom": "5px"}),
                        html.Div(id="join-tab-sql-query", style={"fontFamily": "monospace", "backgroundColor": "#f8f9fa", 
                                                          "padding": "10px", "borderRadius": "5px", 
                                                          "marginBottom": "15px", "overflowX": "auto", "fontSize": "0.85em"})
                    ], style={"marginBottom": "20px"}),
                    html.Div([
                        html.P("💡 Tip: Use the column headers to filter and sort. Click column headers to sort, or use the filter boxes below headers to filter.", 
                               style={"color": "#666", "fontSize": "0.9em", "fontStyle": "italic", "marginBottom": "10px", 
                                      "padding": "10px", "backgroundColor": "#e7f3ff", "borderRadius": "5px"})
                    ]),
                    html.Div([
                        # DataTable in layout so callbacks can reference it
                        dash_table.DataTable(
                            id="join-tab-datatable",
                            data=[],
                            columns=[],
                            page_size=25,
                            page_action="native",
                            filter_action="native",
                            sort_action="native",
                            sort_mode="multi",
                            style_table={"overflowX": "auto"},
                            style_cell={
                                "textAlign": "left",
                                "padding": "10px",
                                "fontSize": "12px",
                            },
                            style_header={
                                "backgroundColor": "#f0f0f0",
                                "fontWeight": "bold",
                                "textAlign": "center",
                            },
                            style_data={
                                "whiteSpace": "normal",
                                "height": "auto",
                            },
                            style_data_conditional=[
                                {
                                    "if": {"row_index": "odd"},
                                    "backgroundColor": "#f9f9f9",
                                }
                            ],
                        )
                    ], id="join-tab-results-table"),
                    html.Div([
                        html.Div(id="join-tab-results-stats", style={"marginTop": "15px", "color": "#666", "fontSize": "0.95em"}),
                        html.Div([
                            html.Div([
                                html.Label("Customize filename (optional):", style={"fontWeight": "bold", "marginBottom": "5px", "fontSize": "0.9em"}),
                                html.Div([
                                    dcc.Input(
                                        id="join-tab-csv-filename",
                                        type="text",
                                        placeholder="joined_data",
                                        value="joined_data",
                                        style={
                                            "padding": "8px 12px",
                                            "border": "1px solid #ccc",
                                            "borderRadius": "4px",
                                            "fontSize": "14px",
                                            "width": "250px",
                                            "marginRight": "10px"
                                        }
                                    ),
                                    html.Span(".csv", style={"fontSize": "14px", "color": "#666"})
                                ], style={"display": "flex", "alignItems": "center", "marginBottom": "15px"})
                            ], style={"marginTop": "15px", "marginBottom": "10px"}),
                            html.Div([
                                html.Button(
                                    "Download Filtered/Sorted Data (CSV)",
                                    id="download-join-tab-csv-button",
                                    style={
                                        "backgroundColor": "#007bff",
                                        "color": "white",
                                        "border": "none",
                                        "borderRadius": "4px",
                                        "padding": "8px 20px",
                                        "fontSize": "14px",
                                        "cursor": "pointer",
                                        "marginRight": "10px"
                                    }
                                ),
                                html.Button(
                                    "Download All Data (CSV)",
                                    id="download-join-tab-all-csv-button",
                                    style={
                                        "backgroundColor": "#28a745",
                                        "color": "white",
                                        "border": "none",
                                        "borderRadius": "4px",
                                        "padding": "8px 20px",
                                        "fontSize": "14px",
                                        "cursor": "pointer"
                                    }
                                ),
                            ], style={"display": "flex", "flexWrap": "wrap", "gap": "10px"}),
                        ]),
                        dcc.Download(id="download-join-tab-csv"),
                        dcc.Download(id="download-join-tab-all-csv")
                    ])

                ], id="join-tab-results-div", style={"display": "none", "padding": "20px", "backgroundColor": "#ffffff", 
                                                     "borderRadius": "8px", "border": "1px solid #e0e0e0"})
            ], type="circle", color="#28a745", id="join-loading-outer")
            ]
        )
    ]
) 

# Track tab selection state
@callback(
    Output('joins-tab-active', 'data'),
    [Input('main-tabs', 'value')]  
)
def set_tab_active(tab_value):
    return tab_value == 'joins-tab'

# Reset all components when tab is switched
@callback(
    [Output('join-tab-core-dropdown', 'value', allow_duplicate=True),
     Output('join-core-table-options', 'options', allow_duplicate=True),
     Output('join-core-table-options', 'value', allow_duplicate=True),
     Output('join-tree-table-options', 'options', allow_duplicate=True),
     Output('join-tree-table-options', 'value', allow_duplicate=True),
     Output('join-garden-table-options', 'options', allow_duplicate=True),
     Output('join-garden-table-options', 'value', allow_duplicate=True),
     Output('join-table-columns-container', 'style', allow_duplicate=True),
     Output('join-tree-table-columns-container', 'style', allow_duplicate=True),
     Output('join-garden-table-columns-container', 'style', allow_duplicate=True),
     Output('join-tab-execute-button-div', 'style', allow_duplicate=True),
     Output('join-tab-execute-error', 'style', allow_duplicate=True),
     Output('join-tab-results-div', 'style', allow_duplicate=True),
     Output('join-tab-sql-query', 'children', allow_duplicate=True),
     Output('join-tab-results-stats', 'children', allow_duplicate=True),
     Output('join-tab-preview-container', 'style', allow_duplicate=True),
     Output('join-tab-preview', 'children', allow_duplicate=True),
     Output('join-tab-full-data', 'data', allow_duplicate=True),
     Output('join-tab-datatable', 'data', allow_duplicate=True),
     Output('join-tab-datatable', 'columns', allow_duplicate=True),

     Output('join-tab-csv-filename', 'value', allow_duplicate=True),
     Output('join-total-count', 'data', allow_duplicate=True)],
    [Input('joins-tab-active', 'data')],
    prevent_initial_call=True
)
def reset_tab_data(is_active):
    if not is_active:
        # Reset all controls when leaving the tab
        return (None, [], [], [], [], [], [], 
                {"display": "none"}, {"display": "none"}, {"display": "none"}, 
                {"display": "none"}, {"display": "none"}, {"display": "none"},
                "", "", {"display": "none"}, "", None, [], [], "joined_data", 0)
    else:
        # Don't reset when entering the tab
        return [dash.no_update] * 23

# Reset core table columns when core table changes
@callback(
    [Output('join-core-table-options', 'value', allow_duplicate=True),
     Output('join-tree-table-options', 'value', allow_duplicate=True),
     Output('join-garden-table-options', 'value', allow_duplicate=True),
     Output('join-tab-results-div', 'style', allow_duplicate=True),
     Output('join-tab-execute-error', 'style', allow_duplicate=True),
     Output('join-tab-preview-container', 'style', allow_duplicate=True)],
    [Input('join-tab-core-dropdown', 'value')],
    prevent_initial_call=True
)
def reset_columns_on_table_change(selected_table):
    # Reset all column selections and hide results when core table changes
    return [], [], [], {"display": "none"}, {"display": "none"}, {"display": "none"}

# Handle conditionally rendered variable checklist - AUTO-SELECT ALL BY DEFAULT
@callback(
    [Output("join-core-table-options", "options"),
     Output("join-core-table-options", "value"),
     Output("join-table-columns-container", "style"),
     Output("join-tree-table-options", "options"),
     Output("join-tree-table-options", "value"),
     Output("join-tree-table-columns-container", "style"),
     Output("join-garden-table-options", "options"),
     Output("join-garden-table-options", "value"),
     Output("join-garden-table-columns-container", "style"),
     Output("join-tab-execute-button-div", "style"),
     Output("join-tab-preview-container", "style")],
    [Input("join-tab-core-dropdown", "value")],
)
def update_core_table_columns(selected_table):
    if selected_table is None:
        return [], [], {"display": "none"}, [], [], {"display": "none"}, [], [], {"display": "none"}, {"display": "none"}, {"display": "none"}

    try:
        # Fetch garden table columns
        sample_df = fetch_data_from_sql(f"SELECT TOP 1 * FROM dbo.[{GARDENS_TABLE}]")
        cols = sample_df.columns.tolist()
        GARDENS_TABLE_OPTIONS = [{'label': c, 'value': c} for c in cols]
        gardens_default_values = [c for c in cols]  # Auto-select all

        # Fetch maternal tree table columns
        sample_df = fetch_data_from_sql(f"SELECT TOP 1 * FROM dbo.[{MATERNAL_TREE_TABLE}]")
        cols = sample_df.columns.tolist()
        MATERNAL_TREE_OPTIONS = [{'label': c, 'value': c} for c in cols]
        tree_default_values = [c for c in cols]  # Auto-select all

        # Fetch core table columns
        sample_df = fetch_data_from_sql(f"SELECT TOP 1 * FROM [dbo].[{selected_table}]")
        cols = sample_df.columns.tolist()
        opts = [{'label': c, 'value': c} for c in cols]
        core_default_values = [c for c in cols]  # Auto-select all
        
        return (opts, core_default_values, {"display": "block", "marginBottom": "20px", 
                                            "padding": "15px", "backgroundColor": "#ffffff", 
                                            "borderRadius": "8px", "border": "1px solid #e0e0e0"}, 
                MATERNAL_TREE_OPTIONS, tree_default_values, {"display": "block", "marginBottom": "20px",
                                                              "padding": "15px", "backgroundColor": "#ffffff", 
                                                              "borderRadius": "8px", "border": "1px solid #e0e0e0"}, 
                GARDENS_TABLE_OPTIONS, gardens_default_values, {"display": "block", "marginBottom": "20px",
                                                                  "padding": "15px", "backgroundColor": "#ffffff", 
                                                                  "borderRadius": "8px", "border": "1px solid #e0e0e0"}, 
                {"display": "block", "textAlign": "center", "marginTop": "20px", "marginBottom": "20px"},
                {"display": "block", "marginBottom": "20px", "padding": "15px", "backgroundColor": "#ffffff", 
                 "borderRadius": "8px", "border": "1px solid #e0e0e0"})
    except Exception as e:
        print(f"Error fetching columns: {e}")
        return [], [], {"display": "none"}, [], [], {"display": "none"}, [], [], {"display": "none"}, {"display": "none"}, {"display": "none"}

# Handle Core table Select All and Deselect All buttons
@callback(
    Output('join-core-table-options', 'value', allow_duplicate=True),
    [Input('join-select_all_btn', 'n_clicks'), 
     Input('join-deselect_all_btn', 'n_clicks')],
    [State('join-core-table-options', 'options'), 
     State('join-core-table-options', 'value')],
    prevent_initial_call=True
)
def handle_core_select_buttons(select_all_clicks, deselect_all_clicks, current_options, current_values):
    trigger_id = ctx.triggered_id if ctx.triggered_id else 'no_trigger'

    if trigger_id == 'join-select_all_btn' and current_options:
        return [opt['value'] for opt in current_options]
    if trigger_id == 'join-deselect_all_btn':
        return []
    
    return dash.no_update

# Handle Tree table Select All and Deselect All buttons
@callback(
    Output('join-tree-table-options', 'value', allow_duplicate=True),
    [Input('join-select_all_btn-2', 'n_clicks'), 
     Input('join-deselect_all_btn-2', 'n_clicks')],
    [State('join-tree-table-options', 'options'), 
     State('join-tree-table-options', 'value')],
    prevent_initial_call=True
)
def handle_tree_select_buttons(select_all_clicks, deselect_all_clicks, current_options, current_values):
    trigger_id = ctx.triggered_id if ctx.triggered_id else 'no_trigger'

    if trigger_id == 'join-select_all_btn-2' and current_options:
        return [opt['value'] for opt in current_options]
    if trigger_id == 'join-deselect_all_btn-2':
        return []
    
    return dash.no_update

# Handle Garden table Select All and Deselect All buttons
@callback(
    Output('join-garden-table-options', 'value', allow_duplicate=True),
    [Input('join-select_all_btn-3', 'n_clicks'), 
     Input('join-deselect_all_btn-3', 'n_clicks')],
    [State('join-garden-table-options', 'options'), 
     State('join-garden-table-options', 'value')],
    prevent_initial_call=True
)
def handle_garden_select_buttons(select_all_clicks, deselect_all_clicks, current_options, current_values):
    trigger_id = ctx.triggered_id if ctx.triggered_id else 'no_trigger'

    if trigger_id == 'join-select_all_btn-3' and current_options:
        return [opt['value'] for opt in current_options]
    if trigger_id == 'join-deselect_all_btn-3':
        return []
    
    return dash.no_update

# Update join preview based on selections
@callback(
    [Output("join-tab-preview", "children"),
     Output("join-tab-preview-container", "style", allow_duplicate=True)],
    [Input("join-tab-core-dropdown", "value"),
     Input("join-core-table-options", "value"),
     Input("join-tree-table-options", "value"),
     Input("join-garden-table-options", "value")],
    prevent_initial_call=True
)
def update_join_preview(core_table, core_vars, tree_vars, garden_vars):
    if not core_table:
        return "", {"display": "none"}
    
    preview_parts = []
    
    # Core table info
    core_name = CORE_TABLES.get(core_table, core_table)
    core_count = len(core_vars) if core_vars else 0
    preview_parts.append(html.Div([
        html.Strong(f"{core_name}:"), 
        html.Span(f" {core_count} columns selected", style={"marginLeft": "10px"})
    ], style={"marginBottom": "8px"}))
    
    # Maternal tree info
    if tree_vars:
        tree_count = len(tree_vars)
        preview_parts.append(html.Div([
            html.Strong("Maternal Tree Climate:"), 
            html.Span(f" {tree_count} columns selected", style={"marginLeft": "10px"}),
            html.Br(),
            html.Span("(Matched by Accession + Locality)", style={"fontSize": "0.85em", "color": "#888", "marginLeft": "20px"})
        ], style={"marginBottom": "8px"}))
    
    # Garden climate info
    if garden_vars:
        garden_count = len(garden_vars)
        if core_table == "leaf_traits_2016":
            match_info = "(Matched by Site)"
        else:
            match_info = "(Matched by Year + Site)"
        preview_parts.append(html.Div([
            html.Strong("Garden Climate:"), 
            html.Span(f" {garden_count} columns selected", style={"marginLeft": "10px"}),
            html.Br(),
            html.Span(match_info, style={"fontSize": "0.85em", "color": "#888", "marginLeft": "20px"})
        ], style={"marginBottom": "8px"}))
    
    if not tree_vars and not garden_vars:
        preview_parts.append(html.Div([
            html.Span("ERROR: Select at least one data source to combine", style={"color": "#ffc107", "fontStyle": "italic"})
        ]))
    
    return preview_parts, {"display": "block", "marginBottom": "20px", "padding": "15px", 
                          "backgroundColor": "#ffffff", "borderRadius": "8px", "border": "1px solid #e0e0e0"}

# Main execution callback - handles both validation and execution
@callback(
    [
        Output("join-tab-results-div", "style", allow_duplicate=True),
        Output("join-tab-datatable", "data"),  # Update DataTable data
        Output("join-tab-datatable", "columns"),  # Update DataTable columns
        Output("join-tab-sql-query", "children", allow_duplicate=True),
        Output("join-tab-results-stats", "children", allow_duplicate=True),
        Output("join-tab-full-data", "data"),  # Store full dataframe
        Output("join-tab-csv-filename", "value", allow_duplicate=True),  # Set default filename
        Output("download-join-tab-csv-button", "children", allow_duplicate=True),
        Output("download-join-tab-all-csv-button", "children", allow_duplicate=True),
        Output("join-total-count", "data"),
    ],
    [Input("join-tab-execute-button", "n_clicks")],
    [
        State("join-tab-core-dropdown", "value"),
        State("join-core-table-options", "value"),
        State("join-tree-table-options", "value"),
        State("join-garden-table-options", "value"),
    ],
    prevent_initial_call=True,
)
def execute_join(n_clicks, core_table, core_table_vars, maternal_tree_vars, garden_climate_vars):
    if not n_clicks or not core_table or (not maternal_tree_vars and not garden_climate_vars):
        return {"display": "none"}, [], [], "", "", None, dash.no_update, dash.no_update, dash.no_update, 0

    try:
        # 1) Required core columns
        if core_table == "leaf_traits_2016":
            required_core_cols = ["Accession", "Locality", "Site"]
            garden_key_cols = {"Site"}
        else:
            required_core_cols = ["Accession", "Locality", "Year", "Site"]
            garden_key_cols = {"Year", "Site"}
        tree_key_cols = {"Accession", "Locality"}

        # 2) Core SELECT
        core_cols = required_core_cols[:]
        if core_table_vars:
            core_cols += [c for c in core_table_vars if c not in core_cols]
        core_sel = ", ".join(f"core.[{c}]" for c in core_cols)
        selected_clauses = [core_sel]

        # 3) Clean out any key‐columns from the non‐core selections
        safe_tree_vars   = [c for c in maternal_tree_vars   or [] if c not in tree_key_cols]
        safe_garden_vars = [c for c in garden_climate_vars or [] if c not in garden_key_cols]

        # 4) Maternal‐tree join
        joins = []
        if maternal_tree_vars:
            # only add non‐key columns to SELECT
            if safe_tree_vars:
                tree_sel = ", ".join(
                    f"maternal.[{c}] AS [maternal_{c.replace(' ', '_')}]"
                    for c in safe_tree_vars
                )
                selected_clauses.append(tree_sel)

            # build a subquery that SELECTs keys + only the safe vars
            tree_cols = ["TRY_CAST(TRY_CAST([Accession] AS NUMERIC) AS INT) AS [Accession]",
                         "[Locality]"] \
                        + [f"[{c}]" for c in safe_tree_vars]
            joins.append(f"""
LEFT JOIN (
  SELECT {', '.join(tree_cols)}
  FROM [dbo].[{MATERNAL_TREE_TABLE}]
) maternal
  ON core.[Accession] = maternal.[Accession]
 AND core.[Locality]  = maternal.[Locality]
""".strip())

        # 5) Garden‐climate join
        if garden_climate_vars:
            if safe_garden_vars:
                garden_sel = ", ".join(
                    f"garden.[{c}] AS [garden_{c.replace(' ', '_')}]"
                    for c in safe_garden_vars
                )
                selected_clauses.append(garden_sel)

            if core_table == "leaf_traits_2016":
                garden_cols = ["[Site]"] + [f"[{c}]" for c in safe_garden_vars]
                join_cond   = "core.[Site] = garden.[Site]"
            else:
                garden_cols = ["TRY_CAST(TRY_CAST([Year] AS NUMERIC) AS INT) AS [Year]",
                               "[Site]"] + [f"[{c}]" for c in safe_garden_vars]
                join_cond   = "core.[Year] = garden.[Year] AND core.[Site] = garden.[Site]"

            joins.append(f"""
LEFT JOIN (
  SELECT {', '.join(garden_cols)}
  FROM [dbo].[{GARDENS_TABLE}]
) garden
  ON {join_cond}
""".strip())

        # 6) Assemble & run
        sql_query = f"""
SELECT DISTINCT
  {', '.join(selected_clauses)}
FROM [dbo].[{core_table}] core
{chr(10).join(joins)}
""".strip()
        result_df = fetch_data_from_sql(sql_query)

        # 7) If nothing came back, hide and exit
        if result_df is None or result_df.empty:
            return {"display": "none"}, [], [], sql_query, "", None, dash.no_update, dash.no_update, dash.no_update, 0

        # 8) Prepare data for the table with filtering and sorting enabled
        # Store full dataframe (limit to 10000 rows for performance in display)
        display_df = result_df.head(10000) if len(result_df) > 10000 else result_df
        
        # Prepare data and columns for DataTable
        table_data = display_df.to_dict("records")
        table_columns = [{"name": c, "id": c} for c in display_df.columns]
        
        # Store column info for stats
        total_rows = len(result_df)
        stats_text = f"Total Rows: {total_rows:,}"

        # Store full dataframe as JSON for later use
        full_data_json = result_df.to_dict("records")
        
        # Generate default filename based on core table name
        default_filename = CORE_TABLES.get(core_table, "joined_data").lower().replace(" ", "_").replace("/", "_")
        
        filtered_btn_text = f"Download Filtered Dataset ({len(result_df):,} rows)" #### ATTENTION, has a maximum of 10,000 rows, incorrect
        full_btn_text = f"Download Full Dataset ({total_rows:,} rows)"

        return {"display": "block"}, table_data, table_columns, sql_query, stats_text, full_data_json, default_filename, filtered_btn_text, full_btn_text, total_rows

    except Exception as e:
        err = f"Error executing join: {e}"
        print("SQL Error:", err)
        return {"display": "none"}, [], [], err, "", None, dash.no_update, dash.no_update, dash.no_update, 0
        
# Reset results when any selection changes (but don't show error until execute is clicked)
@callback(
    [Output("join-tab-results-div", "style", allow_duplicate=True)],
    [Input("join-core-table-options", "value"),
     Input("join-tree-table-options", "value"),
     Input("join-garden-table-options", "value")],
    prevent_initial_call=True
)
def reset_results_on_selection_change(core_vars, tree_vars, garden_vars):
    # Hide results whenever selections change
    return [{"display": "none"}]

# Update stats when filtering/sorting changes
@callback(
    [Output("join-tab-results-stats", "children", allow_duplicate=True),
     Output("download-join-tab-csv-button", "children", allow_duplicate=True),
     Output("download-join-tab-all-csv-button", "children", allow_duplicate=True)],
    [Input("join-tab-datatable", "derived_virtual_data"),
     Input("join-total-count", "data")],
    prevent_initial_call=True
)
def update_filtered_stats(filtered_data, total_count):
    # Handle case where DataTable doesn't exist yet or data is missing
    if filtered_data is None:
        return dash.no_update
    
    try:
        filtered_count = len(filtered_data)
        total_count = total_count if total_count else 0
        
        if total_count == 0:
            return dash.no_update
        
        # Extract column info from original stats format if available
        # For now, just show row counts - column info is less critical for filtered view
        if filtered_count >= total_count or filtered_count == 10000: # 10000 is the limit
             stats_text = f"Showing all {total_count:,} rows"
             filtered_btn_text = f"Download Filtered Dataset ({total_count:,} rows)"
        else:
             stats_text = f"Filtered down to {filtered_count:,} of {total_count:,} rows"
             filtered_btn_text = f"Download Filtered Dataset ({filtered_count:,} rows)"
        
        full_btn_text = f"Download Full Dataset ({total_count:,} rows)"
        
        return stats_text, filtered_btn_text, full_btn_text
    except Exception as e:
        print(f"Error updating stats: {e}")
        return dash.no_update

# Download filtered/sorted data from DataTable
@callback(
    Output('download-join-tab-csv', 'data'),
    Input('download-join-tab-csv-button', 'n_clicks'),
    [State('join-tab-datatable', 'derived_virtual_data'),  # Get filtered/sorted data
     State('join-tab-full-data', 'data'),  # Fallback to full data if filtered not available
     State('join-tab-csv-filename', 'value')],  # Get custom filename
    prevent_initial_call=True
)
def download_filtered_join_results(n_clicks, filtered_data, full_data, custom_filename):
    if not n_clicks:
        return dash.no_update
    
    try:
        # Use filtered data if available, otherwise use full data
        # If filtered data length matches the view limit (10000), assume it's unfiltered and use full data
        view_limit = 10000
        total_count = len(full_data) if full_data else 0
        current_view_count = min(total_count, view_limit)
        
        if filtered_data and len(filtered_data) == current_view_count:
            data_to_download = full_data
        else:
            data_to_download = filtered_data if filtered_data else full_data
        
        if not data_to_download:
            return dash.no_update
        
        # Convert data back to DataFrame
        df = pd.DataFrame(data_to_download)
        if df.empty:
            return dash.no_update
        
        # Determine filename - use custom if provided, otherwise default
        if custom_filename and custom_filename.strip():
            # Clean filename (remove invalid characters)
            clean_filename = "".join(c for c in custom_filename.strip() if c.isalnum() or c in (' ', '-', '_')).strip()
            if not clean_filename:
                clean_filename = "joined_data_filtered" if filtered_data and filtered_data != full_data else "joined_data"
            filename = f"{clean_filename}.csv"
        else:
            # Default filename based on whether it's filtered
            filename = "joined_data_filtered.csv" if filtered_data and filtered_data != full_data else "joined_data.csv"
        
        # Trigger download
        return dcc.send_data_frame(
            df.to_csv,
            filename,
            index=False
        )
    except Exception as e:
        print(f"Error during filtered download: {e}")
        return dash.no_update

# Download all data (unfiltered)
@callback(
    Output('download-join-tab-all-csv', 'data'),
    Input('download-join-tab-all-csv-button', 'n_clicks'),
    [State('join-tab-full-data', 'data'),
     State('join-tab-csv-filename', 'value')],  # Get custom filename
    prevent_initial_call=True
)
def download_all_join_results(n_clicks, full_data, custom_filename):
    if not n_clicks or not full_data:
        return dash.no_update
    
    try:
        # Convert stored data back to DataFrame
        df = pd.DataFrame(full_data)
        if df.empty:
            return dash.no_update
        
        # Determine filename - use custom if provided, otherwise default
        if custom_filename and custom_filename.strip():
            # Clean filename (remove invalid characters)
            clean_filename = "".join(c for c in custom_filename.strip() if c.isalnum() or c in (' ', '-', '_')).strip()
            if not clean_filename:
                clean_filename = "joined_data_all"
            filename = f"{clean_filename}_all.csv"
        else:
            filename = "joined_data_all.csv"
        
        # Trigger download
        return dcc.send_data_frame(
            df.to_csv,
            filename,
            index=False
        )
    except Exception as e:
        print(f"Error during full download: {e}")
        return dash.no_update


# Error button
@callback(
    Output("join-tab-execute-error", "style"),
    [Input("join-tab-execute-button", "n_clicks")],
    [State("join-core-table-options", "value"),
     State("join-tree-table-options", "value"),
     State("join-garden-table-options", "value")],
    prevent_initial_call=True
)
def show_error_message(n_clicks, core_table_vars, maternal_tree_vars, garden_climate_vars):
    if n_clicks is None or n_clicks == 0:
        return {"display": "none"}
    
    # Show error message if no maternal tree or garden climate variables are selected
    if not maternal_tree_vars and not garden_climate_vars:
        return {"display": "block", "textAlign": "center", "marginTop": "20px",
                "padding": "15px", "backgroundColor": "#fff3cd", 
                "borderRadius": "8px", "border": "1px solid #ffc107"}
    
    return {"display": "none"}

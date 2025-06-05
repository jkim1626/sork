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
    label="Tab 4",
    id="joins-tab",
    style={"padding": "15px"},
    children=[
        dcc.Store(id='joins-tab-active', data=False),  
        html.Div(
            [
                # Pick the core table
                html.Div([
                    html.Label("Common Garden Dataset:", style={"fontWeight":"bold", "marginBottom":"5px"}),
                    dcc.Dropdown(
                        id="join-tab-core-dropdown",
                        options=[{"label":value, "value":key} for key,value in CORE_TABLES.items()],
                        placeholder="Select a Table"
                    ),
                ], style={"marginBottom":"15px"}),

                # Pick the core table columns
                html.Div([
                    html.Div([
                        html.Label("Select columns to include:", style={"fontWeight": "bold", "marginBottom": "5px"}),
                        html.Button("Select All", id="join-select_all_btn", n_clicks=0, style={"marginLeft": "10px", "fontSize": "0.8em"}),
                        html.Button("Deselect All", id="join-deselect_all_btn", n_clicks=0, style={"marginLeft": "10px", "fontSize": "0.8em"}),
                    ], style={"display": "flex", "alignItems": "center", "marginBottom": "5px"}),
                    dcc.Checklist(id="join-core-table-options", options=[], value=[], inline=False,
                                labelStyle={"display": "block", "marginBottom": "3px"},
                                style={"maxHeight": "200px", "overflowY": "auto", "padding": "10px", "backgroundColor": "#f9f9f9", "borderRadius": "5px"}),
                ], id="join-table-columns-container", style={"display": "none", "marginBottom": "15px"}),

                # Pick the maternal tree table columns
                html.Div([
                    html.Div([
                        html.Label("Select Maternal Tree Data Variables:", style={"fontWeight": "bold", "marginBottom": "5px"}),
                        html.Button("Select All", id="join-select_all_btn-2", n_clicks=0, style={"marginLeft": "10px", "fontSize": "0.8em"}),
                        html.Button("Deselect All", id="join-deselect_all_btn-2", n_clicks=0, style={"marginLeft": "10px", "fontSize": "0.8em"}),
                    ], style={"display": "flex", "alignItems": "center", "marginBottom": "5px"}),
                    dcc.Checklist(id="join-tree-table-options", options=[], value=[], inline=False,
                                labelStyle={"display": "block", "marginBottom": "3px"},
                                style={"maxHeight": "200px", "overflowY": "auto", "padding": "10px", "backgroundColor": "#f9f9f9", "borderRadius": "5px"}),
                ], id="join-tree-table-columns-container", style={"display": "none", "marginBottom": "15px"}),

                # Pick the garden climate variables
                html.Div([
                    html.Div([
                        html.Label("Select Garden Climate Variables:", style={"fontWeight": "bold", "marginBottom": "5px"}),
                        html.Button("Select All", id="join-select_all_btn-3", n_clicks=0, style={"marginLeft": "10px", "fontSize": "0.8em"}),
                        html.Button("Deselect All", id="join-deselect_all_btn-3", n_clicks=0, style={"marginLeft": "10px", "fontSize": "0.8em"}),
                    ], style={"display": "flex", "alignItems": "center", "marginBottom": "5px"}),
                    dcc.Checklist(id="join-garden-table-options", options=[], value=[], inline=False,
                                labelStyle={"display": "block", "marginBottom": "3px"},
                                style={"maxHeight": "200px", "overflowY": "auto", "padding": "10px", "backgroundColor": "#f9f9f9", "borderRadius": "5px"}),
                ], id="join-garden-table-columns-container", style={"display": "none", "marginBottom": "15px"}),


                html.Div([
                    html.Button(
                        "Execute Join",
                        id="join-tab-execute-button",
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
                ], id="join-tab-execute-button-div", style={"display": "none", "textAlign": "center", "marginTop": "20px"}),
                
                # Error message div - separate from results
                html.Div([
                    html.Label("Cannot Complete Execute without Selecting Maternal Tree or Garden Climate Variables", 
                              style={"fontWeight": "bold", "marginBottom": "5px", "color": "red"})
                ], id="join-tab-execute-error", style={"display": "none", "textAlign": "center", "marginTop": "20px"}),
                
                # Join execution div - only shows after successful execution
                html.Div([
                    html.H5("Join Preview", style={"marginBottom": "15px"}),
                    html.Div(id="join-tab-sql-query", style={"fontFamily": "monospace", "backgroundColor": "#f8f9fa", 
                                                      "padding": "10px", "borderRadius": "5px", 
                                                      "marginBottom": "15px", "overflowX": "auto"}),
                    dcc.Loading(
                        html.Div(id="join-tab-results-table"),
                        type="circle"
                    ),
                    html.Div([
                        html.Div(id="join-tab-results-stats", style={"marginTop": "15px", "color": "#666"}),
                        html.Button(
                            "Download CSV",
                            id="download-join-tab-csv-button",
                            style={
                                "backgroundColor": "#28a745",
                                "color": "white",
                                "border": "none",
                                "borderRadius": "4px",
                                "padding": "5px 15px",
                                "marginTop": "15px"
                            }
                        ),
                        dcc.Download(id="download-join-tab-csv")
                    ])
                ], id="join-tab-results-div", style={"display": "none"})
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
     Output('join-tab-results-table', 'children', allow_duplicate=True),
     Output('join-tab-results-stats', 'children', allow_duplicate=True)],
    [Input('joins-tab-active', 'data')],
    prevent_initial_call=True
)
def reset_tab_data(is_active):
    if not is_active:
        # Reset all controls when leaving the tab
        return (None, [], [], [], [], [], [], 
                {"display": "none"}, {"display": "none"}, {"display": "none"}, 
                {"display": "none"}, {"display": "none"}, {"display": "none"},
                "", [], "")
    else:
        # Don't reset when entering the tab
        return [dash.no_update] * 16

# Reset core table columns when core table changes
@callback(
    [Output('join-core-table-options', 'value', allow_duplicate=True),
     Output('join-tree-table-options', 'value', allow_duplicate=True),
     Output('join-garden-table-options', 'value', allow_duplicate=True),
     Output('join-tab-results-div', 'style', allow_duplicate=True),
     Output('join-tab-execute-error', 'style', allow_duplicate=True)],
    [Input('join-tab-core-dropdown', 'value')],
    prevent_initial_call=True
)
def reset_columns_on_table_change(selected_table):
    # Reset all column selections and hide results when core table changes
    return [], [], [], {"display": "none"}, {"display": "none"}

# Handle conditionally rendered variable checklist
@callback(
    [Output("join-core-table-options", "options"),
     Output("join-table-columns-container", "style"),
     Output("join-tree-table-options", "options"),
     Output("join-tree-table-columns-container", "style"),
     Output("join-garden-table-options", "options"),
     Output("join-garden-table-columns-container", "style"),
     Output("join-tab-execute-button-div", "style")],
    [Input("join-tab-core-dropdown", "value")],
)
def update_core_table_columns(selected_table):
    if selected_table is None:
        return [], {"display": "none"}, [], {"display": "none"}, [], {"display": "none"}, {"display": "none"}

    try:
        # Fetch garden table columns
        sample_df = fetch_data_from_sql(f"SELECT TOP 1 * FROM dbo.[{GARDENS_TABLE}]")
        cols = sample_df.columns.tolist()
        GARDENS_TABLE_OPTIONS = [{'label': c, 'value': c} for c in cols]

        # Fetch maternal tree table columns
        sample_df = fetch_data_from_sql(f"SELECT TOP 1 * FROM dbo.[{MATERNAL_TREE_TABLE}]")
        cols = sample_df.columns.tolist()
        MATERNAL_TREE_OPTIONS = [{'label': c, 'value': c} for c in cols]

        # Fetch core table columns
        sample_df = fetch_data_from_sql(f"SELECT TOP 1 * FROM [dbo].[{selected_table}]")
        cols = sample_df.columns.tolist()
        opts = [{'label': c, 'value': c} for c in cols]
        
        return (opts, {"display": "block", "marginBottom": "15px"}, 
                MATERNAL_TREE_OPTIONS, {"display": "block", "marginBottom": "15px"}, 
                GARDENS_TABLE_OPTIONS, {"display": "block", "marginBottom": "15px"}, 
                {"display": "block", "textAlign": "center", "marginTop": "20px"})
    except Exception as e:
        print(f"Error fetching columns: {e}")
        return [], {"display": "none"}, [], {"display": "none"}, [], {"display": "none"}, {"display": "none"}

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

# Main execution callback - handles both validation and execution
@callback(
    [
        Output("join-tab-results-div", "style", allow_duplicate=True),
        Output("join-tab-results-table", "children", allow_duplicate=True),
        Output("join-tab-sql-query", "children", allow_duplicate=True),
        Output("join-tab-results-stats", "children", allow_duplicate=True),
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
        return {"display": "none"}, [], "", ""

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
            return {"display": "none"}, [], sql_query, ""

        # 8) Build the table and stats
        table = dash_table.DataTable(
            data=result_df.head(1000).to_dict("records"),
            columns=[{"name": c, "id": c} for c in result_df.columns],
            page_size=15,
            style_table={"overflowX": "auto"},
        )
        stats_text = f"{len(result_df)} rows | {len(core_cols)} core cols | " \
                     f"{len(safe_tree_vars)} maternal cols | {len(safe_garden_vars)} garden cols"

        return {"display": "block"}, table, sql_query, stats_text

    except Exception as e:
        err = f"Error executing join: {e}"
        print("SQL Error:", err)
        return {"display": "none"}, [], err, ""
        
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

# Download functionality
@callback(
    Output('download-join-tab-csv', 'data'),
    Input('download-join-tab-csv-button', 'n_clicks'),
    State("join-tab-core-dropdown", "value"),
    State("join-core-table-options", "value"),
    State("join-tree-table-options", "value"),
    State("join-garden-table-options", "value"),
    prevent_initial_call=True
)
def download_join_results(n_clicks, core_table, core_table_vars, maternal_tree_vars, garden_climate_vars):
    if not n_clicks:
        return dash.no_update

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
        # guard against None or empty
        if result_df is None or result_df.empty:
            return dash.no_update

        # 6) Trigger download
        return dcc.send_data_frame(
            result_df.to_csv,
            f"{core_table}_joined_data.csv",
            index=False
        )

    except Exception as e:
        print(f"Error during download: {e}")
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
        return {"display": "block", "color": "red", "fontWeight": "bold", "marginBottom": "5px", "textAlign": "center"}
    
    return {"display": "none"}
from dash import dcc, html, Input, Output, State, callback, ctx
from dash.exceptions import PreventUpdate
import dash
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats
from database import fetch_data_from_sql
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from dotenv import load_dotenv
import os
from datetime import datetime

# Import join utilities
from tabs.joins import (
    create_join_ui, 
    CORE_TABLES, 
    ALLOWED_CORE_TABLES,
    MATERNAL_TREE_TABLE,
    GARDENS_TABLE,
    validate_table_name,
    get_column_lists_cached,
    generate_join_query
)

# Load environment variables
load_dotenv(override=True)

# Table Options - Hardcoded whitelist
table_options = os.getenv("TABLE_OPTIONS").split(",")
ALLOWED_TABLES = set(table_options)

# ===== CONFIGURATION CONSTANTS =====

# Sampling configuration
DEFAULT_SAMPLE_SIZE = 50000
MIN_SAMPLE_SIZE = 10000
MEDIUM_SAMPLE_SIZE = 20000

# Minimum data requirements
MIN_ROWS_FOR_REGRESSION = 3
MIN_ROWS_FOR_PCA = 3
MIN_VARS_FOR_PCA = 2

# Statistical test options
stat_test_options = [
    {'label': 'Linear Regression', 'value': 'linear_regression'},
    {'label': 'Principal Component Analysis (PCA)', 'value': 'pca'},
    {'label': 'Summary Statistics', 'value': 'summary_stats'}
]

# Create the layout for the stats tab
stats_layout = dcc.Tab(
    label="Statistics",
    id="stats-tab",
    style={"padding": "15px"},
    children=[
        # Store the tab's active state
        dcc.Store(id="stats-tab-active", data=False),
        
        # Store for table metadata (row counts, numeric columns)
        dcc.Store(id="stats-metadata-store", data={}),
        
        # Store for join query and metadata
        dcc.Store(id='stats-join-query-store'),
        
        html.Br(),
        html.H4("Statistical Analysis", style={"marginBottom": "20px"}),

        # Table selection (will include Custom Join option)
        html.Label("1) Select a table or create custom join", style={"fontWeight": "bold", "marginBottom": "5px", "fontSize": "16px"}), 
        dcc.Dropdown(id="stats-table-dropdown", placeholder="Select Table or Custom Join"),
        
        # Join UI container (hidden initially, shown when Custom Join selected)
        html.Div([
            html.Br(),
            create_join_ui("stats")
        ], id="stats-join-ui-wrapper", style={"display": "none"}),
        
        # Test selection (hidden until table/join is ready)
        html.Div([
            html.Label("2) Select analysis type", style={"fontWeight": "bold", "marginTop": "20px", "marginBottom": "5px", "fontSize": "16px"}),
            dcc.Dropdown(stat_test_options, id="stats-test-dropdown", placeholder="Statistical Test Options"),
        ], id="test-selection-div", style={"display": "none"}),
        
        # Containers for each test type
        html.Div([
            # Linear Regression
            html.Div([
                html.Label("3) Select variables for Linear Regression", style={"fontWeight": "bold", "marginTop": "20px", "marginBottom": "5px"}),
                html.Div([
                    html.Label("X-axis:", style={"marginRight": "10px"}),
                    dcc.Dropdown(id="lr-x-variable", placeholder="Select x Variable"),
                ], style={"marginBottom": "10px"}),
                html.Div([
                    html.Label("Y-axis:", style={"marginRight": "10px"}),
                    dcc.Dropdown(id="lr-y-variable", placeholder="Select y Variable"),
                ], style={"marginBottom": "10px"}),
                html.Button("Generate Regression", id="run-lr-button", n_clicks=0,
                           style={
                               "backgroundColor": "#007bff",
                               "color": "white",
                               "border": "none",
                               "borderRadius": "4px",
                               "padding": "5px 15px",
                               "marginTop": "10px"
                           }),
                html.Div(id="lr-output", style={"marginTop": "20px"}, children=[
                    dcc.Loading(id="lr-loading", type="default", children=html.Div(id="lr-output-content"))
                ]),
                # Hidden full dataset button
                html.Div(id="lr-full-button-container", style={"display": "none"}, children=[
                    html.Button(
                        "🔄 Analyze Full Dataset",
                        id="run-lr-full",
                        n_clicks=0,
                        style={
                            "backgroundColor": "#28a745",
                            "color": "white",
                            "border": "none",
                            "borderRadius": "4px",
                            "padding": "5px 15px",
                            "marginTop": "10px",
                            "cursor": "pointer"
                        }
                    )
                ])
            ], id="linear-regression-div", style={"display": "none"}),
            
            # PCA
            html.Div([
                html.Label("3) Select variables for PCA", style={"fontWeight": "bold", "marginTop": "20px", "marginBottom": "5px"}),
                html.Div([
                    html.Label("Select numeric columns (minimum 2):", style={"marginRight": "10px"}),
                    dcc.Dropdown(id="pca-variables", placeholder="Variables", multi=True),
                ], style={"marginBottom": "10px"}),
                html.Div([
                    html.Label("Visualization:", style={"marginRight": "10px"}),
                    dcc.RadioItems(
                        id='pca-dimensions',
                        options=[
                            {'label': '2D ', 'value': '2d'},
                            {'label': '3D ', 'value': '3d'}
                        ],
                        value='2d',
                        inline=True,
                        style={"marginBottom": "10px"}
                    ),
                ]),
                html.Button("Generate PCA", id="run-pca-button", n_clicks=0,
                           style={
                               "backgroundColor": "#007bff",
                               "color": "white",
                               "border": "none",
                               "borderRadius": "4px",
                               "padding": "5px 15px",
                               "marginTop": "10px"
                           }),
                # Warning message for insufficient variables
                html.Div(id="pca-warning", style={"marginTop": "10px"}),
                html.Div(id="pca-output", style={"marginTop": "20px"}, children=[
                    dcc.Loading(id="pca-loading", type="default", children=html.Div(id="pca-output-content"))
                ]),
                # Hidden full dataset button
                html.Div(id="pca-full-button-container", style={"display": "none"}, children=[
                    html.Button(
                        "🔄 Analyze Full Dataset",
                        id="run-pca-full",
                        n_clicks=0,
                        style={
                            "backgroundColor": "#28a745",
                            "color": "white",
                            "border": "none",
                            "borderRadius": "4px",
                            "padding": "5px 15px",
                            "marginTop": "10px",
                            "cursor": "pointer"
                        }
                    )
                ])
            ], id="pca-div", style={"display": "none"}),
            
            # Summary Statistics
            html.Div([
                html.Label("3) Select Variable for Summary Statistics", style={"fontWeight": "bold", "marginTop": "20px", "marginBottom": "5px"}),
                html.Div([
                    dcc.Dropdown(id="summary-variable", placeholder="Variables"),
                ], style={"marginBottom": "10px"}),
                html.Button("Generate Summary", id="run-summary-button", n_clicks=0,
                           style={
                               "backgroundColor": "#007bff",
                               "color": "white",
                               "border": "none",
                               "borderRadius": "4px",
                               "padding": "5px 15px",
                               "marginTop": "10px"
                           }),
                html.Div(id="summary-output", style={"marginTop": "20px"}, children=[
                    dcc.Loading(id="summary-loading", type="default", children=html.Div(id="summary-output-content"))
                ]),
                # Hidden full dataset button
                html.Div(id="summary-full-button-container", style={"display": "none"}, children=[
                    html.Button(
                        "🔄 Analyze Full Dataset",
                        id="run-summary-full",
                        n_clicks=0,
                        style={
                            "backgroundColor": "#28a745",
                            "color": "white",
                            "border": "none",
                            "borderRadius": "4px",
                            "padding": "5px 15px",
                            "marginTop": "10px",
                            "cursor": "pointer"
                        }
                    )
                ])
            ], id="summary-stats-div", style={"display": "none"}),
            
        ], id="test-container", style={"display": "none"}),
        
        # Placeholder message
        html.Div(id="stats-placeholder", children=[
            html.Div(
                html.H5("Select a table and analysis type to begin", 
                        style={"textAlign": "center", "marginTop": "50px", "color": "#666"})
            )
        ]),
    ]
)



# ===== HELPERS =====

# Validate table name against whitelist
def validate_table_name_stats(table_name):
    if table_name not in ALLOWED_TABLES and table_name != "__custom_join__":
        raise ValueError(f"Invalid table name: {table_name}")
    return table_name

# Get approximate row count using sys.partitions
def get_table_row_count(table_name):
    try:
        validate_table_name_stats(table_name)
        query = f"""
        SELECT SUM(p.rows) AS row_count
        FROM sys.partitions p
        INNER JOIN sys.objects o ON p.object_id = o.object_id
        WHERE o.name = '{table_name}' 
          AND p.index_id IN (0, 1)
        """
        result = fetch_data_from_sql(query)
        if result is not None and not result.empty:
            return int(result.iloc[0]['row_count'])
        return None
    except Exception as e:
        print(f"Error fetching row count for {table_name}: {e}")
        return None

# Get numeric column names from INFORMATION_SCHEMA
def get_numeric_column_names(table_name):
    try:
        validate_table_name_stats(table_name)
        query = f"""
        SELECT COLUMN_NAME, DATA_TYPE 
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_NAME = '{table_name}'
        ORDER BY ORDINAL_POSITION
        """
        result = fetch_data_from_sql(query)
        if result is not None and not result.empty:
            # Known numeric types in SQL Server
            numeric_types = {
                'int', 'bigint', 'smallint', 'tinyint',
                'decimal', 'numeric', 'float', 'real',
                'money', 'smallmoney'
            }
            numeric_cols = result[result['DATA_TYPE'].str.lower().isin(numeric_types)]['COLUMN_NAME'].tolist()
            return numeric_cols
        return []
    except Exception as e:
        print(f"Error fetching numeric columns for {table_name}: {e}")
        return []

# Calculate appropriate sample size based on total rows
def calculate_sample_size(total_rows):
    if total_rows <= MIN_SAMPLE_SIZE:
        return total_rows  # Use all data
    elif total_rows <= 100000:
        return min(MEDIUM_SAMPLE_SIZE, total_rows)  # 20K sample for medium tables
    else:
        return DEFAULT_SAMPLE_SIZE  # 50K sample for large tables

# Format sample size information for display
def format_sample_info(sample_size, total_rows):
    if sample_size >= total_rows:
        return f"✓ Analysis based on all {total_rows:,} rows"
    else:
        percentage = (sample_size / total_rows) * 100
        return f"✓ Analysis based on {sample_size:,} rows ({percentage:.1f}% of total {total_rows:,} rows)"



# ===== CALLBACKS =====

# Track tab selection state
@callback(
    Output('stats-tab-active', 'data'),
    [Input('main-tabs', 'value')]
)
def set_stats_tab_active(tab_value):
    return tab_value == 'stats-tab'

# Update dropdown options to include Custom Join
@callback(
    Output('stats-table-dropdown', 'options'),
    Input('stats-tab-active', 'data'),
    prevent_initial_call=False
)
def update_stats_table_options(is_active):
    # Start with regular table options
    options = [{'label': table, 'value': table} for table in table_options]
    
    # Add Custom Join option at the top
    options.insert(0, {'label': '--- Custom Join ---', 'value': 'custom_join'})
    
    return options

# Show/hide join UI and control test selection based on table selection
@callback(
    [Output('stats-join-ui-wrapper', 'style'),
     Output('stats-join-ui-container', 'style'),
     Output('test-selection-div', 'style', allow_duplicate=True),
     Output('test-container', 'style', allow_duplicate=True),
     Output('stats-placeholder', 'style', allow_duplicate=True)],
    [Input('stats-table-dropdown', 'value')],
    prevent_initial_call=True
)
def control_join_ui_visibility(selected_value):
    if selected_value == 'custom_join':
        # Show join UI, hide test selection and test container
        return (
            {"display": "block"},  # wrapper
            {"display": "block"},  # join UI container
            {"display": "none"},   # test selection
            {"display": "none"},   # test container
            {"display": "none"}    # placeholder
        )
    elif selected_value == "__custom_join__":
        # Custom join executed - keep join UI visible AND show test selection
        return (
            {"display": "block"},  # wrapper - keep visible
            {"display": "block"},  # join UI container - keep visible
            {"display": "block"},  # test selection - now visible
            {"display": "none"},   # test container
            {"display": "none"}    # placeholder
        )
    elif selected_value is None:
        # Nothing selected - show placeholder
        return (
            {"display": "none"},   # wrapper
            {"display": "none"},   # join UI container
            {"display": "none"},   # test selection
            {"display": "none"},   # test container
            {"display": "block"}   # placeholder
        )
    else:
        # Regular table selected - hide join UI, show test selection
        return (
            {"display": "none"},   # wrapper
            {"display": "none"},   # join UI container
            {"display": "block"},  # test selection
            {"display": "none"},   # test container
            {"display": "none"}    # placeholder
        )

# Reset join UI when custom join is selected
@callback(
    [Output('stats-join-core-dropdown', 'value'),
     Output('stats-join-core-table-options', 'value'),
     Output('stats-join-tree-table-options', 'value'),
     Output('stats-join-garden-table-options', 'value')],
    [Input('stats-table-dropdown', 'value')],
    prevent_initial_call=True
)
def reset_join_ui(selected_value):
    if selected_value == 'custom_join':
        # Reset to empty
        return None, [], [], []
    else:
        raise PreventUpdate

# Reset all components when tab is switched
@callback(
    [Output('stats-table-dropdown', 'value', allow_duplicate=True),
     Output('stats-test-dropdown', 'value', allow_duplicate=True),
     Output('lr-x-variable', 'value', allow_duplicate=True),
     Output('lr-y-variable', 'value', allow_duplicate=True),
     Output('pca-variables', 'value', allow_duplicate=True),
     Output('summary-variable', 'value', allow_duplicate=True),
     Output('lr-output-content', 'children', allow_duplicate=True),
     Output('pca-output-content', 'children', allow_duplicate=True),
     Output('summary-output-content', 'children', allow_duplicate=True)],
    [Input('stats-tab-active', 'data')],
    prevent_initial_call=True
)
def reset_stats_tab_data(is_active):
    if is_active:
        raise PreventUpdate
    # Reset all controls when leaving the tab
    return None, None, None, None, None, None, html.Div(), html.Div(), html.Div()

# Fetch and cache table metadata when table is selected (handles both regular tables and custom join)
@callback(
    [Output('stats-metadata-store', 'data'),
     Output('test-selection-div', 'style', allow_duplicate=True),
     Output('stats-placeholder', 'style', allow_duplicate=True)],
    [Input('stats-table-dropdown', 'value'),
     Input('stats-join-query-store', 'data')],
    [State('stats-metadata-store', 'data')],
    prevent_initial_call=True
)
def fetch_stats_metadata(selected_table, join_query_data, metadata_store):
    # Don't proceed if Custom Join selected (will be handled after execution)
    if selected_table == 'custom_join':
        raise PreventUpdate
    
    if selected_table is None:
        return metadata_store, {"display": "none"}, {"display": "block"}
    
    # Handle custom join
    if selected_table == "__custom_join__":
        if not join_query_data:
            return metadata_store, {"display": "none"}, {"display": "block"}
        
        # Check if already cached
        if "__custom_join__" in metadata_store:
            return metadata_store, {"display": "block"}, {"display": "none"}
        
        # Fetch metadata for joined table
        try:
            total_rows = join_query_data.get('total_rows', 0)
            
            # Get numeric columns by fetching a sample
            base_query = join_query_data.get('base_query')
            sample_query = f"SELECT TOP 1 * FROM ({base_query}) AS sample"
            sample_df = fetch_data_from_sql(sample_query)
            
            if sample_df is None or sample_df.empty:
                return metadata_store, {"display": "none"}, {"display": "block"}
            
            # Detect numeric columns
            numeric_columns = []
            for col in sample_df.columns:
                if pd.api.types.is_numeric_dtype(sample_df[col]):
                    numeric_columns.append(col)
            
            # Store metadata
            metadata_store["__custom_join__"] = {
                'row_count': total_rows,
                'numeric_columns': numeric_columns
            }
            
            return metadata_store, {"display": "block"}, {"display": "none"}
            
        except Exception as e:
            print(f"Error fetching custom join metadata: {e}")
            return metadata_store, {"display": "none"}, {"display": "block"}
    
    # Handle regular tables
    try:
        validate_table_name_stats(selected_table)
        
        # Check if metadata already cached
        if selected_table in metadata_store:
            return metadata_store, {"display": "block"}, {"display": "none"}
        
        # Fetch metadata
        row_count = get_table_row_count(selected_table)
        numeric_columns = get_numeric_column_names(selected_table)
        
        if not numeric_columns:
            print(f"Warning: No numeric columns found in {selected_table}")
        
        # Store metadata
        metadata_store[selected_table] = {
            'row_count': row_count,
            'numeric_columns': numeric_columns
        }
        
        return metadata_store, {"display": "block"}, {"display": "none"}
        
    except Exception as e:
        error_msg = f"Error loading table metadata: {str(e)}"
        print(error_msg)
        return metadata_store, {"display": "none"}, {"display": "block"}

# Reset dependent controls when table changes
@callback(
    [Output('stats-test-dropdown', 'value', allow_duplicate=True),
     Output('lr-x-variable', 'value', allow_duplicate=True),
     Output('lr-y-variable', 'value', allow_duplicate=True),
     Output('pca-variables', 'value', allow_duplicate=True),
     Output('summary-variable', 'value', allow_duplicate=True),
     Output('lr-output-content', 'children', allow_duplicate=True),
     Output('pca-output-content', 'children', allow_duplicate=True),
     Output('summary-output-content', 'children', allow_duplicate=True)],
    [Input('stats-table-dropdown', 'value')],
    prevent_initial_call=True
)
def reset_on_table_change(selected_table):
    if selected_table:
        # Reset analysis-related controls but show test selection
        return None, None, None, None, None, html.Div(), html.Div(), html.Div()
    else:
        # Hide everything when no table is selected
        return None, None, None, None, None, html.Div(), html.Div(), html.Div()

# Callback to show appropriate test container based on selection
@callback(
    [Output("test-container", "style", allow_duplicate=True),
     Output("linear-regression-div", "style", allow_duplicate=True),
     Output("pca-div", "style", allow_duplicate=True),
     Output("summary-stats-div", "style", allow_duplicate=True),
     Output('lr-output-content', 'children', allow_duplicate=True),
     Output('pca-output-content', 'children', allow_duplicate=True),
     Output('summary-output-content', 'children', allow_duplicate=True)],
    [Input("stats-test-dropdown", "value")],
    prevent_initial_call=True
)
def show_test_container(selected_test):
    # Reset outputs when test type changes
    empty_output = html.Div()
    
    if not selected_test:
        return {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}, empty_output, empty_output, empty_output
    
    lr_style = {"display": "block"} if selected_test == "linear_regression" else {"display": "none"}
    pca_style = {"display": "block"} if selected_test == "pca" else {"display": "none"}
    summary_style = {"display": "block"} if selected_test == "summary_stats" else {"display": "none"}
    
    return {"display": "block"}, lr_style, pca_style, summary_style, empty_output, empty_output, empty_output

# Callback to populate dropdowns with numeric columns from cache
@callback(
    [Output("lr-x-variable", "options"),
     Output("lr-y-variable", "options"),
     Output("pca-variables", "options"),
     Output("summary-variable", "options")],
    [Input("stats-table-dropdown", "value"),
     Input("stats-metadata-store", "data")]
)
def update_variable_options(selected_table, metadata_store):
    # Handle custom join case
    actual_table = "__custom_join__" if selected_table == 'custom_join' or selected_table == '__custom_join__' else selected_table
    
    if not actual_table or actual_table not in metadata_store:
        return [], [], [], []
    
    try:
        numeric_cols = metadata_store[actual_table].get('numeric_columns', [])
        options = [{"label": col, "value": col} for col in numeric_cols]
        return options, options, options, options
    except Exception as e:
        print(f"Error updating variable options: {e}")
        return [], [], [], []

# Clear PCA warning when variables are selected
@callback(
    Output("pca-warning", "children", allow_duplicate=True),
    [Input("pca-variables", "value")],
    prevent_initial_call=True
)
def clear_pca_warning(variables):
    """Clear warning when user changes variable selection."""
    return html.Div()


# ===== JOIN-RELATED CALLBACKS (with stats- prefix) =====

# Populate join column options when core table is selected
@callback(
    [Output("stats-join-core-table-options", "options"),
     Output("stats-join-table-columns-container", "style"),
     Output("stats-join-tree-table-options", "options"),
     Output("stats-join-tree-table-columns-container", "style"),
     Output("stats-join-garden-table-options", "options"),
     Output("stats-join-garden-table-columns-container", "style"),
     Output("stats-join-execute-button-div", "style"),
     Output("stats-join-preview-container", "style"),
     Output("stats-join-general-error", "children")],
    [Input("stats-join-core-dropdown", "value")]
)
def update_join_column_options(selected_table):
    if selected_table is None:
        return [], {"display": "none"}, [], {"display": "none"}, [], {"display": "none"}, {"display": "none"}, {"display": "none"}, ""

    try:
        # Validate table name
        validate_table_name(selected_table, ALLOWED_CORE_TABLES)
        
        # Get column data directly
        column_data = get_column_lists_cached({})
        
        # Get columns from cache
        gardens_cols = column_data.get('gardens_columns', [])
        tree_cols = column_data.get('tree_columns', [])
        
        # Create options (default: none selected)
        GARDENS_TABLE_OPTIONS = [{'label': c, 'value': c} for c in gardens_cols]
        MATERNAL_TREE_OPTIONS = [{'label': c, 'value': c} for c in tree_cols]

        # Fetch core table columns
        sample_df = fetch_data_from_sql(f"SELECT TOP 1 * FROM [dbo].[{selected_table}]")
        if sample_df is None or sample_df.empty:
            error_msg = "Error: Could not fetch columns from selected table"
            return [], {"display": "none"}, [], {"display": "none"}, [], {"display": "none"}, {"display": "none"}, {"display": "none"}, error_msg
        
        cols = sample_df.columns.tolist()
        opts = [{'label': c, 'value': c} for c in cols]
        
        return (opts, {"display": "block", "marginBottom": "20px", "padding": "15px", "backgroundColor": "#ffffff", "borderRadius": "8px", "border": "1px solid #e0e0e0"}, 
                MATERNAL_TREE_OPTIONS, {"display": "block", "marginBottom": "20px", "padding": "15px", "backgroundColor": "#ffffff", "borderRadius": "8px", "border": "1px solid #e0e0e0"}, 
                GARDENS_TABLE_OPTIONS, {"display": "block", "marginBottom": "20px", "padding": "15px", "backgroundColor": "#ffffff", "borderRadius": "8px", "border": "1px solid #e0e0e0"}, 
                {"display": "block", "textAlign": "center", "marginTop": "20px", "marginBottom": "20px"},
                {"display": "block", "marginBottom": "20px"},
                "")
    except ValueError as ve:
        error_msg = f"Security Error: {str(ve)}"
        return [], {"display": "none"}, [], {"display": "none"}, [], {"display": "none"}, {"display": "none"}, {"display": "none"}, error_msg
    except Exception as e:
        error_msg = f"Error fetching columns: {str(e)}"
        return [], {"display": "none"}, [], {"display": "none"}, [], {"display": "none"}, {"display": "none"}, {"display": "none"}, error_msg

# Select/Deselect All buttons for core table
@callback(
    Output('stats-join-core-table-options', 'value', allow_duplicate=True),
    [Input('stats-join-select-all-btn', 'n_clicks'), 
     Input('stats-join-deselect-all-btn', 'n_clicks')],
    [State('stats-join-core-table-options', 'options')],
    prevent_initial_call=True
)
def handle_core_select_buttons(select_all_clicks, deselect_all_clicks, current_options):
    trigger_id = ctx.triggered_id if ctx.triggered_id else None

    if trigger_id == 'stats-join-select-all-btn' and current_options:
        return [opt['value'] for opt in current_options]
    if trigger_id == 'stats-join-deselect-all-btn':
        return []
    
    raise PreventUpdate

# Select/Deselect All buttons for tree table
@callback(
    Output('stats-join-tree-table-options', 'value', allow_duplicate=True),
    [Input('stats-join-select-all-btn-2', 'n_clicks'), 
     Input('stats-join-deselect-all-btn-2', 'n_clicks')],
    [State('stats-join-tree-table-options', 'options')],
    prevent_initial_call=True
)
def handle_tree_select_buttons(select_all_clicks, deselect_all_clicks, current_options):
    trigger_id = ctx.triggered_id if ctx.triggered_id else None

    if trigger_id == 'stats-join-select-all-btn-2' and current_options:
        return [opt['value'] for opt in current_options]
    if trigger_id == 'stats-join-deselect-all-btn-2':
        return []
    
    raise PreventUpdate

# Select/Deselect All buttons for garden table
@callback(
    Output('stats-join-garden-table-options', 'value', allow_duplicate=True),
    [Input('stats-join-select-all-btn-3', 'n_clicks'), 
     Input('stats-join-deselect-all-btn-3', 'n_clicks')],
    [State('stats-join-garden-table-options', 'options')],
    prevent_initial_call=True
)
def handle_garden_select_buttons(select_all_clicks, deselect_all_clicks, current_options):
    trigger_id = ctx.triggered_id if ctx.triggered_id else None

    if trigger_id == 'stats-join-select-all-btn-3' and current_options:
        return [opt['value'] for opt in current_options]
    if trigger_id == 'stats-join-deselect-all-btn-3':
        return []
    
    raise PreventUpdate

# Update join preview content
@callback(
    Output("stats-join-preview", "children"),
    [Input("stats-join-core-dropdown", "value"),
     Input("stats-join-core-table-options", "value"),
     Input("stats-join-tree-table-options", "value"),
     Input("stats-join-garden-table-options", "value")],
    prevent_initial_call=True
)
def update_join_preview(core_table, core_vars, tree_vars, garden_vars):
    if not core_table:
        return ""
    
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
            html.Span("Please select at least one data source", style={"color": "#ffc107", "fontStyle": "italic"})
        ]))
    
    return preview_parts

# Execute join and keep config visible while showing analysis options
@callback(
    [Output('stats-join-query-store', 'data'),
     Output('stats-table-dropdown', 'value', allow_duplicate=True),
     Output('test-selection-div', 'style', allow_duplicate=True),
     Output('stats-join-general-error', 'children', allow_duplicate=True),
     Output('stats-join-execute-error', 'style')],
    [Input('stats-join-execute-button', 'n_clicks')],
    [State('stats-join-core-dropdown', 'value'),
     State('stats-join-core-table-options', 'value'),
     State('stats-join-tree-table-options', 'value'),
     State('stats-join-garden-table-options', 'value')],
    prevent_initial_call=True
)
def execute_stats_join(n_clicks, core_table, core_vars, tree_vars, garden_vars):
    if not n_clicks or not core_table or (not tree_vars and not garden_vars):
        # Show error if attempting to execute without data sources
        if n_clicks and (not tree_vars and not garden_vars):
            return dash.no_update, dash.no_update, dash.no_update, "", {"display": "block", "textAlign": "center", "marginTop": "20px", "padding": "15px", "backgroundColor": "#fff3cd", "borderRadius": "8px", "border": "1px solid #ffc107"}
        raise PreventUpdate
    
    try:
        # Generate SQL query
        base_query = generate_join_query(core_table, core_vars, tree_vars, garden_vars)
        
        # Execute query to get total row count
        count_query = f"SELECT COUNT(*) AS total_rows FROM ({base_query}) AS count_subquery"
        count_result = fetch_data_from_sql(count_query)
        
        if count_result is None or count_result.empty:
            return None, dash.no_update, dash.no_update, "Error: Could not determine row count", {"display": "none"}
        
        total_rows = int(count_result.iloc[0]['total_rows'])
        
        # Prepare query store data
        query_data = {
            'base_query': base_query,
            'total_rows': total_rows
        }
        
        # Change dropdown to "__custom_join__" and show test selection
        return (query_data, "__custom_join__", 
                {"display": "block"}, "", {"display": "none"})
        
    except Exception as e:
        error_msg = f"Error executing join: {str(e)}"
        print(error_msg)
        return None, dash.no_update, dash.no_update, error_msg, {"display": "none"}

# Show error when execute button clicked without data sources
@callback(
    Output('stats-join-execute-error', 'style', allow_duplicate=True),
    [Input('stats-join-execute-button', 'n_clicks')],
    [State('stats-join-tree-table-options', 'value'),
     State('stats-join-garden-table-options', 'value')],
    prevent_initial_call=True
)
def show_join_error(n_clicks, tree_vars, garden_vars):
    if not n_clicks:
        raise PreventUpdate
    
    if not tree_vars and not garden_vars:
        return {"display": "block", "textAlign": "center", "marginTop": "20px",
                "padding": "15px", "backgroundColor": "#fff3cd", 
                "borderRadius": "8px", "border": "1px solid #ffc107"}
    
    return {"display": "none"}


# ===== ANALYSIS CALLBACKS (handle both regular tables and __custom_join__) =====

def fetch_data_for_analysis(selected_table, columns, row_count, join_query_data):
    """Helper to fetch data for analysis - handles both regular tables and custom joins"""
    try:
        if selected_table == "__custom_join__":
            if not join_query_data:
                return None
            base_query = join_query_data.get('base_query')
            cols_sql = ", ".join([f"[{c}]" for c in columns])
            query = f"SELECT TOP {row_count} {cols_sql} FROM ({base_query}) AS subquery WHERE " + " AND ".join([f"[{c}] IS NOT NULL" for c in columns])
        else:
            validate_table_name_stats(selected_table)
            cols_sql = ", ".join([f"[{c}]" for c in columns])
            where_clause = " AND ".join([f"[{c}] IS NOT NULL" for c in columns])
            query = f"SELECT TOP {row_count} {cols_sql} FROM [dbo].[{selected_table}] WHERE {where_clause}"
        
        return fetch_data_from_sql(query)
    except Exception as e:
        print(f"Error fetching data for analysis: {e}")
        return None

# Linear Regression Callback
@callback(
    [Output("lr-output-content", "children", allow_duplicate=True),
     Output("run-lr-button", "disabled", allow_duplicate=True),
     Output("run-lr-button", "children", allow_duplicate=True),
     Output("lr-full-button-container", "style"),
     Output("run-lr-full", "children")],
    [Input("run-lr-button", "n_clicks"),
     Input("run-lr-full", "n_clicks")],
    [State("stats-table-dropdown", "value"),
     State("lr-x-variable", "value"),
     State("lr-y-variable", "value"),
     State("stats-metadata-store", "data"),
     State("stats-join-query-store", "data")],
    prevent_initial_call=True
)
def generate_linear_regression(n_clicks_sample, n_clicks_full, selected_table, x_var, y_var, metadata_store, join_query_data):
    trigger_id = ctx.triggered_id if ctx.triggered_id else None
    
    if not trigger_id or not selected_table or not x_var or not y_var:
        raise PreventUpdate
    
    try:
        # Handle custom join case
        actual_table = "__custom_join__" if selected_table == "__custom_join__" else selected_table
        
        # Get metadata
        metadata = metadata_store.get(actual_table, {})
        total_rows = metadata.get('row_count', DEFAULT_SAMPLE_SIZE)
        
        # Determine if full dataset requested
        use_full_dataset = (trigger_id == "run-lr-full")
        
        if use_full_dataset:
            sample_size = total_rows
        else:
            sample_size = calculate_sample_size(total_rows)
        
        # Fetch the data
        df = fetch_data_for_analysis(actual_table, [x_var, y_var], sample_size, join_query_data)
        
        # Check if we have enough data
        if df is None or df.empty or len(df) < MIN_ROWS_FOR_REGRESSION:
            return (html.Div([
                html.H5("Insufficient Data", style={"color": "red"}),
                html.P("Not enough valid data points for regression analysis.")
            ], style={"color": "red", "fontWeight": "bold"}), 
            False, "Generate Regression", {"display": "none"}, "🔄 Analyze Full Dataset")
            
        # Calculate regression
        x = df[x_var].values
        y = df[y_var].values
        
        slope, intercept, r_value, p_value, std_err = scipy_stats.linregress(x, y)
        
        # Generate prediction line
        x_range = np.linspace(min(x), max(x), 100)
        y_pred = slope * x_range + intercept
        
        # Create the plot
        fig = go.Figure()
        
        # Add scatter plot of data
        fig.add_trace(go.Scatter(
            x=x, 
            y=y, 
            mode='markers',
            name='Data Points',
            marker=dict(
                color='blue',
                opacity=0.6,
                size=8
            )
        ))
        
        # Add regression line
        fig.add_trace(go.Scatter(
            x=x_range,
            y=y_pred,
            mode='lines',
            name='Regression Line',
            line=dict(color='red', width=2)
        ))
        
        # Update layout
        r_squared = r_value**2
        equation = f"y = {slope:.4f}x + {intercept:.4f}"
        
        fig.update_layout(
            title=f"Linear Regression: {y_var} vs {x_var}",
            xaxis_title=x_var,
            yaxis_title=y_var,
            height=500,
            paper_bgcolor="#e5ecf6",
            plot_bgcolor="#f9f9f9",
            annotations=[
                dict(
                    x=0.02,
                    y=0.98,
                    xref="paper",
                    yref="paper",
                    text=f"Equation: {equation}<br>R² = {r_squared:.4f}<br>p-value = {p_value:.4f}",
                    showarrow=False,
                    bgcolor="rgba(255, 255, 255, 0.8)",
                    bordercolor="rgba(0, 0, 0, 0.2)",
                    borderwidth=1,
                    borderpad=10,
                    font=dict(size=12)
                )
            ]
        )
        
        # Add statistics summary
        stats_table = html.Div([
            html.H5("Regression Statistics", style={"marginTop": "20px"}),
            html.Table([
                html.Thead(
                    html.Tr([
                        html.Th("Metric", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                        html.Th("Value", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"})
                    ])
                ),
                html.Tbody([
                    html.Tr([
                        html.Td("Slope", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                        html.Td(f"{slope:.6f}", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"})
                    ]),
                    html.Tr([
                        html.Td("Intercept", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                        html.Td(f"{intercept:.6f}", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"})
                    ]),
                    html.Tr([
                        html.Td("R-squared", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                        html.Td(f"{r_squared:.6f}", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"})
                    ]),
                    html.Tr([
                        html.Td("p-value", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                        html.Td(f"{p_value:.6f}", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"})
                    ]),
                    html.Tr([
                        html.Td("Standard Error", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                        html.Td(f"{std_err:.6f}", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"})
                    ]),
                    html.Tr([
                        html.Td("Sample Size", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                        html.Td(f"{len(df)}", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"})
                    ]),
                ])
            ], style={"borderCollapse": "collapse", "width": "100%", "marginBottom": "20px"})
        ])
        
        # Sample size info
        sample_info = html.Div(
            format_sample_info(len(df), total_rows),
            style={"color": "#28a745", "fontWeight": "bold", "marginTop": "15px", "fontSize": "14px"}
        )
        
        result = html.Div([
            dcc.Graph(figure=fig),
            stats_table,
            sample_info
        ], style={"padding": "20px", "backgroundColor": "#ffffff", "borderRadius": "8px", "border": "1px solid #e0e0e0"})
        
        # Show button only if sample was used
        show_button = (len(df) < total_rows and not use_full_dataset)
        button_style = {"display": "block", "marginTop": "15px", "textAlign": "center"} if show_button else {"display": "none"}
        button_text = f"🔄 Analyze Full Dataset ({total_rows:,} rows)"
        
        return result, False, "Generate Regression", button_style, button_text
    
    except Exception as e:
        error_msg = html.Div([
            html.H5("Error", style={"color": "red"}),
            html.P(f"An error occurred: {str(e)}")
        ], style={"color": "red", "fontWeight": "bold"})
        print(f"Linear regression error: {e}")
        return error_msg, False, "Generate Regression", {"display": "none"}, "🔄 Analyze Full Dataset"

# PCA Callback
@callback(
    [Output("pca-output-content", "children", allow_duplicate=True),
     Output("run-pca-button", "children", allow_duplicate=True),
     Output("pca-full-button-container", "style"),
     Output("run-pca-full", "children"),
     Output("pca-warning", "children")],
    [Input("run-pca-button", "n_clicks"),
     Input("run-pca-full", "n_clicks")],
    [State("stats-table-dropdown", "value"),
     State("pca-variables", "value"),
     State("pca-dimensions", "value"),
     State("stats-metadata-store", "data"),
     State("stats-join-query-store", "data")], 
    prevent_initial_call=True
)
def generate_pca(n_clicks_sample, n_clicks_full, selected_table, variables, dimensions, metadata_store, join_query_data):
    trigger_id = ctx.triggered_id if ctx.triggered_id else None
    
    if not trigger_id or not selected_table:
        raise PreventUpdate
    
    # Check for minimum variables FIRST and show warning
    if not variables or len(variables) < MIN_VARS_FOR_PCA:
        warning_msg = html.Div([
            html.Span("⚠️ ", style={"fontSize": "18px"}),
            html.Span(f"Please select at least {MIN_VARS_FOR_PCA} variables to perform PCA analysis.", 
                     style={"fontWeight": "bold"})
        ], style={
            "color": "#856404",
            "backgroundColor": "#fff3cd",
            "border": "1px solid #ffeaa7",
            "borderRadius": "4px",
            "padding": "12px",
            "marginTop": "10px"
        })
        return html.Div(), "Generate PCA", {"display": "none"}, "🔄 Analyze Full Dataset", warning_msg
    
    try:
        # Handle custom join case
        actual_table = "__custom_join__" if selected_table == "__custom_join__" else selected_table
        
        # Get metadata
        metadata = metadata_store.get(actual_table, {})
        total_rows = metadata.get('row_count', DEFAULT_SAMPLE_SIZE)
        
        # Determine if full dataset requested
        use_full_dataset = (trigger_id == "run-pca-full")
        
        if use_full_dataset:
            sample_size = total_rows
        else:
            sample_size = calculate_sample_size(total_rows)
        
        # Fetch the data
        df = fetch_data_for_analysis(actual_table, variables, sample_size, join_query_data)
        
        # Drop rows with NaN values
        if df is not None:
            df = df.dropna()
        
        # Check if we have enough data
        if df is None or len(df) < MIN_ROWS_FOR_PCA:
            error_msg = html.Div([
                html.H5("Insufficient Data", style={"color": "red"}),
                html.P("Not enough valid data points for PCA analysis.")
            ], style={"color": "red", "fontWeight": "bold"})
            return error_msg, "Generate PCA", {"display": "none"}, "🔄 Analyze Full Dataset", html.Div()
        
        # Scale the data
        scaler = StandardScaler()
        scaled_data = scaler.fit_transform(df)
        
        # Determine number of components
        n_components = min(3, len(variables))
        
        # Perform PCA
        pca = PCA(n_components=n_components)
        pca_result = pca.fit_transform(scaled_data)
        
        # Create a DataFrame with PCA results
        pca_df = pd.DataFrame(
            data=pca_result,
            columns=[f'PC{i+1}' for i in range(n_components)]
        )
        
        # Calculate explained variance
        explained_variance = pca.explained_variance_ratio_ * 100
        
        # Create the plot
        if dimensions == '3d' and n_components >= 3:
            fig = px.scatter_3d(
                pca_df, 
                x='PC1', 
                y='PC2', 
                z='PC3',
                title="3D PCA Visualization",
                labels={
                    'PC1': f'PC1 ({explained_variance[0]:.2f}%)',
                    'PC2': f'PC2 ({explained_variance[1]:.2f}%)',
                    'PC3': f'PC3 ({explained_variance[2]:.2f}%)'
                },
                opacity=0.7
            )
        else:
            fig = px.scatter(
                pca_df, 
                x='PC1', 
                y='PC2',
                title="2D PCA Visualization",
                labels={
                    'PC1': f'PC1 ({explained_variance[0]:.2f}%)',
                    'PC2': f'PC2 ({explained_variance[1]:.2f}%)'
                },
                opacity=0.7
            )
        
        fig.update_layout(
            height=600,
            paper_bgcolor="#e5ecf6",
            plot_bgcolor="#f9f9f9"
        )
        
        # Create loading plot and variance table
        loadings = pca.components_
        loading_df = pd.DataFrame(loadings.T, columns=[f'PC{i+1}' for i in range(n_components)], index=variables)
        
        # Create variance explanation table
        variance_table = html.Div([
            html.H5("Explained Variance", style={"marginTop": "20px"}),
            html.Table([
                html.Thead(
                    html.Tr([
                        html.Th("Component", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                        html.Th("Variance Explained (%)", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                        html.Th("Cumulative Variance (%)", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"})
                    ])
                ),
                html.Tbody([
                    html.Tr([
                        html.Td(f"PC{i+1}", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                        html.Td(f"{explained_variance[i]:.2f}%", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                        html.Td(f"{np.sum(explained_variance[:i+1]):.2f}%", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"})
                    ]) for i in range(n_components)
                ])
            ], style={"borderCollapse": "collapse", "width": "100%", "marginBottom": "20px"})
        ])
        
        # Create loadings table
        loadings_table = html.Div([
            html.H5("Variable Loadings", style={"marginTop": "20px"}),
            html.Table([
                html.Thead(
                    html.Tr([
                        html.Th("Variable", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                    ] + [
                        html.Th(f"PC{i+1}", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"})
                        for i in range(n_components)
                    ])
                ),
                html.Tbody([
                    html.Tr([
                        html.Td(var, style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                    ] + [
                        html.Td(f"{loading_df.loc[var, f'PC{i+1}']:.4f}", 
                                style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"})
                        for i in range(n_components)
                    ]) for var in variables
                ])
            ], style={"borderCollapse": "collapse", "width": "100%", "marginBottom": "20px"})
        ])
        
        # Sample size info
        sample_info = html.Div(
            format_sample_info(len(df), total_rows),
            style={"color": "#28a745", "fontWeight": "bold", "marginTop": "15px", "fontSize": "14px"}
        )
        
        result = html.Div([
            dcc.Graph(figure=fig),
            variance_table,
            loadings_table,
            sample_info
        ], style={"padding": "20px", "backgroundColor": "#ffffff", "borderRadius": "8px", "border": "1px solid #e0e0e0"})
        
        # Show button only if sample was used
        show_button = (len(df) < total_rows and not use_full_dataset)
        button_style = {"display": "block", "marginTop": "15px", "textAlign": "center"} if show_button else {"display": "none"}
        button_text = f"🔄 Analyze Full Dataset ({total_rows:,} rows)"
        
        # Clear warning on success
        return result, "Generate PCA", button_style, button_text, html.Div()
    
    except Exception as e:
        error_msg = html.Div([
            html.H5("Error", style={"color": "red"}),
            html.P(f"An error occurred: {str(e)}")
        ], style={"color": "red", "fontWeight": "bold"})
        print(f"PCA error: {e}")
        return error_msg, "Generate PCA", {"display": "none"}, "🔄 Analyze Full Dataset", html.Div()

# Summary Statistics Callback
@callback(
    [Output("summary-output-content", "children", allow_duplicate=True),
     Output("run-summary-button", "children", allow_duplicate=True),
     Output("summary-full-button-container", "style"),
     Output("run-summary-full", "children")],
    [Input("run-summary-button", "n_clicks"),
     Input("run-summary-full", "n_clicks")],
    [State("stats-table-dropdown", "value"),
     State("summary-variable", "value"),
     State("stats-metadata-store", "data"),
     State("stats-join-query-store", "data")],
    prevent_initial_call=True
)
def generate_summary_statistics(n_clicks_sample, n_clicks_full, selected_table, variable, metadata_store, join_query_data):
    trigger_id = ctx.triggered_id if ctx.triggered_id else None
    
    if not trigger_id or not selected_table or not variable:
        raise PreventUpdate
    
    try:
        # Handle custom join case
        actual_table = "__custom_join__" if selected_table == "__custom_join__" else selected_table
        
        # Get metadata
        metadata = metadata_store.get(actual_table, {})
        total_rows = metadata.get('row_count', DEFAULT_SAMPLE_SIZE)
        
        # Determine if full dataset requested
        use_full_dataset = (trigger_id == "run-summary-full")
        
        if use_full_dataset:
            sample_size = total_rows
        else:
            sample_size = calculate_sample_size(total_rows)
        
        # Fetch the data
        df = fetch_data_for_analysis(actual_table, [variable], sample_size, join_query_data)
            
        # Check if we have enough data
        if df is None or len(df) < 1:
            return (html.Div([
                html.H5("Insufficient Data", style={"color": "red"}),
                html.P("No valid data points for summary statistics.")
            ], style={"color": "red", "fontWeight": "bold"}), 
            "Generate Summary", {"display": "none"}, "🔄 Analyze Full Dataset")
        
        # Calculate statistics
        data = df[variable]
        summary = {
            'Count': len(data),
            'Mean': data.mean(),
            'Median': data.median(),
            'Standard Deviation': data.std(),
            'Minimum': data.min(),
            'Maximum': data.max(),
            '25th Percentile': data.quantile(0.25),
            '75th Percentile': data.quantile(0.75),
            'IQR': data.quantile(0.75) - data.quantile(0.25),
            'Skewness': data.skew(),
            'Kurtosis': data.kurtosis()
        }
        
        # Create box plot
        fig_box = go.Figure()
        fig_box.add_trace(go.Box(
            y=data,
            name=variable,
            boxpoints='all',
            jitter=0.3,
            pointpos=-1.8,
            marker=dict(
                color='blue',
                opacity=0.6,
                size=4
            ),
            line=dict(color='darkblue')
        ))
        
        fig_box.update_layout(
            title=f"Box Plot for {variable}",
            yaxis_title=variable,
            height=400,
            paper_bgcolor="#e5ecf6",
            plot_bgcolor="#f9f9f9",
            margin=dict(l=40, r=40, t=40, b=40)
        )
        
        # Create histogram
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(
            x=data,
            histnorm='probability density',
            name=variable,
            marker=dict(color='darkblue')
        ))
        
        # Add mean and median lines
        fig_hist.add_vline(x=summary['Mean'], line_dash="solid", line_color="red", 
                        annotation_text="Mean", annotation_position="top right")
        fig_hist.add_vline(x=summary['Median'], line_dash="dash", line_color="green", 
                        annotation_text="Median", annotation_position="top left")
        
        fig_hist.update_layout(
            title=f"Distribution of {variable}",
            xaxis_title=variable,
            yaxis_title="Density",
            height=400,
            paper_bgcolor="#e5ecf6",
            plot_bgcolor="#f9f9f9",
            margin=dict(l=40, r=40, t=40, b=40)
        )
        
        # Create summary statistics table
        stats_table = html.Div([
            html.H5("Summary Statistics", style={"marginTop": "20px"}),
            html.Table([
                html.Thead(
                    html.Tr([
                        html.Th("Statistic", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                        html.Th("Value", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"})
                    ])
                ),
                html.Tbody([
                    html.Tr([
                        html.Td(stat, style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                        html.Td(f"{value:.6f}" if isinstance(value, float) else f"{value}", 
                                style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"})
                    ]) for stat, value in summary.items()
                ])
            ], style={"borderCollapse": "collapse", "width": "100%", "marginBottom": "20px"})
        ])
        
        # Sample size info
        sample_info = html.Div(
            format_sample_info(len(data), total_rows),
            style={"color": "#28a745", "fontWeight": "bold", "marginTop": "15px", "fontSize": "14px"}
        )
        
        result = html.Div([
            dcc.Graph(figure=fig_box, style={"marginBottom": "20px"}),
            dcc.Graph(figure=fig_hist, style={"marginBottom": "20px"}),
            stats_table,
            sample_info
        ], style={"padding": "20px", "backgroundColor": "#ffffff", "borderRadius": "8px", "border": "1px solid #e0e0e0"})
        
        # Show button only if sample was used
        show_button = (len(data) < total_rows and not use_full_dataset)
        button_style = {"display": "block", "marginTop": "15px", "textAlign": "center"} if show_button else {"display": "none"}
        button_text = f"🔄 Analyze Full Dataset ({total_rows:,} rows)"
        
        return result, "Generate Summary", button_style, button_text
        
    except Exception as e:
        error_msg = html.Div([
            html.H5("Error", style={"color": "red"}),
            html.P(f"An error occurred: {str(e)}")
        ], style={"color": "red", "fontWeight": "bold"})
        print(f"Summary statistics error: {e}")
        return error_msg, "Generate Summary", {"display": "none"}, "🔄 Analyze Full Dataset"
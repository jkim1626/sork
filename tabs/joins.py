import logging

from dash import dcc, html, Input, Output, State, callback, ctx, clientside_callback
from dash.exceptions import PreventUpdate
import dash
from dotenv import load_dotenv
from database import fetch_data_from_sql, fetch_data_from_sql_public
from flask import session as flask_session
import pandas as pd
from pandas.api.types import is_numeric_dtype
from dash_ag_grid import AgGrid

import plotly.graph_objects as go
import plotly.express as px
from scipy import stats
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
import numpy as np

# Statistical test options
MIN_ROWS_FOR_REGRESSION = 3
MIN_ROWS_FOR_PCA = 3
MIN_VARS_FOR_PCA = 2

stat_test_options = [
    {'label': 'Linear Regression', 'value': 'linear_regression'},
    {'label': 'Principal Component Analysis (PCA)', 'value': 'pca'},
    {'label': 'Summary Statistics', 'value': 'summary_stats'},
    {'label': 'Plot Data (No Test)', 'value': 'plot_data'}
]

# Load environment variables
load_dotenv(override=True)
logger = logging.getLogger(__name__)


def _fetch_for_user(query, raise_on_error=False):
    """Route DB query through the correct credential tier.

    Authenticated users use the standard read role; guests use qplad_public.
    """
    if 'user' in flask_session:
        return fetch_data_from_sql(query, raise_on_error=raise_on_error)
    return fetch_data_from_sql_public(query, raise_on_error=raise_on_error)


# ===== CONFIGURATION CONSTANTS =====

# Type detection
TYPE_DETECTION_SAMPLE_SIZE = 200
NUMERIC_THRESHOLD = 0.5

# Table definitions
CORE_TABLES = {
    "db_main": "Growth/Survival",
    "budburst_detailed_all": "All Budburst Stages",
    "biomass_destructive_2021": "Biomass",
    "leaf_traits_2016": "Leaf traits",
}

MATERNAL_TREE_TABLE = "Valley oak maternal tree climate data BCM 2018_03_08"
GARDENS_TABLE = "gardens_20152023prismmonthly"
CORE_JOIN_KEYS_BY_TABLE = {
    "leaf_traits_2016": ["Accession", "Locality", "Site"],
}
DEFAULT_CORE_JOIN_KEYS = ["Accession", "Locality", "Year", "Site"]
TREE_JOIN_KEYS = {"Accession", "Locality"}
GARDEN_JOIN_KEYS = {"Site", "Year"}

# Whitelists for validation
ALLOWED_CORE_TABLES = set(CORE_TABLES.keys())


def _required_core_cols(core_table):
    return CORE_JOIN_KEYS_BY_TABLE.get(core_table, DEFAULT_CORE_JOIN_KEYS)


def _hide_join_key_options(columns, hidden_keys):
    hidden = set(hidden_keys or [])
    return [{'label': c, 'value': c} for c in columns if c not in hidden]


def _garden_join_validation_message(core_table, core_columns=None, garden_columns=None):
    if core_columns is None:
        return "Garden Climate requires Site + Year, but the selected dataset columns could not be verified right now."
    core_cols = set(core_columns or [])
    missing_core = [col for col in ("Site", "Year") if col not in core_cols]
    if missing_core:
        return f"Garden Climate joins by Site + Year, but {CORE_TABLES.get(core_table, core_table)} does not expose: {', '.join(missing_core)}."
    if garden_columns is not None:
        garden_cols = set(garden_columns or [])
        missing_garden = [col for col in ("Site", "Year") if col not in garden_cols]
        if missing_garden:
            return f"Garden Climate joins by Site + Year, but the Garden Climate table does not expose: {', '.join(missing_garden)}."
    return None

# Create a layout for the joins tab
joins_layout = dcc.Tab(
    label="Select and Filter",
    id="joins-tab",
    style={"padding": "15px", "display": "flex", "flexDirection": "column", "flex": "1 1 auto", "minHeight": 0},
    children=[
        dcc.Store(id='joins-tab-active', data=False),
        dcc.Store(id='join-tab-full-query', data=None),  # Store the SQL query instead of data
        dcc.Store(id='joins-metadata-store', data={}),  # Cache metadata (column lists)
        dcc.Store(id='join-available-years', data=[]),  # Store available years for filtering
        html.Div(className="d-flex w-100", id="join-split-container", style={"display": "flex", "flex": "1 1 auto", "flexDirection": "row", "alignItems": "stretch", "maxWidth": "98%", "margin": "0 auto", "padding": "0 20px"}, children=[
            # LEFT COLUMN: Selection (Draggable)
            html.Div(id="join-left-pane", style={"flex": "0 0 auto", "width": "30%", "minWidth": "20%", "maxWidth": "85%", "overflowX": "hidden", "overflowY": "auto", "paddingRight": "20px", "height": "100%"}, children=[

                # Introduction section
                html.Div([
                    html.H4("Select & Filter Data", style={"marginBottom": "10px", "color": "#133817"}),
                    html.P(
                        "Choose one dataset or combine datasets only when needed. Required identifiers and join keys are included automatically, so they are not shown in the variable checklists.",
                        style={"color": "#666", "marginBottom": "20px", "fontSize": "0.95em"}
                    ),
                    html.Div(
                        "Garden Climate is opt-in and requires both Site and Year. Larger joins and exports may take a while, so the preview is limited by default.",
                        style={"backgroundColor": "#fff3cd", "border": "1px solid #ffe69c", "padding": "10px 12px", "borderRadius": "6px", "fontSize": "0.9em"},
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

                # Error message for general errors
                html.Div(id="join-tab-general-error", style={"color": "red", "marginTop": "10px", "fontWeight": "bold", "textAlign": "center"}),

                # Step 2: Pre-join filters (Year filter)
                html.Div([
                    html.H5("Step 2: Pre-Join Filters (Optional)", style={"fontWeight": "bold", "marginBottom": "10px", "color": "#133817"}),
                    html.P("Filter data before joining to reduce dataset size. Leave empty to include all.",
                           style={"color": "#666", "marginBottom": "8px", "fontSize": "0.9em"}),
                    html.Div([
                        html.Label("Filter by Year(s):", style={"fontWeight": "bold", "marginBottom": "5px", "fontSize": "0.9em"}),
                        dcc.Dropdown(
                            id="join-year-filter",
                            options=[],
                            value=[],
                            multi=True,
                            placeholder="All years (no filter)",
                            style={"marginBottom": "10px"}
                        ),
                    ]),
                    html.Div([
                        html.Label("Filter by Site(s):", style={"fontWeight": "bold", "marginBottom": "5px", "fontSize": "0.9em"}),
                        dcc.Dropdown(
                            id="join-site-filter",
                            options=[],
                            value=[],
                            multi=True,
                            placeholder="All sites (no filter)",
                        ),
                    ]),
                ], id="join-prefilter-container", style={"display": "none", "marginBottom": "25px", "padding": "15px", "backgroundColor": "#ffffff", "borderRadius": "8px", "border": "1px solid #e0e0e0"}),

                # Step 3: Core table columns (in a card)
                html.Div([
                    html.Div([
                        html.H5("Step 3: Garden Dataset Columns", style={"fontWeight": "bold", "marginBottom": "5px", "color": "#133817"}),
                        html.P("No columns selected by default. Join keys such as Accession, Locality, Site, and Year are included automatically when needed.", 
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
                                style={"padding": "10px", 
                                      "backgroundColor": "#f9f9f9", "borderRadius": "5px"}),
                ], id="join-table-columns-container", style={"display": "none", "marginBottom": "20px", 
                                                              "padding": "15px", "backgroundColor": "#ffffff", 
                                                              "borderRadius": "8px", "border": "1px solid #e0e0e0"}),

                # Step 4: Maternal tree table columns (in a card)
                html.Div([
                    html.Div([
                        html.H5("Step 4: Maternal Tree Climate Data", style={"fontWeight": "bold", "marginBottom": "5px", "color": "#133817"}),
                        html.P("Climate data from original tree locations. Optional: select these variables to join by Accession and Locality. You can also leave this section empty.", 
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
                                style={"padding": "10px", 
                                      "backgroundColor": "#f9f9f9", "borderRadius": "5px"}),
                ], id="join-tree-table-columns-container", style={"display": "none", "marginBottom": "20px",
                                                                    "padding": "15px", "backgroundColor": "#ffffff", 
                                                                    "borderRadius": "8px", "border": "1px solid #e0e0e0"}),

                # Step 5: Garden climate variables (in a card)
                html.Div([
                    html.Div([
                        html.H5("Step 5: Garden Climate Data", style={"fontWeight": "bold", "marginBottom": "5px", "color": "#133817"}),
                        html.P("Monthly climate data from garden sites. Optional and matched strictly by Site + Year; datasets without both keys are blocked before running.", 
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
                                style={"padding": "10px", 
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
                        n_clicks=0,
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
            ]), # END LEFT COLUMN

            # FULL HEIGHT DRAGGABLE DIVIDER
            html.Div(id="join-drag-divider", style={
                "width": "6px", 
                "height": "100%",
                "cursor": "col-resize", 
                "backgroundColor": "#f4f4f4", 
                "borderLeft": "1px solid #ddd",
                "borderRight": "1px solid #ddd",
                "zIndex": 10,
                "transition": "background-color 0.2s",
                "flexShrink": 0
            }),
            
            # RIGHT COLUMN: Results & Analysis
            html.Div(id="join-right-pane", style={"flex": "1 1 auto", "overflowY": "auto", "paddingLeft": "20px", "minWidth": "100px", "height": "100%"}, children=[

                # Placeholder shown when no data is loaded
                html.Div([
                    html.Div("Select your data and click Join to see results here.", 
                             style={"color": "#999", "fontSize": "1.1em", "textAlign": "center", "marginTop": "40px"}),
                ], id="join-right-placeholder", style={"display": "block", "height": "100%"}),

                # Row limit toggle and input
                html.Div([
                    html.Div([
                        dcc.Checklist(
                            id="join-limit-rows-toggle",
                            options=[{"label": " Limit rows displayed", "value": "limit"}],
                            value=["limit"],
                            inline=True,
                            style={"fontWeight": "bold", "display": "inline-block", "marginRight": "15px"}
                        ),
                        html.Span(id="join-max-rows-info", style={"color": "#666", "fontSize": "0.9em"}),
                    ], style={"display": "flex", "alignItems": "center", "marginBottom": "8px"}),
                    html.Div([
                        html.Label("Max rows:", style={"marginRight": "8px"}),
                        dcc.Input(id="join-row-count", type="number", min=1, max=1000000, value=100,
                                style={"width": "100px"}, debounce=True),
                    ], id="join-row-count-input-wrapper", style={"display": "flex", "alignItems": "center"}),
                ], id="join-row-count-container", style={"display": "none", "marginBottom": "15px"}),
                
                # Error message div
                html.Div([
                    html.Div([
                        html.Strong("⚠️ Please select at least one data source", style={"color": "#dc3545"}),
                        html.P("Select at least one variable from the garden dataset, maternal tree climate, or garden climate sections to proceed.", 
                               style={"color": "#666", "marginTop": "5px", "marginBottom": "0", "fontSize": "0.9em"})
                    ])
                ], id="join-tab-execute-error", style={"display": "none", "textAlign": "center", "marginTop": "20px",
                                                       "padding": "15px", "backgroundColor": "#fff3cd", 
                                                       "borderRadius": "8px", "border": "1px solid #ffc107"}),
                
                # Join execution div - only shows after successful execution
                html.Div(id="join-tab-results-div", style={"display": "none", "padding": "20px", "backgroundColor": "#ffffff", 
                                                     "borderRadius": "8px", "border": "1px solid #e0e0e0"}, children=[
                    html.H4("Results", style={"marginBottom": "15px", "color": "#133817"}),
                    
                    # Filter and selection counts
                    html.Div([
                        html.Span(id='join-filter-count-text', style={"marginRight": "20px", "fontWeight": "bold"}),
                        html.Span(id='join-selected-count-text', style={"fontWeight": "bold", "marginRight": "12px"}),
                    ], style={"marginBottom": "8px"}),
                    
                    # Loading indicator - wraps placeholder that gets replaced with grid
                    dcc.Loading(
                        id="join-grid-loading",
                        type="default",
                        children=html.Div(id="join-grid-wrapper", style={"backgroundColor": "#e5ecf6", 
                                 "padding": "10px", "borderRadius": "5px", "border": "1px solid #d1d1d1", "marginBottom": "15px"})
                    ),
                    
                    # Stats and download section
                    html.Div([
                        html.Div(id="join-tab-results-stats", style={"marginTop": "15px", "color": "#666", "fontSize": "0.95em"}),
                        
                        # Download warning (for large datasets)
                        html.Div(id="join-download-warning", style={"marginTop": "10px"}),
                        
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
                ]),

                # -------------------------------------------------------------
                # Statistical Analysis Section (Appended to Joins Tab)
                # -------------------------------------------------------------
                html.Div([
                    html.H4("Optional Statistics & Figures", style={"marginBottom": "20px"}),
                    html.P(
                        "Run lightweight summaries and figures after you confirm the previewed dataset looks right. These analyses operate on filtered results and may be capped for performance.",
                        style={"color": "#666", "marginBottom": "15px"},
                    ),

                    # Test selection (only shows when there's data)
                    html.Div([
                        html.Label("1) Select analysis type", style={"fontWeight": "bold", "marginTop": "20px", "marginBottom": "5px", "fontSize": "16px"}),
                        dcc.Dropdown(stat_test_options, id="stats-test-dropdown", placeholder="Statistical Test Options"),
                    ], id="test-selection-div", style={"display": "block"}),
                    
                    # Containers for each test type
                    html.Div([
                        # Linear Regression
                        html.Div([
                            html.Label("2) Select variables for Linear Regression", style={"fontWeight": "bold", "marginTop": "20px", "marginBottom": "5px"}),
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
                            ])
                        ], id="linear-regression-div", style={"display": "none"}),
                        
                        # PCA
                        html.Div([
                            html.Label("2) Select variables for PCA", style={"fontWeight": "bold", "marginTop": "20px", "marginBottom": "5px"}),
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
                            ])
                        ], id="pca-div", style={"display": "none"}),
                        
                        # Plot Data (No Test)
                        html.Div([
                            html.Label("2) Select variables for Plot", style={"fontWeight": "bold", "marginTop": "20px", "marginBottom": "5px"}),
                            html.Div([
                                html.Label("X-axis:", style={"marginRight": "10px"}),
                                dcc.Dropdown(id="pd-x-variable", placeholder="Select x Variable"),
                            ], style={"marginBottom": "10px"}),
                            html.Div([
                                html.Label("Y-axis:", style={"marginRight": "10px"}),
                                dcc.Dropdown(id="pd-y-variable", placeholder="Select y Variable"),
                            ], style={"marginBottom": "10px"}),
                            html.Button("Generate Figure", id="run-pd-button", n_clicks=0,
                                       style={
                                           "backgroundColor": "#007bff",
                                           "color": "white",
                                           "border": "none",
                                           "borderRadius": "4px",
                                           "padding": "5px 15px",
                                           "marginTop": "10px"
                                       }),
                            
                            # Graph type selector (appears conditionally for CatxCat)
                            html.Div([
                                html.Div([
                                    html.Span("Switch view:", style={"fontWeight": "500", "marginRight": "15px", "color": "#333"}),
                                    dcc.RadioItems(
                                        id='cat-cat-graph-type',
                                        options=[
                                            {'label': ' 📊 Bar Chart', 'value': 'bar'},
                                            {'label': ' 🔥 Heatmap', 'value': 'heatmap'}
                                        ],
                                        value='bar',
                                        inline=True,
                                        labelStyle={"marginRight": "20px", "cursor": "pointer"},
                                        inputStyle={"marginRight": "5px"}
                                    ),
                                ], style={
                                    "display": "flex", 
                                    "alignItems": "center", 
                                    "justifyContent": "center",
                                    "padding": "12px 20px",
                                    "backgroundColor": "#f8f9fa",
                                    "borderRadius": "8px",
                                    "border": "1px solid #dee2e6",
                                    "marginTop": "15px"
                                }),
                            ], id="graph-type-selector", style={"display": "none"}),
                            
                            html.Div(id="pd-output", style={"marginTop": "20px"}, children=[
                                dcc.Loading(id="pd-loading", type="default", children=html.Div(id="pd-output-content"))
                            ])
                        ], id="plot-data-div", style={"display": "none"}),
                        
                        # Summary Statistics
                        html.Div([
                            html.Label("2) Select Variable for Summary Statistics", style={"fontWeight": "bold", "marginTop": "20px", "marginBottom": "5px"}),
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
                            ])
                        ], id="summary-stats-div", style={"display": "none"}),
                        
                    ], id="test-container", style={"display": "none"}),
                    
                ], id="stats-main-container", style={"display": "none", "padding": "20px", "backgroundColor": "#ffffff", "borderRadius": "8px", "border": "1px solid #e0e0e0", "marginTop": "20px"})

            ]) # END RIGHT COLUMN
        ]) # END ROW
    ]
) 



# ====== HELPERS ======

def validate_table_name(table_name, allowed_set):
    """Validate table name against whitelist."""
    if table_name not in allowed_set:
        raise ValueError(f"Invalid table name: {table_name}")
    return table_name

def apply_filter_model(df, filter_model):
    """Apply AG Grid filter model to a DataFrame"""
    for field, model in (filter_model or {}).items():
        if field not in df.columns:
            continue
        # Text filter
        if model.get('filterType') == 'text' or isinstance(df[field].dtype, object):
            fval = str(model.get('filter', ''))
            ftype = model.get('type', 'contains')
            if ftype == 'contains':
                df = df[df[field].astype(str).str.contains(fval, na=False, case=False)]
            elif ftype == 'equals':
                df = df[df[field].astype(str) == fval]
            elif ftype == 'notEqual':
                df = df[df[field].astype(str) != fval]
            elif ftype == 'startsWith':
                df = df[df[field].astype(str).str.startswith(fval, na=False)]
            elif ftype == 'endsWith':
                df = df[df[field].astype(str).str.endswith(fval, na=False)]
            else:
                # Default to contains
                df = df[df[field].astype(str).str.contains(fval, na=False, case=False)]
        else:
            # Numeric filter
            comp = model.get('type')
            val = model.get('filter')
            if val is None:
                continue
            val = float(val)
            if comp == 'lessThan':
                df = df[pd.to_numeric(df[field], errors='coerce') < val]
            elif comp == 'lessThanOrEqual':
                df = df[pd.to_numeric(df[field], errors='coerce') <= val]
            elif comp == 'greaterThan':
                df = df[pd.to_numeric(df[field], errors='coerce') > val]
            elif comp == 'greaterThanOrEqual':
                df = df[pd.to_numeric(df[field], errors='coerce') >= val]
            elif comp == 'equals':
                df = df[pd.to_numeric(df[field], errors='coerce') == val]
            elif comp == 'notEqual':
                df = df[pd.to_numeric(df[field], errors='coerce') != val]
    return df

def get_column_lists_cached(metadata_store):
    """Get cached column lists or fetch if not cached."""
    cache_key = "all_columns"
    
    if cache_key in metadata_store:
        return metadata_store[cache_key]
    
    # Fetch all column lists
    try:
        # Gardens table
        gardens_df = _fetch_for_user(f"SELECT TOP 1 * FROM dbo.[{GARDENS_TABLE}]")
        gardens_cols = gardens_df.columns.tolist() if gardens_df is not None else []
        
        # Maternal tree table
        tree_df = _fetch_for_user(f"SELECT TOP 1 * FROM dbo.[{MATERNAL_TREE_TABLE}]")
        tree_cols = tree_df.columns.tolist() if tree_df is not None else []
        
        return {
            'gardens_columns': gardens_cols,
            'tree_columns': tree_cols
        }
    except Exception as e:
        print(f"Error fetching column lists: {e}")
        return {
            'gardens_columns': [],
            'tree_columns': []
        }



# ====== CALLBACKS ======

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
     Output('join-tab-results-stats', 'children', allow_duplicate=True),
     Output('join-tab-preview-container', 'style', allow_duplicate=True),
     Output('join-tab-preview', 'children', allow_duplicate=True),
     Output('join-tab-full-query', 'data', allow_duplicate=True),
     Output('join-grid-wrapper', 'children', allow_duplicate=True),
     Output('join-tab-csv-filename', 'value', allow_duplicate=True),
     Output('join-row-count', 'value', allow_duplicate=True),
     Output('join-row-count-container', 'style', allow_duplicate=True),
     Output('join-tab-general-error', 'children', allow_duplicate=True),
     Output('join-year-filter', 'options', allow_duplicate=True),
     Output('join-year-filter', 'value', allow_duplicate=True),
     Output('join-site-filter', 'options', allow_duplicate=True),
     Output('join-site-filter', 'value', allow_duplicate=True),
     Output('join-prefilter-container', 'style', allow_duplicate=True),
     Output('join-limit-rows-toggle', 'value', allow_duplicate=True),
     Output('stats-main-container', 'style', allow_duplicate=True),
     Output('stats-test-dropdown', 'value', allow_duplicate=True),
     Output('test-container', 'style', allow_duplicate=True),
     Output('lr-output-content', 'children', allow_duplicate=True),
     Output('pca-output-content', 'children', allow_duplicate=True),
     Output('summary-output-content', 'children', allow_duplicate=True),
     Output('pd-output-content', 'children', allow_duplicate=True),
     Output('join-right-placeholder', 'style', allow_duplicate=True)],
    [Input('joins-tab-active', 'data')],
    prevent_initial_call=True
)
def reset_tab_data(is_active):
    raise PreventUpdate

# Cache metadata when tab becomes active
@callback(
    Output('joins-metadata-store', 'data'),
    [Input('joins-tab-active', 'data')],
    [State('joins-metadata-store', 'data')],
    prevent_initial_call=True
)
def cache_metadata_on_tab_active(is_active, metadata_store):
    if not is_active or 'all_columns' in metadata_store:
        raise PreventUpdate
    
    # Fetch and cache column lists
    column_data = get_column_lists_cached(metadata_store)
    metadata_store['all_columns'] = column_data
    return metadata_store

# Reset core table columns when core table changes
@callback(
    [Output('join-core-table-options', 'value', allow_duplicate=True),
     Output('join-tree-table-options', 'value', allow_duplicate=True),
     Output('join-garden-table-options', 'value', allow_duplicate=True),
     Output('join-tab-results-div', 'style', allow_duplicate=True),
     Output('join-tab-execute-error', 'style', allow_duplicate=True),
     Output('join-tab-preview-container', 'style', allow_duplicate=True),
     Output('join-row-count-container', 'style', allow_duplicate=True),
     Output('join-tab-general-error', 'children', allow_duplicate=True),
     Output('join-year-filter', 'value', allow_duplicate=True),
     Output('join-site-filter', 'value', allow_duplicate=True),
     Output('join-right-placeholder', 'style', allow_duplicate=True)],
    [Input('join-tab-core-dropdown', 'value')],
    prevent_initial_call=True
)
def reset_columns_on_table_change(selected_table):
    # Reset all column selections and hide results when core table changes
    return [], [], [], {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}, "", [], [], {"display": "block", "height": "100%"}

# Handle conditionally rendered variable checklist - DEFAULT TO DE-SELECTED
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
     Output("join-tab-preview-container", "style"),
     Output("join-row-count-container", "style"),
     Output("join-tab-general-error", "children"),
     Output("join-year-filter", "options"),
     Output("join-site-filter", "options"),
     Output("join-prefilter-container", "style")],
    [Input("join-tab-core-dropdown", "value")],
    [State('joins-metadata-store', 'data')]
)
def update_core_table_columns(selected_table, metadata_store):
    if selected_table is None:
        return [], [], {"display": "none"}, [], [], {"display": "none"}, [], [], {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}, "", [], [], {"display": "none"}

    try:
        # Validate table name
        validate_table_name(selected_table, ALLOWED_CORE_TABLES)
        
        # Get cached column data
        column_data = metadata_store.get('all_columns', {})
        
        if not column_data:
            column_data = get_column_lists_cached(metadata_store)
        
        # Get columns from cache
        gardens_cols = column_data.get('gardens_columns', [])
        tree_cols = column_data.get('tree_columns', [])
        
        # Create user-facing options without required join keys. Keys are added
        # internally when a join is built so users do not have to select them.
        GARDENS_TABLE_OPTIONS = _hide_join_key_options(gardens_cols, GARDEN_JOIN_KEYS)
        MATERNAL_TREE_OPTIONS = _hide_join_key_options(tree_cols, TREE_JOIN_KEYS)

        # Fetch core table columns (not cached since it depends on selection)
        sample_df = _fetch_for_user(f"SELECT TOP 0 * FROM [dbo].[{selected_table}]")
        if sample_df is None or not len(sample_df.columns):
            error_msg = "Error: Could not fetch columns from selected table"
            return [], [], {"display": "none"}, [], [], {"display": "none"}, [], [], {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}, error_msg, [], [], {"display": "none"}
        
        cols = sample_df.columns.tolist()
        opts = _hide_join_key_options(cols, _required_core_cols(selected_table))
        
        # Fetch available years and sites for pre-join filtering
        year_options = []
        site_options = []
        show_prefilter = {"display": "none"}
        
        try:
            # Get distinct years if Year column exists
            if "Year" in cols:
                years_df = _fetch_for_user(f"SELECT DISTINCT [Year] FROM [dbo].[{selected_table}] WHERE [Year] IS NOT NULL ORDER BY [Year]")
                if years_df is not None and not years_df.empty:
                    year_values = sorted(years_df['Year'].dropna().unique())
                    year_options = [{"label": str(int(y)) if float(y) == int(y) else str(y), "value": y} for y in year_values]
            
            # Get distinct sites if Site column exists
            if "Site" in cols:
                sites_df = _fetch_for_user(f"SELECT DISTINCT [Site] FROM [dbo].[{selected_table}] WHERE [Site] IS NOT NULL ORDER BY [Site]")
                if sites_df is not None and not sites_df.empty:
                    site_values = sorted(sites_df['Site'].dropna().unique())
                    site_options = [{"label": str(s), "value": s} for s in site_values]
            
            if year_options or site_options:
                show_prefilter = {"display": "block", "marginBottom": "25px", "padding": "15px", "backgroundColor": "#ffffff", "borderRadius": "8px", "border": "1px solid #e0e0e0"}
        except Exception as e:
            print(f"Warning: Could not fetch filter options: {e}")
        
        card_style = {"display": "block", "marginBottom": "20px", 
                      "padding": "15px", "backgroundColor": "#ffffff", 
                      "borderRadius": "8px", "border": "1px solid #e0e0e0"}
        
        return (opts, [], card_style, 
                MATERNAL_TREE_OPTIONS, [], card_style, 
                GARDENS_TABLE_OPTIONS, [], card_style, 
                {"display": "block", "textAlign": "center", "marginTop": "20px", "marginBottom": "20px"},
                {"display": "block", "marginBottom": "20px", "padding": "15px", "backgroundColor": "#ffffff", 
                 "borderRadius": "8px", "border": "1px solid #e0e0e0"},
                {"display": "block", "marginBottom": "15px"},
                "",
                year_options, site_options, show_prefilter)
    except ValueError as ve:
        logger.exception("Invalid core table selection in Select and Filter")
        error_msg = "That table is not available in this workflow."
        return [], [], {"display": "none"}, [], [], {"display": "none"}, [], [], {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}, error_msg, [], [], {"display": "none"}
    except Exception as e:
        logger.exception("Unable to fetch Select and Filter columns")
        error_msg = "Column choices are unavailable right now. Try another dataset or try again later."
        return [], [], {"display": "none"}, [], [], {"display": "none"}, [], [], {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}, error_msg, [], [], {"display": "none"}

# Handle Core table Select All and Deselect All buttons
@callback(
    Output('join-core-table-options', 'value', allow_duplicate=True),
    [Input('join-select_all_btn', 'n_clicks'), 
     Input('join-deselect_all_btn', 'n_clicks')],
    [State('join-core-table-options', 'options')],
    prevent_initial_call=True
)
def handle_core_select_buttons(select_all_clicks, deselect_all_clicks, current_options):
    trigger_id = ctx.triggered_id if ctx.triggered_id else None

    if trigger_id == 'join-select_all_btn' and current_options:
        return [opt['value'] for opt in current_options]
    if trigger_id == 'join-deselect_all_btn':
        return []
    
    raise PreventUpdate

# Handle Tree table Select All and Deselect All buttons
@callback(
    Output('join-tree-table-options', 'value', allow_duplicate=True),
    [Input('join-select_all_btn-2', 'n_clicks'), 
     Input('join-deselect_all_btn-2', 'n_clicks')],
    [State('join-tree-table-options', 'options')],
    prevent_initial_call=True
)
def handle_tree_select_buttons(select_all_clicks, deselect_all_clicks, current_options):
    trigger_id = ctx.triggered_id if ctx.triggered_id else None

    if trigger_id == 'join-select_all_btn-2' and current_options:
        return [opt['value'] for opt in current_options]
    if trigger_id == 'join-deselect_all_btn-2':
        return []
    
    raise PreventUpdate

# Handle Garden table Select All and Deselect All buttons
@callback(
    Output('join-garden-table-options', 'value', allow_duplicate=True),
    [Input('join-select_all_btn-3', 'n_clicks'), 
     Input('join-deselect_all_btn-3', 'n_clicks')],
    [State('join-garden-table-options', 'options')],
    prevent_initial_call=True
)
def handle_garden_select_buttons(select_all_clicks, deselect_all_clicks, current_options):
    trigger_id = ctx.triggered_id if ctx.triggered_id else None

    if trigger_id == 'join-select_all_btn-3' and current_options:
        return [opt['value'] for opt in current_options]
    if trigger_id == 'join-deselect_all_btn-3':
        return []
    
    raise PreventUpdate

# Update join preview based on selections
@callback(
    [Output("join-tab-preview", "children"),
     Output("join-tab-preview-container", "style", allow_duplicate=True)],
    [Input("join-tab-core-dropdown", "value"),
     Input("join-core-table-options", "value"),
     Input("join-tree-table-options", "value"),
     Input("join-garden-table-options", "value"),
     Input("join-year-filter", "value"),
     Input("join-site-filter", "value")],
    prevent_initial_call=True
)
def update_join_preview(core_table, core_vars, tree_vars, garden_vars, year_filter, site_filter):
    if not core_table:
        return "", {"display": "none"}
    
    preview_parts = []
    try:
        core_df = _fetch_for_user(f"SELECT TOP 0 * FROM [dbo].[{core_table}]")
        core_columns = core_df.columns.tolist() if core_df is not None else []
    except Exception:
        core_columns = None
    
    # Core table info
    core_name = CORE_TABLES.get(core_table, core_table)
    core_count = len(core_vars) if core_vars else 0
    preview_parts.append(html.Div([
        html.Strong(f"{core_name}:"), 
        html.Span(f" {core_count} columns selected", style={"marginLeft": "10px"})
    ], style={"marginBottom": "8px"}))
    
    # Pre-join filter info
    if year_filter and len(year_filter) > 0:
        year_str = ", ".join(str(int(y)) if float(y) == int(y) else str(y) for y in sorted(year_filter))
        preview_parts.append(html.Div([
            html.Strong("Year filter:"),
            html.Span(f" {year_str}", style={"marginLeft": "10px", "color": "#007bff"})
        ], style={"marginBottom": "8px"}))
    
    if site_filter and len(site_filter) > 0:
        site_str = ", ".join(str(s) for s in sorted(site_filter))
        preview_parts.append(html.Div([
            html.Strong("Site filter:"),
            html.Span(f" {site_str}", style={"marginLeft": "10px", "color": "#007bff"})
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
        garden_validation = _garden_join_validation_message(core_table, core_columns, None)
        match_info = "(Matched by Site + Year)"
        preview_parts.append(html.Div([
            html.Strong("Garden Climate:"), 
            html.Span(f" {garden_count} columns selected", style={"marginLeft": "10px"}),
            html.Br(),
            html.Span(match_info, style={"fontSize": "0.85em", "color": "#888", "marginLeft": "20px"})
        ], style={"marginBottom": "8px"}))
        if garden_validation:
            preview_parts.append(html.Div(garden_validation, className="status-warning"))
    else:
        preview_parts.append(html.Div(
            "Garden Climate is not selected. Single-dataset exports and joins without Garden Climate are allowed.",
            style={"fontSize": "0.85em", "color": "#666", "marginBottom": "8px"},
        ))
    
    if not core_vars and not tree_vars and not garden_vars:
        preview_parts.append(html.Div([
            html.Span("Select at least one variable to preview results.", style={"color": "#856404", "fontStyle": "italic"})
        ]))
    
    return preview_parts, {"display": "block", "marginBottom": "20px", "padding": "15px", 
                          "backgroundColor": "#ffffff", "borderRadius": "8px", "border": "1px solid #e0e0e0"}

# Main execution callback - generates the SQL query (no count initially)
@callback(
    [
        Output("join-tab-full-query", "data"),
        Output("join-tab-csv-filename", "value", allow_duplicate=True),
        Output("join-tab-results-div", "style", allow_duplicate=True),
        Output("join-row-count-container", "style", allow_duplicate=True),
        Output("join-tab-execute-button", "children"),
        Output("join-tab-execute-button", "disabled"),
        Output("join-tab-general-error", "children", allow_duplicate=True),
        Output("join-row-count", "value"),
        Output("join-right-placeholder", "style", allow_duplicate=True),
    ],
    [Input("join-tab-execute-button", "n_clicks")],
    [
        State("join-tab-core-dropdown", "value"),
        State("join-core-table-options", "value"),
        State("join-tree-table-options", "value"),
        State("join-garden-table-options", "value"),
        State("join-year-filter", "value"),
        State("join-site-filter", "value"),
    ],
    prevent_initial_call=True,
)
def execute_join(n_clicks, core_table, core_table_vars, maternal_tree_vars, garden_climate_vars, year_filter, site_filter):
    if not n_clicks or not core_table or (not core_table_vars and not maternal_tree_vars and not garden_climate_vars):
        raise PreventUpdate

    try:
        # Validate table name
        validate_table_name(core_table, ALLOWED_CORE_TABLES)
        
        core_schema_df = _fetch_for_user(f"SELECT TOP 0 * FROM [dbo].[{core_table}]")
        garden_schema_df = _fetch_for_user(f"SELECT TOP 0 * FROM [dbo].[{GARDENS_TABLE}]")
        core_columns = core_schema_df.columns.tolist() if core_schema_df is not None else []
        garden_columns = garden_schema_df.columns.tolist() if garden_schema_df is not None else []

        # 1) Required core columns. Join keys are hidden from checklists but
        # always included in outputs when they exist on the selected core table.
        required_core_cols = [c for c in _required_core_cols(core_table) if c in core_columns]
        tree_key_cols = TREE_JOIN_KEYS
        garden_key_cols = GARDEN_JOIN_KEYS

        if garden_climate_vars:
            garden_error = _garden_join_validation_message(core_table, core_columns, garden_columns)
            if garden_error:
                return None, dash.no_update, {"display": "none"}, {"display": "none"}, "Join Data & View Results", False, garden_error, 100, {"display": "block", "height": "100%"}

        # 2) Core SELECT
        core_cols = required_core_cols[:]
        if core_table_vars:
            core_cols += [c for c in core_table_vars if c not in core_cols]
        core_sel = ", ".join(f"core.[{c}]" for c in core_cols)
        selected_clauses = [core_sel]

        # 3) Clean out any key-columns from the non-core selections
        safe_tree_vars = [c for c in maternal_tree_vars or [] if c not in tree_key_cols]
        safe_garden_vars = [c for c in garden_climate_vars or [] if c not in garden_key_cols]

        # 4) Maternal-tree join
        joins = []
        if maternal_tree_vars:
            if safe_tree_vars:
                tree_sel = ", ".join(
                    f"maternal.[{c}] AS [maternal_{c.replace(' ', '_')}]"
                    for c in safe_tree_vars
                )
                selected_clauses.append(tree_sel)

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

        # 5) Garden-climate join
        if garden_climate_vars:
            if not safe_garden_vars:
                return None, dash.no_update, {"display": "none"}, {"display": "none"}, "Join Data & View Results", False, "Select at least one non-key Garden Climate variable. Site and Year are included automatically.", 100, {"display": "block", "height": "100%"}
            if safe_garden_vars:
                garden_sel = ", ".join(
                    f"garden.[{c}] AS [garden_{c.replace(' ', '_')}]"
                    for c in safe_garden_vars
                )
                selected_clauses.append(garden_sel)

            garden_cols = ["TRY_CAST(TRY_CAST([Year] AS NUMERIC) AS INT) AS [Year]", "[Site]"] + [f"[{c}]" for c in safe_garden_vars]
            join_cond = "core.[Year] = garden.[Year] AND core.[Site] = garden.[Site]"

            joins.append(f"""
LEFT JOIN (
  SELECT {', '.join(garden_cols)}
  FROM [dbo].[{GARDENS_TABLE}]
) garden
  ON {join_cond}
""".strip())

        # 6) Build WHERE clause for pre-join filters
        where_clauses = []
        if year_filter and len(year_filter) > 0 and "Year" in core_columns:
            year_placeholders = ", ".join(str(int(y)) for y in year_filter)
            where_clauses.append(f"core.[Year] IN ({year_placeholders})")
        if site_filter and len(site_filter) > 0:
            # Sanitize site values to prevent injection
            safe_sites = ", ".join(f"'{str(s).replace(chr(39), chr(39)+chr(39))}'" for s in site_filter)
            where_clauses.append(f"core.[Site] IN ({safe_sites})")
        
        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        # 7) Assemble base query (without TOP clause)
        base_query = f"""
SELECT DISTINCT
  {', '.join(selected_clauses)}
FROM [dbo].[{core_table}] core
{chr(10).join(joins)}
{where_sql}
""".strip()
        
        # Generate default filename based on core table name
        default_filename = CORE_TABLES.get(core_table, "joined_data").lower().replace(" ", "_").replace("/", "_")
        
        # Store the base query (without TOP) - count will be determined after first query
        return (base_query, default_filename, 
                {"display": "block", "padding": "20px", "backgroundColor": "#ffffff", "borderRadius": "8px", "border": "1px solid #e0e0e0"}, 
                {"display": "block", "marginBottom": "15px"}, 
                "Join Data & View Results", False, "", 100, {"display": "none"})

    except ValueError as ve:
        logger.exception("Invalid join request")
        error_msg = "That dataset selection is not available."
        return None, dash.no_update, {"display": "none"}, {"display": "none"}, "Join Data & View Results", False, error_msg, 100, {"display": "block", "height": "100%"}
    except Exception as e:
        logger.exception("Unable to execute Select and Filter join")
        error_msg = "Results could not be prepared. Try fewer variables or narrower filters."
        return None, dash.no_update, {"display": "none"}, {"display": "none"}, "Join Data & View Results", False, error_msg, 100, {"display": "block", "height": "100%"}

# Toggle visibility of row count input
@callback(
    Output('join-row-count-input-wrapper', 'style'),
    [Input('join-limit-rows-toggle', 'value')],
    prevent_initial_call=True
)
def toggle_row_count_input(limit_toggle):
    if limit_toggle and "limit" in limit_toggle:
        return {"display": "flex", "alignItems": "center"}
    return {"display": "none"}

# Update the grid data based on row count (and determine total count from actual query)
@callback(
    [Output('join-grid-wrapper', 'children'),
     Output('join-tab-results-stats', 'children'),
     Output('join-max-rows-info', 'children'),
     Output('join-row-count', 'max'),
     Output('download-join-tab-csv-button', 'children'),
     Output('download-join-tab-all-csv-button', 'children'),
     Output('join-download-warning', 'children'),
     Output('join-tab-results-div', 'style', allow_duplicate=True),
     Output('join-row-count-container', 'style', allow_duplicate=True),
     Output('join-right-placeholder', 'style', allow_duplicate=True)],
    [Input('join-tab-full-query', 'data'),
     Input('join-row-count', 'value'),
     Input('join-limit-rows-toggle', 'value')],
    prevent_initial_call=True
)
def update_grid_display(base_query, row_count, limit_toggle):
    if not base_query:
        raise PreventUpdate

    try:
        # Determine if we should limit rows
        use_limit = limit_toggle and "limit" in limit_toggle and row_count and row_count > 0
        
        if use_limit:
            if row_count < 1:
                row_count = 100
            # Execute with TOP limit
            display_query = f"""
SELECT TOP {row_count}
  q.*,
  COUNT(*) OVER() AS __total_count__
FROM (
  {base_query}
) AS q
"""
        else:
            # Execute without limit - show all rows, but still get count
            display_query = f"""
SELECT
  q.*,
  COUNT(*) OVER() AS __total_count__
FROM (
  {base_query}
) AS q
"""

        result_df = _fetch_for_user(display_query)

        if result_df is None or result_df.empty:
            empty_div = html.Div("No results returned", style={"padding": "20px", "textAlign": "center", "color": "#666"})
            return empty_div, "No results returned", "", 1000000, dash.no_update, dash.no_update, html.Div(), {"display": "block", "padding": "20px", "backgroundColor": "#ffffff", "borderRadius": "8px", "border": "1px solid #e0e0e0"}, {"display": "block", "marginBottom": "15px"}, {"display": "none"}

        # Pull the total count and then drop the helper column so it doesn't show in the grid/downloads
        total_count = 0
        if "__total_count__" in result_df.columns:
            try:
                total_count = int(result_df["__total_count__"].iloc[0])
            except Exception:
                total_count = 0
            result_df = result_df.drop(columns=["__total_count__"], errors="ignore")

        actual_rows = len(result_df)

        # Max rows info (mirror dataset tab pattern)
        if total_count > 0:
            total_count_text = f"{total_count:,}"
            max_rows_text = f"(Max: {total_count:,} rows available)"
            max_val = total_count
        else:
            # Fallback: we couldn't determine total count; keep behavior permissive
            total_count_text = f"{actual_rows:,}+"
            max_rows_text = ""
            max_val = 1000000

        # Prepare data for AG Grid
        row_data = result_df.to_dict("records")
        column_defs = []
        
        # Add checkbox column pinned to left
        column_defs.append({
            'headerName': '',
            'field': '__select__',
            'checkboxSelection': True,
            'headerCheckboxSelection': True,
            'pinned': 'left',
            'width': 50,
            'sortable': False,
            'filter': False
        })
        
        # Add column definitions with appropriate filters
        for c in result_df.columns:
            col_series = result_df[c]
            is_num = False
            
            # Determine if column is numeric
            try:
                if is_numeric_dtype(col_series):
                    is_num = True
                else:
                    # Try coercing a small sample to detect numbers
                    sample = pd.to_numeric(col_series.dropna().head(TYPE_DETECTION_SAMPLE_SIZE), errors='coerce')
                    if len(sample) > 0 and sample.notna().sum() / float(len(sample)) >= NUMERIC_THRESHOLD:
                        is_num = True
            except Exception:
                is_num = False
            
            if is_num:
                col_def = {
                    'headerName': c,
                    'field': c,
                    'filter': 'agNumberColumnFilter',
                    'filterParams': {
                        'filterOptions': ['equals', 'notEqual', 'lessThan', 'lessThanOrEqual', 'greaterThan', 'greaterThanOrEqual'],
                        'suppressAndOrCondition': True
                    }
                }
            else:
                # Use dropdown (set) filter for categorical/text columns
                unique_vals = col_series.dropna().unique().tolist()
                # If reasonable number of unique values, use set filter; otherwise text filter
                if len(unique_vals) <= 200:
                    col_def = {
                        'headerName': c,
                        'field': c,
                        'filter': True,
                        'filterParams': {
                            'filterOptions': ['contains','notContains','equals','notEqual','startsWith','endsWith'],
                            'suppressAndOrCondition': True
                        }
                    }
                else:
                    col_def = {
                        'headerName': c,
                        'field': c,
                        'filter': 'agTextColumnFilter',
                        'filterParams': {
                            'filterOptions': ['contains','notContains','equals','notEqual','startsWith','endsWith'],
                            'suppressAndOrCondition': True
                        }
                    }
            
            column_defs.append(col_def)
        
        # Create the grid component
        grid_component = html.Div(
            AgGrid(
                id='join-tab-grid',
                rowData=row_data,
                columnDefs=column_defs,
                defaultColDef={
                    'filter': True,
                    'sortable': True,
                    'resizable': True,
                    'minWidth': 50,
                    'width': 120
                },
                dashGridOptions={'rowSelection': 'multiple', 'rowMultiSelectWithClick': True},
                selectedRows=[],
                className='ag-theme-alpine',
                style={'width': '100%', 'height': '500px'},
                enableEnterpriseModules=False,
            ),
            style={"width": "100%"}
        )
        
        # Stats text - removed per user request
        stats_text = ""
        
        # Button texts
        filtered_btn_text = f"Download Filtered Dataset"
        full_btn_text = f"Download All Data ({total_count_text} rows)"
        
        # Download warning for large datasets
        download_warning = html.Div()
        if actual_rows >= 100000:
            download_warning = html.Div([
                html.Span("⚠️ ", style={"fontSize": "18px"}),
                html.Span(f"Large dataset warning: Downloading all data may take significant time and resources ({actual_rows:,}+ rows).", 
                         style={"fontWeight": "bold"})
            ], style={
                "color": "#856404",
                "backgroundColor": "#fff3cd",
                "border": "1px solid #ffeaa7",
                "borderRadius": "4px",
                "padding": "12px",
                "marginBottom": "10px"
            })

        return grid_component, stats_text, max_rows_text, max_val, filtered_btn_text, full_btn_text, download_warning, {"display": "block", "padding": "20px", "backgroundColor": "#ffffff", "borderRadius": "8px", "border": "1px solid #e0e0e0"}, {"display": "block", "marginBottom": "15px"}, {"display": "none"}

    except Exception as e:
        logger.exception("Unable to update Select and Filter grid")
        error_msg = "Results are unavailable right now. Try a smaller preview or adjust your filters."
        error_div = html.Div(error_msg, className="status-warning")
        return error_div, "", "", 1000000, dash.no_update, dash.no_update, html.Div(), {"display": "none"}, {"display": "none"}, {"display": "block", "height": "100%"}

# Reset results when any selection changes
@callback(
    [Output("join-tab-results-div", "style", allow_duplicate=True),
     Output("join-row-count-container", "style", allow_duplicate=True),
     Output("join-tab-full-query", "data", allow_duplicate=True),
     Output("join-grid-wrapper", "children", allow_duplicate=True),
     Output("join-tab-results-stats", "children", allow_duplicate=True),
     Output("join-filter-count-text", "children", allow_duplicate=True),
     Output("join-selected-count-text", "children", allow_duplicate=True),
     Output("join-download-warning", "children", allow_duplicate=True),
     Output("stats-main-container", "style", allow_duplicate=True),
     Output("stats-test-dropdown", "value", allow_duplicate=True),
     Output("test-container", "style", allow_duplicate=True),
     Output("lr-output-content", "children", allow_duplicate=True),
     Output("pca-output-content", "children", allow_duplicate=True),
     Output("summary-output-content", "children", allow_duplicate=True),
     Output("pd-output-content", "children", allow_duplicate=True),
     Output("join-right-placeholder", "style", allow_duplicate=True)],
    [Input("join-core-table-options", "value"),
     Input("join-tree-table-options", "value"),
     Input("join-garden-table-options", "value"),
     Input("join-year-filter", "value"),
     Input("join-site-filter", "value")],
    prevent_initial_call=True
)
def reset_results_on_selection_change(core_vars, tree_vars, garden_vars, year_filter, site_filter):
    # Hide and clear stale generated outputs whenever selected inputs change.
    empty = html.Div()
    return (
        {"display": "none"},
        {"display": "none"},
        None,
        empty,
        "",
        "",
        "",
        empty,
        {"display": "none"},
        None,
        {"display": "none"},
        empty,
        empty,
        empty,
        empty,
        {"display": "block", "height": "100%"},
    )

# Update filter and selection counts for AG Grid
@callback(
    [Output('join-filter-count-text', 'children'), 
     Output('join-selected-count-text', 'children')],
    [Input('join-tab-grid', 'rowData'), 
     Input('join-tab-grid', 'selectedRows'), 
     Input('join-tab-grid', 'filterModel')]
)
def update_join_table_counts(row_data, selected_rows, filter_model):
    """Update the filtered and selected row counts for AG Grid"""
    if not row_data:
        return "", ""
    
    df = pd.DataFrame(row_data)

    if filter_model:
        filtered = apply_filter_model(df, filter_model)
    else:
        filtered = df

    filtered_count = len(filtered)
    selected_count = len(selected_rows) if selected_rows else 0

    return f"Filtered rows: {filtered_count}", f"Selected rows: {selected_count}"

# Update download button text based on filtering
@callback(
    [Output("download-join-tab-csv-button", "children", allow_duplicate=True)],
    [Input('join-tab-grid', 'rowData'),
     Input('join-tab-grid', 'filterModel')],
    prevent_initial_call=True
)
def update_download_button_text(row_data, filter_model):
    """Update download button text based on current filter state"""
    if not row_data:
        raise PreventUpdate
    
    try:
        df = pd.DataFrame(row_data)
        
        if filter_model:
            filtered = apply_filter_model(df, filter_model)
            filtered_count = len(filtered)
        else:
            filtered_count = len(df)
        
        filtered_btn_text = f"Download Filtered Dataset ({filtered_count:,} rows)"
        
        return [filtered_btn_text]
    except Exception as e:
        print(f"Error updating download button: {e}")
        raise PreventUpdate

# Download filtered/sorted data from AG Grid
@callback(
    Output('download-join-tab-csv', 'data'),
    Input('download-join-tab-csv-button', 'n_clicks'),
    [State('join-tab-grid', 'rowData'),
     State('join-tab-grid', 'selectedRows'),
     State('join-tab-grid', 'filterModel'),
     State('join-tab-csv-filename', 'value')],
    prevent_initial_call=True
)
def download_filtered_join_results(n_clicks, row_data, selected_rows, filter_model, custom_filename):
    if not n_clicks or not row_data:
        raise PreventUpdate
    
    try:
        # Priority 1: Use selected rows if any
        if selected_rows and len(selected_rows) > 0:
            data_to_download = selected_rows
        # Priority 2: Use filtered data if filters are applied
        elif filter_model:
            df = pd.DataFrame(row_data)
            filtered_df = apply_filter_model(df, filter_model)
            data_to_download = filtered_df.to_dict('records')
        # Priority 3: Use all grid data
        else:
            data_to_download = row_data
        
        if not data_to_download:
            raise PreventUpdate
        
        # Convert data back to DataFrame
        df = pd.DataFrame(data_to_download)
        if df.empty:
            raise PreventUpdate
        
        # Determine filename
        if custom_filename and custom_filename.strip():
            clean_filename = "".join(c for c in custom_filename.strip() if c.isalnum() or c in (' ', '-', '_')).strip()
            if not clean_filename:
                clean_filename = "joined_data"
            filename = f"{clean_filename}.csv"
        else:
            filename = "joined_data.csv"
        
        return dcc.send_data_frame(df.to_csv, filename, index=False)
    except Exception as e:
        print(f"Error during filtered download: {e}")
        raise PreventUpdate

# Download all data (unfiltered) - fetches from database
@callback(
    Output('download-join-tab-all-csv', 'data'),
    Input('download-join-tab-all-csv-button', 'n_clicks'),
    [State('join-tab-full-query', 'data'),
     State('join-tab-csv-filename', 'value')],
    prevent_initial_call=True
)
def download_all_join_results(n_clicks, base_query, custom_filename):
    if not n_clicks or not base_query:
        raise PreventUpdate
    
    try:
        # Fetch all data from database using the stored query
        df = _fetch_for_user(base_query)
        
        if df is None or df.empty:
            raise PreventUpdate
        
        # Determine filename
        if custom_filename and custom_filename.strip():
            clean_filename = "".join(c for c in custom_filename.strip() if c.isalnum() or c in (' ', '-', '_')).strip()
            if not clean_filename:
                clean_filename = "joined_data_all"
            filename = f"{clean_filename}_all.csv"
        else:
            filename = "joined_data_all.csv"
        
        return dcc.send_data_frame(df.to_csv, filename, index=False)
    except Exception as e:
        print(f"Error during full download: {e}")
        raise PreventUpdate

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
        raise PreventUpdate
    
    # Show error message if no variables are selected anywhere.
    if not core_table_vars and not maternal_tree_vars and not garden_climate_vars:
        return {"display": "block", "textAlign": "center", "marginTop": "20px",
                "padding": "15px", "backgroundColor": "#fff3cd", 
                "borderRadius": "8px", "border": "1px solid #ffc107"}
    
    return {"display": "none"}

# ====== STATISTICAL CALLBACKS ======

@callback(
    [Output("stats-main-container", "style", allow_duplicate=True),
     Output("lr-x-variable", "options"),
     Output("lr-y-variable", "options"),
     Output("pca-variables", "options"),
     Output("summary-variable", "options"),
     Output("pd-x-variable", "options"),
     Output("pd-y-variable", "options"),
     Output("stats-test-dropdown", "value"),
     Output("lr-x-variable", "value"),
     Output("lr-y-variable", "value"),
     Output("pca-variables", "value"),
     Output("summary-variable", "value"),
     Output("pd-x-variable", "value"),
     Output("pd-y-variable", "value"),
     Output("lr-output-content", "children", allow_duplicate=True),
     Output("pca-output-content", "children", allow_duplicate=True),
     Output("summary-output-content", "children", allow_duplicate=True),
     Output("pd-output-content", "children", allow_duplicate=True)],
    [Input('join-tab-grid', 'rowData')],
    prevent_initial_call=True
)
def populate_stats_options(row_data):
    # This runs when grid row data is first loaded/updated. Let's provide options based on numeric columns in row_data.
    if not row_data:
        return {"display": "none"}, [], [], [], [], [], [], None, None, None, None, None, None, None, html.Div(), html.Div(), html.Div(), html.Div()
    
    df = pd.DataFrame(row_data)
    numeric_cols = []
    
    all_options = []
    for c in df.columns:
        if c == '__select__':
            continue
        all_options.append({"label": c, "value": c})
        col_series = df[c]
        try:
            if is_numeric_dtype(col_series):
                numeric_cols.append(c)
            else:
                sample = pd.to_numeric(col_series.dropna().head(TYPE_DETECTION_SAMPLE_SIZE), errors='coerce')
                if len(sample) > 0 and sample.notna().sum() / float(len(sample)) >= NUMERIC_THRESHOLD:
                    numeric_cols.append(c)
        except Exception:
            pass
            
    options = [{"label": col, "value": col} for col in numeric_cols]
    
    # We also clear out previous results and selections to easily support new joins
    return (
        {"display": "block", "padding": "20px", "backgroundColor": "#ffffff", "borderRadius": "8px", "border": "1px solid #e0e0e0", "marginTop": "20px"},
        options, options, options, options, all_options, all_options,
        None, None, None, None, None, None, None,
        html.Div(), html.Div(), html.Div(), html.Div()
    )

@callback(
    [Output("test-container", "style", allow_duplicate=True),
     Output("linear-regression-div", "style"),
     Output("pca-div", "style"),
     Output("summary-stats-div", "style"),
     Output("plot-data-div", "style"),
     Output('lr-output-content', 'children', allow_duplicate=True),
     Output('pca-output-content', 'children', allow_duplicate=True),
     Output('summary-output-content', 'children', allow_duplicate=True),
     Output('pd-output-content', 'children', allow_duplicate=True)],
    [Input("stats-test-dropdown", "value")],
    prevent_initial_call=True
)
def show_test_container(selected_test):
    empty_output = html.Div()
    if not selected_test:
        return {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}, empty_output, empty_output, empty_output, empty_output
    
    lr_style = {"display": "block"} if selected_test == "linear_regression" else {"display": "none"}
    pca_style = {"display": "block"} if selected_test == "pca" else {"display": "none"}
    summary_style = {"display": "block"} if selected_test == "summary_stats" else {"display": "none"}
    plot_data_style = {"display": "block"} if selected_test == "plot_data" else {"display": "none"}
    
    return {"display": "block"}, lr_style, pca_style, summary_style, plot_data_style, empty_output, empty_output, empty_output, empty_output

@callback(
    Output("pca-warning", "children", allow_duplicate=True),
    [Input("pca-variables", "value")],
    prevent_initial_call=True
)
def clear_pca_warning(variables):
    return html.Div()

# Analysis Helper
def get_analysis_df(base_query, filter_model):
    query = f"SELECT TOP 50000 * FROM ({base_query}) q"
    df = _fetch_for_user(query)
    if df is not None and not df.empty and filter_model:
        df = apply_filter_model(df, filter_model)
    return df

@callback(
    Output("lr-output-content", "children", allow_duplicate=True),
    [Input("run-lr-button", "n_clicks")],
    [State("join-tab-full-query", "data"),
     State("join-tab-grid", "filterModel"),
     State("lr-x-variable", "value"),
     State("lr-y-variable", "value")],
    prevent_initial_call=True
)
def run_linear_regression(n_clicks, base_query, filter_model, x_var, y_var):
    if not base_query or not x_var or not y_var:
        raise PreventUpdate
        
    df = get_analysis_df(base_query, filter_model)
    df = df.dropna(subset=[x_var, y_var])
    
    # Needs numeric conversion just in case
    df[x_var] = pd.to_numeric(df[x_var], errors='coerce')
    df[y_var] = pd.to_numeric(df[y_var], errors='coerce')
    df = df.dropna(subset=[x_var, y_var])
    
    if df is None or df.empty or len(df) < MIN_ROWS_FOR_REGRESSION:
        return html.Div([
            html.H5("Insufficient Data", style={"color": "red"}),
            html.P("Not enough valid data points for regression analysis.")
        ], style={"color": "red", "fontWeight": "bold"})
        
    x = df[x_var].values
    y = df[y_var].values
    
    slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
    x_range = np.linspace(min(x), max(x), 100)
    y_pred = slope * x_range + intercept
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=y, mode='markers', name='Data Points', marker=dict(color='blue', opacity=0.6, size=8)))
    fig.add_trace(go.Scatter(x=x_range, y=y_pred, mode='lines', name='Regression Line', line=dict(color='red', width=2)))
    
    r_squared = r_value**2
    equation = f"y = {slope:.4f}x + {intercept:.4f}"
    
    fig.update_layout(
        title=f"Linear Regression: {y_var} vs {x_var}", xaxis_title=x_var, yaxis_title=y_var,
        height=500, paper_bgcolor="#e5ecf6", plot_bgcolor="#f9f9f9",
        annotations=[
            dict(x=0.02, y=0.98, xref="paper", yref="paper", text=f"Equation: {equation}<br>R² = {r_squared:.4f}<br>p-value = {p_value:.4f}",
                 showarrow=False, bgcolor="rgba(255, 255, 255, 0.8)", bordercolor="rgba(0, 0, 0, 0.2)", borderwidth=1, borderpad=10, font=dict(size=12))
        ]
    )
    
    # We replace HTML table with plotly figure table (so they can download as image)
    table_fig = go.Figure(data=[go.Table(
        header=dict(values=['Metric', 'Value'], align='left', line_color='darkslategray', fill_color='lightskyblue'),
        cells=dict(values=[
            ['Slope', 'Intercept', 'R-squared', 'p-value', 'Standard Error', 'Sample Size'], 
            [f"{slope:.6f}", f"{intercept:.6f}", f"{r_squared:.6f}", f"{p_value:.6f}", f"{std_err:.6f}", str(len(df))]
        ], align='left', line_color='darkslategray', fill_color='white')
    )])
    
    table_fig.update_layout(
        title="Regression Statistics",
        height=250, margin=dict(t=50, b=0, l=0, r=0), paper_bgcolor="#ffffff", plot_bgcolor="#ffffff"
    )

    return html.Div([
        dcc.Graph(figure=fig),
        dcc.Graph(figure=table_fig)
    ], style={"padding": "20px", "backgroundColor": "#ffffff", "borderRadius": "8px", "border": "1px solid #e0e0e0"})


@callback(
    Output("pca-output-content", "children", allow_duplicate=True),
    [Input("run-pca-button", "n_clicks")],
    [State("join-tab-full-query", "data"),
     State("join-tab-grid", "filterModel"),
     State("pca-variables", "value"),
     State("pca-dimensions", "value")], 
    prevent_initial_call=True
)
def run_pca(n_clicks, base_query, filter_model, variables, dimensions):
    if not base_query or not variables:
        raise PreventUpdate
        
    df = get_analysis_df(base_query, filter_model)
    df = df.dropna(subset=variables)
    
    for v in variables:
        df[v] = pd.to_numeric(df[v], errors='coerce')
        
    df = df.dropna(subset=variables)
    
    if df is None or df.empty or len(df) < MIN_ROWS_FOR_PCA:
        return html.Div([
            html.H5("Insufficient Data", style={"color": "red"}),
            html.P("Not enough valid data points for PCA analysis.")
        ], style={"color": "red", "fontWeight": "bold"})
        
    scaler = StandardScaler()
    scaled_data = scaler.fit_transform(df[variables])
    
    n_components = min(3, len(variables))
    pca = PCA(n_components=n_components)
    pca_result = pca.fit_transform(scaled_data)
    
    pca_df = pd.DataFrame(data=pca_result, columns=[f'PC{i+1}' for i in range(n_components)])
    explained_variance = pca.explained_variance_ratio_ * 100
    
    if dimensions == '3d' and n_components >= 3:
        fig = px.scatter_3d(pca_df, x='PC1', y='PC2', z='PC3', title="3D PCA Visualization",
            labels={'PC1': f'PC1 ({explained_variance[0]:.2f}%)', 'PC2': f'PC2 ({explained_variance[1]:.2f}%)', 'PC3': f'PC3 ({explained_variance[2]:.2f}%)'}, opacity=0.7)
    else:
        fig = px.scatter(pca_df, x='PC1', y='PC2', title="2D PCA Visualization",
            labels={'PC1': f'PC1 ({explained_variance[0]:.2f}%)', 'PC2': f'PC2 ({explained_variance[1]:.2f}%)'}, opacity=0.7)
            
    fig.update_layout(height=600, paper_bgcolor="#e5ecf6", plot_bgcolor="#f9f9f9")
    
    loadings = pca.components_
    loading_df = pd.DataFrame(loadings.T, columns=[f'PC{i+1}' for i in range(n_components)], index=variables)

    # Explained Variance Table as Plotly Figure
    ev_headers = ["Component", "Variance Explained (%)", "Cumulative Variance (%)"]
    ev_components = [f"PC{i+1}" for i in range(n_components)]
    ev_var = [f"{explained_variance[i]:.2f}%" for i in range(n_components)]
    ev_cum = [f"{np.sum(explained_variance[:i+1]):.2f}%" for i in range(n_components)]
    
    ev_table_fig = go.Figure(data=[go.Table(
        header=dict(values=ev_headers, align='left', line_color='darkslategray', fill_color='lightskyblue'),
        cells=dict(values=[ev_components, ev_var, ev_cum], align='left', line_color='darkslategray', fill_color='white')
    )])
    ev_table_fig.update_layout(title="Explained Variance", height=200, margin=dict(t=50, b=0, l=0, r=0), paper_bgcolor="#ffffff", plot_bgcolor="#ffffff")

    # Loadings Table as Plotly Figure
    loadings_headers = ["Variable"] + [f"PC{i+1}" for i in range(n_components)]
    loadings_values = [variables] + [[f"{loading_df.loc[var, f'PC{i+1}']:.4f}" for var in variables] for i in range(n_components)]
    
    load_table_fig = go.Figure(data=[go.Table(
        header=dict(values=loadings_headers, align='left', line_color='darkslategray', fill_color='lightskyblue'),
        cells=dict(values=loadings_values, align='left', line_color='darkslategray', fill_color='white')
    )])
    load_table_fig.update_layout(title="Variable Loadings", height=300, margin=dict(t=50, b=0, l=0, r=0), paper_bgcolor="#ffffff", plot_bgcolor="#ffffff")
    
    return html.Div([
        dcc.Graph(figure=fig),
        dcc.Graph(figure=ev_table_fig),
        dcc.Graph(figure=load_table_fig)
    ], style={"padding": "20px", "backgroundColor": "#ffffff", "borderRadius": "8px", "border": "1px solid #e0e0e0"})

@callback(
    Output("summary-output-content", "children", allow_duplicate=True),
    [Input("run-summary-button", "n_clicks")],
    [State("join-tab-full-query", "data"),
     State("join-tab-grid", "filterModel"),
     State("summary-variable", "value")],
    prevent_initial_call=True
)
def run_summary(n_clicks, base_query, filter_model, variable):
    if not base_query or not variable:
        raise PreventUpdate
        
    df = get_analysis_df(base_query, filter_model)
    
    df[variable] = pd.to_numeric(df[variable], errors='coerce')
    clean_data = df[variable].dropna()
    
    if len(clean_data) < 2:
        return html.Div([
            html.H5("Insufficient Data", style={"color": "red"}),
            html.P("Not enough valid data points for summary statistics.")
        ], style={"color": "red", "fontWeight": "bold"})
        
    mean = clean_data.mean()
    median = clean_data.median()
    std_dev = clean_data.std()
    variance = clean_data.var()
    minimum = clean_data.min()
    maximum = clean_data.max()
    q1 = clean_data.quantile(0.25)
    q3 = clean_data.quantile(0.75)
    skewness = stats.skew(clean_data)
    kurtosis = stats.kurtosis(clean_data)
    count = len(clean_data)
    missing = len(df) - count
    
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=clean_data, nbinsx=30, name='Histogram', marker_color='#007bff', opacity=0.7))
    fig.add_vline(x=mean, line_dash="dash", line_color="red", annotation_text=f"Mean: {mean:.2f}", annotation_position="top right")
    fig.add_vline(x=median, line_dash="dash", line_color="green", annotation_text=f"Median: {median:.2f}", annotation_position="top left")
    
    fig.update_layout(title=f"Distribution of {variable}", xaxis_title=variable, yaxis_title="Frequency", height=500, paper_bgcolor="#e5ecf6", plot_bgcolor="#f9f9f9")
    
    # Use Plotly Table for Summary Stats
    sum_table_fig = go.Figure(data=[go.Table(
        header=dict(values=['Statistic', 'Value'], align='left', line_color='darkslategray', fill_color='lightskyblue'),
        cells=dict(values=[
            ['Count', 'Missing Values', 'Mean', 'Median', 'Standard Deviation', 'Variance', 'Minimum', '25th Percentile (Q1)', '75th Percentile (Q3)', 'Maximum', 'Skewness', 'Kurtosis'],
            [f"{count}", f"{missing}", f"{mean:.4f}", f"{median:.4f}", f"{std_dev:.4f}", f"{variance:.4f}", f"{minimum:.4f}", f"{q1:.4f}", f"{q3:.4f}", f"{maximum:.4f}", f"{skewness:.4f}", f"{kurtosis:.4f}"]
        ], align='left', line_color='darkslategray', fill_color='white')
    )])
    sum_table_fig.update_layout(title="Summary Statistics", height=350, margin=dict(t=50, b=0, l=0, r=0), paper_bgcolor="#ffffff", plot_bgcolor="#ffffff")

    # Add Box Plot
    box_fig = go.Figure()
    box_fig.add_trace(go.Box(x=clean_data, name=variable, marker_color='#28a745'))
    box_fig.update_layout(title=f"Box Plot of {variable}", xaxis_title=variable, height=300, paper_bgcolor="#e5ecf6", plot_bgcolor="#f9f9f9")
    
    return html.Div([
        dcc.Graph(figure=fig),
        dcc.Graph(figure=box_fig),
        dcc.Graph(figure=sum_table_fig)
    ], style={"padding": "20px", "backgroundColor": "#ffffff", "borderRadius": "8px", "border": "1px solid #e0e0e0"})


@callback(
    [Output("pd-output-content", "children", allow_duplicate=True),
     Output('graph-type-selector', 'style', allow_duplicate=True)],
    [Input("run-pd-button", "n_clicks"),
     Input('cat-cat-graph-type', 'value')],
    [State('join-tab-full-query', 'data'),
     State('join-tab-grid', 'rowData'),
     State('join-tab-grid', 'selectedRows'),
     State('join-tab-grid', 'filterModel'),
     State('pd-x-variable', 'value'),
     State('pd-y-variable', 'value')],
    prevent_initial_call=True
)
def run_plot_data(n_clicks, graph_type, base_query, row_data, selected_rows, filter_model, x_var, y_var):
    trigger_id = ctx.triggered_id if ctx.triggered_id else None
    if trigger_id != 'run-pd-button' and trigger_id != 'cat-cat-graph-type':
        raise PreventUpdate
        
    if not base_query or not x_var or not y_var:
        raise PreventUpdate
        
    # Priority 1: Use user-selected rows if any
    if selected_rows and len(selected_rows) > 0:
        df = pd.DataFrame(selected_rows)
    # Priority 2: Apply filter model to grid data if filters exist
    elif row_data and filter_model:
        df = pd.DataFrame(row_data)
        df = apply_filter_model(df, filter_model)
    # Priority 3: Use all grid data
    elif row_data:
        df = pd.DataFrame(row_data)
    else:
        df = get_analysis_df(base_query, filter_model)
    
    if df is None or df.empty:
        return html.Div([
            html.H5("Insufficient Data", style={"color": "red"}),
            html.P("No valid data points for plotting.")
        ], style={"color": "red", "fontWeight": "bold"}), {"display": "none"}
        
    df = df.dropna(subset=[x_var, y_var])
    
    if len(df) == 0:
        return html.Div([
            html.H5("Insufficient Data", style={"color": "red"}),
            html.P("No valid data points after dropping missing values.")
        ], style={"color": "red", "fontWeight": "bold"}), {"display": "none"}
        
    x_is_numeric = False
    y_is_numeric = False
    
    try:
        df[x_var] = pd.to_numeric(df[x_var])
        x_is_numeric = True
    except: pass

    try:
        df[y_var] = pd.to_numeric(df[y_var])
        y_is_numeric = True
    except: pass
    
    both_categorical = not x_is_numeric and not y_is_numeric
    
    if x_is_numeric and y_is_numeric:
        fig = px.scatter(df, x=x_var, y=y_var, title=f"{x_var} vs {y_var}")
    elif x_is_numeric or y_is_numeric:
        numeric_var = x_var if x_is_numeric else y_var
        categorical_var = y_var if x_is_numeric else x_var
        df_agg = df.groupby(categorical_var)[numeric_var].mean().reset_index()
        fig = px.bar(df_agg, x=categorical_var, y=numeric_var, title=f"Mean {numeric_var} by {categorical_var}")
    else:
        if graph_type == 'heatmap':
            fig = px.density_heatmap(df, x=x_var, y=y_var, title=f"Heatmap of {x_var} vs {y_var}")
        else:
            fig = px.bar(df, x=x_var, color=y_var, barmode='group', title=f"{x_var} by {y_var}")
            
    fig.update_layout(height=500, paper_bgcolor="#e5ecf6", plot_bgcolor="#f9f9f9")
    
    toggle_style = {"display": "block"} if both_categorical else {"display": "none"}
    
    res = html.Div([
        dcc.Graph(figure=fig)
    ], style={"padding": "20px", "backgroundColor": "#ffffff", "borderRadius": "8px", "border": "1px solid #e0e0e0"})

    return res, toggle_style

# Drag and drop split-pane logic
clientside_callback(
    '''
    function(id) {
        var attachDrag = function() {
            var divider = document.getElementById('join-drag-divider');
            var leftPane = document.getElementById('join-left-pane');
            var container = document.getElementById('join-split-container');
            
            if(!divider || !leftPane || !container) {
                setTimeout(attachDrag, 500);
                return;
            }
            
            if(divider.dataset.listenerAttached === 'true') return;
            divider.dataset.listenerAttached = 'true';
            
            var isResizing = false;
            
            divider.addEventListener('mousedown', function(e) {
                isResizing = true;
                document.body.style.cursor = 'col-resize';
                document.body.style.userSelect = 'none'; // Prevent text selection
                divider.style.backgroundColor = '#007bff';
                e.preventDefault();
            });
            
            document.addEventListener('mousemove', function(e) {
                if (!isResizing) return;
                var containerOffsetLeft = container.getBoundingClientRect().left;
                var newWidth = e.clientX - containerOffsetLeft;
                
                var minW = container.getBoundingClientRect().width * 0.15;
                var maxW = container.getBoundingClientRect().width * 0.85;
                if(newWidth < minW) newWidth = minW;
                if(newWidth > maxW) newWidth = maxW;
                
                leftPane.style.width = newWidth + 'px';
                leftPane.style.flex = '0 0 auto';
                e.preventDefault();
            });
            
            document.addEventListener('mouseup', function(e) {
                if (isResizing) {
                    isResizing = false;
                    document.body.style.cursor = '';
                    document.body.style.userSelect = '';
                    divider.style.backgroundColor = '#f4f4f4';
                }
            });
        };
        
        attachDrag();
        return window.dash_clientside.no_update;
    }
    ''',
    Output('join-drag-divider', 'className'),
    Input('join-drag-divider', 'id')
)

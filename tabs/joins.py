from dash import dcc, html
import pandas as pd
from pandas.api.types import is_numeric_dtype
from database import fetch_data_from_sql
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

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

# Whitelists for validation
ALLOWED_CORE_TABLES = set(CORE_TABLES.keys())


# ====== HELPER FUNCTIONS ======

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
        gardens_df = fetch_data_from_sql(f"SELECT TOP 1 * FROM dbo.[{GARDENS_TABLE}]")
        gardens_cols = gardens_df.columns.tolist() if gardens_df is not None else []
        
        # Maternal tree table
        tree_df = fetch_data_from_sql(f"SELECT TOP 1 * FROM dbo.[{MATERNAL_TREE_TABLE}]")
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


def generate_join_query(core_table, core_table_vars, maternal_tree_vars, garden_climate_vars):
    """
    Generate SQL query for joining tables.
    Returns base query (without TOP clause).
    """
    # Validate table name
    validate_table_name(core_table, ALLOWED_CORE_TABLES)
    
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
    safe_tree_vars = [c for c in maternal_tree_vars or [] if c not in tree_key_cols]
    safe_garden_vars = [c for c in garden_climate_vars or [] if c not in garden_key_cols]

    # 4) Maternal‐tree join
    joins = []
    if maternal_tree_vars:
        if safe_tree_vars:
            tree_sel = ", ".join(
                f"maternal.[{c}] AS [maternal_{c.replace(' ', '_')}]"
                for c in safe_tree_vars
            )
            selected_clauses.append(tree_sel)

        tree_cols = ["TRY_CAST(TRY_CAST([Accession] AS NUMERIC) AS INT) AS [Accession]",
                     "[Locality]"] + [f"[{c}]" for c in safe_tree_vars]
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
            join_cond = "core.[Site] = garden.[Site]"
        else:
            garden_cols = ["TRY_CAST(TRY_CAST([Year] AS NUMERIC) AS INT) AS [Year]",
                           "[Site]"] + [f"[{c}]" for c in safe_garden_vars]
            join_cond = "core.[Year] = garden.[Year] AND core.[Site] = garden.[Site]"

        joins.append(f"""
LEFT JOIN (
  SELECT {', '.join(garden_cols)}
  FROM [dbo].[{GARDENS_TABLE}]
) garden
  ON {join_cond}
""".strip())

    # 6) Assemble base query (without TOP clause)
    base_query = f"""
SELECT DISTINCT
  {', '.join(selected_clauses)}
FROM [dbo].[{core_table}] core
{chr(10).join(joins)}
""".strip()
    
    return base_query


# ====== UI CREATION FUNCTION ======

def create_join_ui(prefix):
    """
    Create the join configuration UI with the given prefix for all component IDs.
    
    Args:
        prefix: String prefix for all component IDs (e.g., 'dataset' or 'stats')
    
    Returns:
        html.Div containing the complete join configuration UI
    """
    return html.Div([
        # Introduction section
        html.Div([
            html.H5("Join Your Data", style={"marginBottom": "10px", "color": "#133817"}),
            html.P(
                "Automatically combines your garden dataset with maternal tree climate data and garden climate data. "
                "Select the columns you need from each source.",
                style={"color": "#666", "marginBottom": "20px", "fontSize": "0.95em"}
            ),
        ], style={"marginBottom": "25px", "padding": "15px", "backgroundColor": "#f0f7f2", "borderRadius": "8px"}),

        # Step 1: Pick the core table
        html.Div([
            html.H6("Step 1: Select Your Garden Dataset", style={"fontWeight": "bold", "marginBottom": "10px", "color": "#133817"}),
            html.P("Choose the main dataset you want to work with:", style={"color": "#666", "marginBottom": "8px", "fontSize": "0.9em"}),
            dcc.Dropdown(
                id=f"{prefix}-join-core-dropdown",
                options=[{"label": value, "value": key} for key, value in CORE_TABLES.items()],
                placeholder="Select a Garden Dataset..."
            ),
        ], style={"marginBottom": "25px", "padding": "15px", "backgroundColor": "#ffffff", "borderRadius": "8px", "border": "1px solid #e0e0e0"}),

        # Error message for general errors
        html.Div(id=f"{prefix}-join-general-error", style={"color": "red", "marginTop": "10px", "fontWeight": "bold", "textAlign": "center"}),

        # Step 2: Core table columns (in a card)
        html.Div([
            html.Div([
                html.H6("Garden Dataset Columns", style={"fontWeight": "bold", "marginBottom": "5px", "color": "#133817"}),
                html.P("Select the columns you need from the main dataset.", 
                       style={"color": "#666", "fontSize": "0.85em", "marginBottom": "10px"}),
                html.Div([
                    html.Button("Select All", id=f"{prefix}-join-select-all-btn", n_clicks=0, 
                              style={"marginRight": "10px", "fontSize": "0.85em", "padding": "5px 12px", 
                                    "backgroundColor": "#007bff", "color": "white", "border": "none", "borderRadius": "4px", "cursor": "pointer"}),
                    html.Button("Deselect All", id=f"{prefix}-join-deselect-all-btn", n_clicks=0, 
                              style={"fontSize": "0.85em", "padding": "5px 12px", 
                                    "backgroundColor": "#6c757d", "color": "white", "border": "none", "borderRadius": "4px", "cursor": "pointer"}),
                ], style={"marginBottom": "10px"}),
            ]),
            dcc.Checklist(id=f"{prefix}-join-core-table-options", options=[], value=[], inline=False,
                        labelStyle={"display": "block", "marginBottom": "5px", "padding": "3px"},
                        style={"maxHeight": "250px", "overflowY": "auto", "padding": "10px", 
                              "backgroundColor": "#f9f9f9", "borderRadius": "5px"}),
        ], id=f"{prefix}-join-table-columns-container", style={"display": "none", "marginBottom": "20px", 
                                                              "padding": "15px", "backgroundColor": "#ffffff", 
                                                              "borderRadius": "8px", "border": "1px solid #e0e0e0"}),

        # Step 3: Maternal tree table columns (in a card)
        html.Div([
            html.Div([
                html.H6("Maternal Tree Climate Data", style={"fontWeight": "bold", "marginBottom": "5px", "color": "#133817"}),
                html.P("Climate data from the original tree locations. Automatically matched by Accession and Locality.", 
                       style={"color": "#666", "fontSize": "0.85em", "marginBottom": "10px"}),
                html.Div([
                    html.Button("Select All", id=f"{prefix}-join-select-all-btn-2", n_clicks=0, 
                              style={"marginRight": "10px", "fontSize": "0.85em", "padding": "5px 12px", 
                                    "backgroundColor": "#007bff", "color": "white", "border": "none", "borderRadius": "4px", "cursor": "pointer"}),
                    html.Button("Deselect All", id=f"{prefix}-join-deselect-all-btn-2", n_clicks=0, 
                              style={"fontSize": "0.85em", "padding": "5px 12px", 
                                    "backgroundColor": "#6c757d", "color": "white", "border": "none", "borderRadius": "4px", "cursor": "pointer"}),
                ], style={"marginBottom": "10px"}),
            ]),
            dcc.Checklist(id=f"{prefix}-join-tree-table-options", options=[], value=[], inline=False,
                        labelStyle={"display": "block", "marginBottom": "5px", "padding": "3px"},
                        style={"maxHeight": "250px", "overflowY": "auto", "padding": "10px", 
                              "backgroundColor": "#f9f9f9", "borderRadius": "5px"}),
        ], id=f"{prefix}-join-tree-table-columns-container", style={"display": "none", "marginBottom": "20px",
                                                                    "padding": "15px", "backgroundColor": "#ffffff", 
                                                                    "borderRadius": "8px", "border": "1px solid #e0e0e0"}),

        # Step 4: Garden climate variables (in a card)
        html.Div([
            html.Div([
                html.H6("Garden Climate Data", style={"fontWeight": "bold", "marginBottom": "5px", "color": "#133817"}),
                html.P("Monthly climate data from garden sites. Automatically matched by Site (and Year, if available).", 
                       style={"color": "#666", "fontSize": "0.85em", "marginBottom": "10px"}),
                html.Div([
                    html.Button("Select All", id=f"{prefix}-join-select-all-btn-3", n_clicks=0, 
                              style={"marginRight": "10px", "fontSize": "0.85em", "padding": "5px 12px", 
                                    "backgroundColor": "#007bff", "color": "white", "border": "none", "borderRadius": "4px", "cursor": "pointer"}),
                    html.Button("Deselect All", id=f"{prefix}-join-deselect-all-btn-3", n_clicks=0, 
                              style={"fontSize": "0.85em", "padding": "5px 12px", 
                                    "backgroundColor": "#6c757d", "color": "white", "border": "none", "borderRadius": "4px", "cursor": "pointer"}),
                ], style={"marginBottom": "10px"}),
            ]),
            dcc.Checklist(id=f"{prefix}-join-garden-table-options", options=[], value=[], inline=False,
                        labelStyle={"display": "block", "marginBottom": "5px", "padding": "3px"},
                        style={"maxHeight": "250px", "overflowY": "auto", "padding": "10px", 
                              "backgroundColor": "#f9f9f9", "borderRadius": "5px"}),
        ], id=f"{prefix}-join-garden-table-columns-container", style={"display": "none", "marginBottom": "20px",
                                                                     "padding": "15px", "backgroundColor": "#ffffff", 
                                                                     "borderRadius": "8px", "border": "1px solid #e0e0e0"}),

        # Join preview section (shows before execution)
        html.Div([
            html.H6("Join Preview", style={"fontWeight": "bold", "marginBottom": "10px", "color": "#133817"}),
            html.Div(id=f"{prefix}-join-preview", style={"padding": "10px", "backgroundColor": "#f8f9fa", 
                                                           "borderRadius": "5px", "color": "#666", "fontSize": "0.9em"}),
        ], id=f"{prefix}-join-preview-container", style={"display": "none", "marginBottom": "20px",
                                                           "padding": "15px", "backgroundColor": "#ffffff", 
                                                           "borderRadius": "8px", "border": "1px solid #e0e0e0"}),

        # Execute button
        html.Div([
            html.Button(
                "Execute Join & Load Data",
                id=f"{prefix}-join-execute-button",
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
        ], id=f"{prefix}-join-execute-button-div", style={"display": "none", "textAlign": "center", "marginTop": "20px", "marginBottom": "20px"}),
        
        # Error message div
        html.Div([
            html.Div([
                html.Strong("⚠️ Please select at least one data source", style={"color": "#dc3545"}),
                html.P("You need to select at least one column from either Maternal Tree Data or Garden Climate Data to proceed.", 
                       style={"color": "#666", "marginTop": "5px", "marginBottom": "0", "fontSize": "0.9em"})
            ])
        ], id=f"{prefix}-join-execute-error", style={"display": "none", "textAlign": "center", "marginTop": "20px",
                                                       "padding": "15px", "backgroundColor": "#fff3cd", 
                                                       "borderRadius": "8px", "border": "1px solid #ffc107"}),
    ], id=f"{prefix}-join-ui-container", style={"display": "none"})
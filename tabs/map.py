import base64
import io
import logging
import os
import re

import pandas as pd
import plotly.graph_objects as go
from dash import (
    Patch,
    Input,
    Output,
    State,
    callback,
    callback_context,
    dcc,
    html,
    no_update,
)
from dash_ag_grid import AgGrid
from dash.exceptions import PreventUpdate
from dotenv import load_dotenv

from database import fetch_data_from_sql

load_dotenv(override=True)
logger = logging.getLogger(__name__)

map_table = (os.getenv("MAP_TABLE") or "").strip('"')
dat_avail_table = os.getenv("DAT_AVAIL_TABLE")
COMMON_GARDEN_TREE_TABLE = "dat_cgp_db"

SEARCH_ID_COLUMNS = [
    {"label": "Accession", "value": "Accession"},
    {"label": "Sample ID", "value": "sample_id"},
]

OPTIONAL_MAP_COLUMNS = ["Accession", "sample_id", "Year", "Site"]
INDIVIDUAL_TREE_ZOOM_THRESHOLD = 8
MAX_UPLOADED_MAP_ROWS = 10000
MAX_UPLOAD_PREVIEW_ROWS = 8
TREE_MARKER_COLOR = "#d90429"
COMMON_GARDEN_TREE_COLOR = "#0891b2"
DEFAULT_MAP_VIEW = {"center": {"lon": -119.5, "lat": 37.5}, "zoom": 5}

UCLA_COORDINATES = {
    "latitude": 34.0682,
    "longitude": -118.4455,
}

# Known common garden sites (static reference layer, always visible).
# TODO: update lat/lon values to match the actual Sork lab site coordinates.
COMMON_GARDEN_SITES = {
    "Chico": {"latitude": 39.73, "longitude": -121.84},
    "Placerville": {"latitude": 38.73, "longitude": -120.80},
}
COMMON_GARDEN_SITE_ALIASES = {
    "IFG": "Placerville",
}

COORDINATE_ALIASES = {
    "Latitude": ["Latitude", "latitude", "lat", "Lat", "LAT", "Y", "y"],
    "Longitude": ["Longitude", "longitude", "lon", "Lon", "LON", "long", "Long", "lng", "Lng", "X", "x"],
}
SITE_ALIASES = ["locality_full_name", "Site", "site", "Locality", "locality", "Garden", "garden"]


def _sanitize_identifier(name):
    if not name or not re.fullmatch(r"[\w \-()./]+", name):
        raise ValueError(f"Invalid identifier: {name}")
    return name


def _sql_literal(value):
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


_TABLE_COLUMN_CACHE = {}


def get_table_columns(table_name):
    safe_name = _sanitize_identifier(table_name)
    if safe_name in _TABLE_COLUMN_CACHE:
        return _TABLE_COLUMN_CACHE[safe_name]
    df = fetch_data_from_sql(f"SELECT TOP 0 * FROM [dbo].[{safe_name}]")
    if df is None or not len(df.columns):
        return []
    columns = df.columns.tolist()
    _TABLE_COLUMN_CACHE[safe_name] = columns
    return columns


def _map_source_options():
    if not map_table:
        return [{"label": "Tree site records", "value": "__all__"}]
    return [{"label": "Tree site records", "value": map_table}]


def _initial_map_source_options():
    return _map_source_options()


def _default_map_source_value():
    return map_table or "__all__"


def _map_table_name(_selected_source=None):
    return _sanitize_identifier(map_table) if map_table else None


def _safe_fetch(query):
    df = fetch_data_from_sql(query)
    if df is None:
        return pd.DataFrame()
    return df


def _table_has_column(table_name, column_name):
    if not table_name:
        return False
    return column_name in set(get_table_columns(table_name))


def _first_existing(columns, candidates):
    available = set(columns or [])
    return next((column for column in candidates if column in available), None)


def _normalized_site_key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _known_garden_coordinates(site_value):
    canonical_value = COMMON_GARDEN_SITE_ALIASES.get(str(site_value or "").strip(), site_value)
    site_key = _normalized_site_key(canonical_value)
    if not site_key:
        return None
    for garden_name, coords in COMMON_GARDEN_SITES.items():
        garden_key = _normalized_site_key(garden_name)
        if site_key == garden_key or site_key in garden_key or garden_key in site_key:
            return coords
    return None


def _is_known_garden_site(value):
    canonical_value = COMMON_GARDEN_SITE_ALIASES.get(str(value or "").strip(), value)
    site_key = _normalized_site_key(canonical_value)
    if not site_key:
        return False
    return any(site_key == _normalized_site_key(name) for name in COMMON_GARDEN_SITES)


def _column_lookup(table_name):
    return {column.lower(): column for column in get_table_columns(table_name)}


def _resolve_column_name(table_name, column_name):
    if not table_name or not column_name:
        return None
    return _column_lookup(table_name).get(str(column_name).lower())


def _sql_like_literal(value):
    text = str(value).replace("'", "''").replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")
    return f"'%{text}%'"


def _ag_simple_filter_clause(column, filter_def):
    filter_type = filter_def.get("filterType")
    filter_value = filter_def.get("filter")
    filter_to = filter_def.get("filterTo")
    operator_type = filter_def.get("type") or "contains"

    if filter_type == "set":
        values = [value for value in (filter_def.get("values") or []) if value not in (None, "")]
        if not values:
            return None
        return f"[{column}] IN ({', '.join(_sql_literal(value) for value in values)})"

    if operator_type == "blank":
        return f"[{column}] IS NULL"
    if operator_type == "notBlank":
        return f"[{column}] IS NOT NULL"
    if filter_value in (None, ""):
        return None

    if filter_type in {"number", "date"}:
        comparators = {
            "equals": "=",
            "notEqual": "<>",
            "lessThan": "<",
            "lessThanOrEqual": "<=",
            "greaterThan": ">",
            "greaterThanOrEqual": ">=",
        }
        if operator_type == "inRange" and filter_to not in (None, ""):
            return f"[{column}] BETWEEN {_sql_literal(filter_value)} AND {_sql_literal(filter_to)}"
        comparator = comparators.get(operator_type)
        if comparator:
            return f"[{column}] {comparator} {_sql_literal(filter_value)}"
        return None

    if operator_type == "equals":
        return f"CAST([{column}] AS VARCHAR(MAX)) = {_sql_literal(filter_value)}"
    if operator_type == "notEqual":
        return f"CAST([{column}] AS VARCHAR(MAX)) <> {_sql_literal(filter_value)}"
    if operator_type == "startsWith":
        return f"CAST([{column}] AS VARCHAR(MAX)) LIKE {_sql_literal(str(filter_value) + '%')}"
    if operator_type == "endsWith":
        return f"CAST([{column}] AS VARCHAR(MAX)) LIKE {_sql_literal('%' + str(filter_value))}"
    if operator_type == "notContains":
        return f"CAST([{column}] AS VARCHAR(MAX)) NOT LIKE {_sql_like_literal(filter_value)}"
    return f"CAST([{column}] AS VARCHAR(MAX)) LIKE {_sql_like_literal(filter_value)}"


def _ag_filter_clauses(table_name, filter_model):
    if not table_name or not filter_model:
        return []
    clauses = []
    for grid_column, filter_def in (filter_model or {}).items():
        column = _resolve_column_name(table_name, grid_column)
        if not column or not isinstance(filter_def, dict):
            continue
        conditions = filter_def.get("conditions")
        if conditions:
            condition_clauses = [
                _ag_simple_filter_clause(column, condition)
                for condition in conditions
                if isinstance(condition, dict)
            ]
            condition_clauses = [clause for clause in condition_clauses if clause]
            if condition_clauses:
                joiner = " OR " if filter_def.get("operator") == "OR" else " AND "
                clauses.append("(" + joiner.join(condition_clauses) + ")")
            continue
        clause = _ag_simple_filter_clause(column, filter_def)
        if clause:
            clauses.append(clause)
    return clauses


def _build_where_clause(table_name, selected_locations=None, selected_years=None, data_filter_col=None, data_filter_val=None, filter_model=None):
    clauses = ["[Latitude] IS NOT NULL", "[Longitude] IS NOT NULL"]
    if selected_locations:
        values = ", ".join(_sql_literal(value) for value in selected_locations)
        locality_col = _resolve_column_name(table_name, "locality_full_name") or _resolve_column_name(table_name, "Locality_full_name")
        if locality_col:
            clauses.append(f"[{locality_col}] IN ({values})")
    if selected_years and _table_has_column(table_name, "Year"):
        values = ", ".join(_sql_literal(value) for value in selected_years)
        clauses.append(f"[Year] IN ({values})")
    if data_filter_col and data_filter_val is not None and data_filter_val != "" and _table_has_column(table_name, data_filter_col):
        clauses.append(f"[{data_filter_col}] = {_sql_literal(data_filter_val)}")
    clauses.extend(_ag_filter_clauses(table_name, filter_model))
    return " AND ".join(clauses)


def _build_site_aggregate_query(selected_source, selected_locations=None, selected_years=None, data_filter_col=None, data_filter_val=None, filter_model=None):
    table_name = _map_table_name(selected_source)
    if not table_name:
        return None
    locality_col = _resolve_column_name(table_name, "locality_full_name") or _resolve_column_name(table_name, "Locality_full_name")
    if not locality_col:
        return None
    
    where_clause = _build_where_clause(table_name, selected_locations, selected_years, data_filter_col, data_filter_val, filter_model)
    
    # If the table is dat_avail_db and a year filter is applied, we must check db_main
    if table_name == "dat_avail_db" and selected_years and not _table_has_column(table_name, "Year"):
        where_clause_no_year = _build_where_clause(table_name, selected_locations, None, data_filter_col, data_filter_val)
        years_list = ", ".join(_sql_literal(y) for y in selected_years)
        where_clause = f"{where_clause_no_year} AND EXISTS (SELECT 1 FROM [dbo].[db_main] d WHERE d.[Locality] = [dbo].[{table_name}].[Locality] AND d.[Year] IN ({years_list}))"

    return f"""
SELECT
    [{locality_col}] AS [locality_full_name],
    AVG([Longitude]) AS avg_longitude,
    AVG([Latitude]) AS avg_latitude,
    COUNT(*) AS tree_count
FROM [dbo].[{table_name}]
WHERE {where_clause}
GROUP BY [{locality_col}]
"""


def _build_coordinate_query(selected_source, selected_locations=None, selected_years=None, data_filter_col=None, data_filter_val=None, filter_model=None):
    table_name = _map_table_name(selected_source)
    if not table_name:
        return None
    available_columns = set(get_table_columns(table_name))
    locality_col = _resolve_column_name(table_name, "locality_full_name") or _resolve_column_name(table_name, "Locality_full_name")
    if not locality_col:
        return None
    optional_selects = []
    for column_name in OPTIONAL_MAP_COLUMNS:
        if column_name in available_columns:
            optional_selects.append(f"[{column_name}]")
        else:
            optional_selects.append(f"NULL AS [{column_name}]")
            
    where_clause = _build_where_clause(table_name, selected_locations, selected_years, data_filter_col, data_filter_val, filter_model)
    
    # If the table is dat_avail_db and a year filter is applied, we must check db_main
    if table_name == "dat_avail_db" and selected_years and not _table_has_column(table_name, "Year"):
        where_clause_no_year = _build_where_clause(table_name, selected_locations, None, data_filter_col, data_filter_val)
        years_list = ", ".join(_sql_literal(y) for y in selected_years)
        where_clause = f"{where_clause_no_year} AND EXISTS (SELECT 1 FROM [dbo].[db_main] d WHERE d.[Locality] = [dbo].[{table_name}].[Locality] AND d.[Year] IN ({years_list}))"

    return f"""
SELECT
    {_sql_literal(table_name)} AS [source_table],
    [{locality_col}] AS [locality_full_name],
    [Latitude],
    [Longitude],
    {', '.join(optional_selects)}
FROM [dbo].[{table_name}]
WHERE {where_clause}
"""


def _build_location_options_query(selected_source, data_filter_col=None, data_filter_val=None):
    table_name = _map_table_name(selected_source)
    if not table_name:
        return None
    base_where = "[locality_full_name] IS NOT NULL AND [Latitude] IS NOT NULL AND [Longitude] IS NOT NULL"
    if data_filter_col and data_filter_val is not None and data_filter_val != "" and _table_has_column(table_name, data_filter_col):
        base_where += f" AND [{data_filter_col}] = {_sql_literal(data_filter_val)}"
    return f"""
SELECT DISTINCT [locality_full_name]
FROM [dbo].[{table_name}]
WHERE {base_where}
ORDER BY [locality_full_name]
"""


def _build_year_options_query(selected_source, selected_locations=None):
    table_name = _map_table_name(selected_source)
    if not table_name:
        return None
        
    if _table_has_column(table_name, "Year"):
        where_clause = _build_where_clause(table_name, selected_locations=selected_locations)
        return f"""
    SELECT DISTINCT [Year]
    FROM [dbo].[{table_name}]
    WHERE [Year] IS NOT NULL AND {where_clause}
    ORDER BY [Year]
    """
    elif table_name == "dat_avail_db" and _table_has_column("db_main", "Year"):
        where_clause = _build_where_clause(table_name, selected_locations=selected_locations)
        where_clause = where_clause.replace("[Latitude]", "a.[Latitude]").replace("[Longitude]", "a.[Longitude]").replace("[locality_full_name]", "a.[locality_full_name]")
        return f"""
    SELECT DISTINCT d.[Year]
    FROM [dbo].[db_main] d
    JOIN [dbo].[{table_name}] a ON d.[Locality] = a.[Locality]
    WHERE d.[Year] IS NOT NULL AND {where_clause}
    ORDER BY d.[Year]
    """
    return None


def _build_detail_query(source_table, locality_name=None, latitude=None, longitude=None):
    safe_table = _map_table_name(source_table)
    if not safe_table:
        return None
    if locality_name is not None:
        locality_sql = _sql_literal(locality_name)
        return f"SELECT * FROM [dbo].[{safe_table}] WHERE [locality_full_name] = {locality_sql}"
    return (
        f"SELECT * FROM [dbo].[{safe_table}] "
        f"WHERE [Latitude] = {float(latitude)} AND [Longitude] = {float(longitude)}"
    )


def _availability_panel(selected_source):
    table_name = _map_table_name(selected_source)
    availability_table = _sanitize_identifier(dat_avail_table) if dat_avail_table else table_name
    availability_df = pd.DataFrame()
    note = "Use the table filters to choose the data shown on the map."
    if availability_table:
        availability_df = _safe_fetch(f"SELECT TOP 500 * FROM [dbo].[{availability_table}]")
        note = f"Showing up to 500 rows from `{availability_table}`. Table filters update the map."
    if availability_df.empty:
        availability_df = pd.DataFrame([{"Dataset": table_name or "Tree site records", "Rows": "Unavailable"}])

    return html.Div(
        [
            html.H6("Dataset Availability", className="section-title"),
            html.P(note, className="section-copy"),
            _make_grid(availability_df, "map-availability-grid", height=560, page_size=25),
        ],
        className="panel-card map-availability-card",
    )


def _availability_panel_from_upload(selected_source, upload_data=None, selected_locations=None, selected_years=None):
    panel = _availability_panel(selected_source)
    upload_records = (upload_data or {}).get("records") or []
    if not upload_records:
        return panel

    upload_df = pd.DataFrame(upload_records)
    if selected_locations and "locality_full_name" in upload_df.columns:
        upload_df = upload_df[upload_df["locality_full_name"].isin(selected_locations)]
    if selected_years and "Year" in upload_df.columns:
        upload_df = upload_df[upload_df["Year"].astype(str).isin([str(value) for value in selected_years])]

    localities = 0
    if "locality_full_name" in upload_df.columns:
        localities = upload_df["locality_full_name"].dropna().nunique()

    return html.Div(
        [
            panel,
            html.Div(
                [
                    html.H6("Uploaded Trees", className="section-title"),
                    html.P(
                        f"{len(upload_df):,} uploaded tree rows are active in this map view across {localities:,} locations.",
                        className="section-copy",
                    ),
                ],
                className="panel-card panel-card--compact map-availability-upload-card",
            ),
        ]
    )


def _summary_card(title, body, accent="#2d6a4f"):
    return html.Div(
        [
            html.Div(title, className="summary-card-title"),
            html.Div(body, className="summary-card-body"),
        ],
        className="summary-card",
        style={"borderTop": f"4px solid {accent}"},
    )


def _make_table(df, table_id, page_size=10):
    return _make_grid(df, table_id, height=320, page_size=page_size)


def _make_grid(df, grid_id, height=320, page_size=10):
    numeric_columns = set()

    def _column_def(column):
        column_values = df[column].dropna()
        is_numeric = False
        try:
            if pd.api.types.is_numeric_dtype(column_values):
                is_numeric = True
            else:
                sample = column_values.head(50)
                coerced = pd.to_numeric(sample, errors="coerce")
                if len(sample) > 0 and coerced.notna().sum() / float(len(sample)) >= 0.9:
                    is_numeric = True
        except Exception:
            is_numeric = False

        if is_numeric:
            numeric_columns.add(column)

        base_def = {
            "headerName": str(column),
            "field": str(column),
            "sortable": True,
            "resizable": True,
            "minWidth": 150 if column == "Dataset" else 110,
            "flex": 2 if column == "Dataset" else 1,
        }

        if is_numeric:
            base_def["filter"] = "agNumberColumnFilter"
            base_def["filterParams"] = {
                "filterOptions": [
                    "equals",
                    "notEqual",
                    "lessThan",
                    "lessThanOrEqual",
                    "greaterThan",
                    "greaterThanOrEqual",
                ],
                "suppressAndOrCondition": True,
            }
        else:
            base_def["filter"] = "agTextColumnFilter"
            base_def["filterParams"] = {
                "filterOptions": [
                    "contains",
                    "notContains",
                    "equals",
                    "notEqual",
                    "startsWith",
                    "endsWith",
                ],
                "suppressAndOrCondition": True,
            }

        return base_def

    column_defs = [_column_def(column) for column in df.columns]

    row_data = []
    for record in df.to_dict("records"):
        if numeric_columns:
            record = {
                key: (pd.to_numeric(value, errors="coerce") if key in numeric_columns else value)
                for key, value in record.items()
            }
        row_data.append(record)

    return AgGrid(
        id=grid_id,
        rowData=row_data,
        columnDefs=column_defs,
        defaultColDef={"filter": True, "sortable": True, "resizable": True, "wrapText": True, "autoHeight": True},
        dashGridOptions={
            "pagination": True,
            "paginationPageSize": page_size,
            "animateRows": False,
            "domLayout": "normal",
            "suppressCellFocus": True,
        },
        className="ag-theme-alpine compact-grid",
        style={"width": "100%", "height": f"{height}px"},
    )


def _normalize_upload_columns(df):
    rename_map = {}
    canonical = {
        "latitude": "Latitude",
        "lat": "Latitude",
        "y": "Latitude",
        "longitude": "Longitude",
        "lon": "Longitude",
        "long": "Longitude",
        "lng": "Longitude",
        "x": "Longitude",
        "locality": "locality_full_name",
        "locality_full_name": "locality_full_name",
        "site": "Site",
        "accession": "Accession",
        "sample_id": "sample_id",
        "sampleid": "sample_id",
        "year": "Year",
    }
    for column in df.columns:
        key = re.sub(r"[^a-z0-9_]+", "_", str(column).strip().lower()).strip("_")
        if key in canonical:
            rename_map[column] = canonical[key]
    return df.rename(columns=rename_map)


def parse_uploaded_tree_file(contents, filename):
    if not contents:
        return None, "Choose a CSV or TSV file with Latitude and Longitude columns."
    try:
        _, content_string = contents.split(",", 1)
        decoded = base64.b64decode(content_string)
        text = decoded.decode("utf-8-sig")
        separator = "\t" if (filename or "").lower().endswith(".tsv") else ","
        df = pd.read_csv(io.StringIO(text), sep=separator)
    except Exception as exc:
        return None, f"Could not read {filename or 'the uploaded file'}: {exc}"

    if df.empty:
        return None, "The uploaded file has no data rows."

    df = _normalize_upload_columns(df)
    missing = [column for column in ["Latitude", "Longitude"] if column not in df.columns]
    if missing:
        return None, "Uploaded tree lists must include Latitude and Longitude columns."

    df["Latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
    df["Longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")
    df = df.dropna(subset=["Latitude", "Longitude"]).copy()
    if df.empty:
        return None, "No rows had usable numeric Latitude and Longitude values."

    if "locality_full_name" not in df.columns:
        if "Site" in df.columns:
            df["locality_full_name"] = df["Site"].astype(str)
        else:
            df["locality_full_name"] = "Uploaded trees"

    df["source_table"] = "Uploaded tree list"
    if len(df) > MAX_UPLOADED_MAP_ROWS:
        df = df.head(MAX_UPLOADED_MAP_ROWS).copy()

    keep_cols = [
        column
        for column in ["source_table", "locality_full_name", "Latitude", "Longitude", "Accession", "sample_id", "Year", "Site"]
        if column in df.columns
    ]
    extra_cols = [column for column in df.columns if column not in keep_cols]
    return df[keep_cols + extra_cols].to_dict("records"), None


def _records_to_coordinate_frame(records):
    df = pd.DataFrame(records or [])
    if df.empty:
        return df
    for column in ["Latitude", "Longitude"]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df.dropna(subset=["Latitude", "Longitude"])


def _fetch_common_garden_tree_coordinates(selected_locations=None, selected_years=None):
    try:
        columns = get_table_columns(COMMON_GARDEN_TREE_TABLE)
    except Exception:
        return pd.DataFrame()

    lat_col = _first_existing(columns, COORDINATE_ALIASES["Latitude"])
    lon_col = _first_existing(columns, COORDINATE_ALIASES["Longitude"])
    site_col = _first_existing(columns, SITE_ALIASES)
    year_col = "Year" if "Year" in columns else _first_existing(columns, ["year", "YEAR"])
    accession_col = _first_existing(columns, ["Accession", "accession"])
    sample_col = _first_existing(columns, ["sample_id", "Sample_ID", "sampleid", "SampleID"])

    if not site_col and not (lat_col and lon_col):
        return pd.DataFrame()

    selected_cols = []
    for col in [site_col, year_col, lat_col, lon_col, accession_col, sample_col]:
        if col and col not in selected_cols:
            selected_cols.append(col)
    if not selected_cols:
        return pd.DataFrame()

    select_sql = ", ".join(f"[{col}]" for col in selected_cols)
    query = f"SELECT TOP {MAX_UPLOADED_MAP_ROWS} {select_sql} FROM [dbo].[{COMMON_GARDEN_TREE_TABLE}]"
    try:
        df = _safe_fetch(query)
    except Exception:
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()

    result = pd.DataFrame()
    result["source_table"] = COMMON_GARDEN_TREE_TABLE
    if site_col:
        result["locality_full_name"] = df[site_col].astype(str)
        result["Site"] = df[site_col]
    else:
        result["locality_full_name"] = "Common Garden trees"

    if year_col:
        result["Year"] = df[year_col]
    if accession_col:
        result["Accession"] = df[accession_col]
    if sample_col:
        result["sample_id"] = df[sample_col]

    if lat_col and lon_col:
        result["Latitude"] = pd.to_numeric(df[lat_col], errors="coerce")
        result["Longitude"] = pd.to_numeric(df[lon_col], errors="coerce")
    else:
        coords = result["locality_full_name"].map(_known_garden_coordinates)
        result["Latitude"] = coords.map(lambda item: item["latitude"] if item else None)
        result["Longitude"] = coords.map(lambda item: item["longitude"] if item else None)

    result = result.dropna(subset=["Latitude", "Longitude"]).copy()
    if selected_locations and "locality_full_name" in result.columns:
        selected_keys = {_normalized_site_key(value) for value in selected_locations}
        result = result[result["locality_full_name"].map(_normalized_site_key).isin(selected_keys)]
    if selected_years and "Year" in result.columns:
        result = result[result["Year"].astype(str).isin([str(value) for value in selected_years])]
    return result


def _tree_label(row):
    accession = row.get("Accession", "")
    sample_id = row.get("sample_id", "")
    locality = row.get("locality_full_name", "Tree")
    identifier = accession or sample_id
    return f"{locality} ({identifier})" if identifier else str(locality)


def _format_coord(value):
    try:
        return f"{float(value):.5f}"
    except (TypeError, ValueError):
        return "Unknown"


def _tree_hover_text(row, source_label=None):
    label = _tree_label(row)
    source = source_label or row.get("source_table", "")
    lines = [
        f"<b>{label}</b>",
        f"Latitude: {_format_coord(row.get('Latitude'))}",
        f"Longitude: {_format_coord(row.get('Longitude'))}",
    ]
    site = row.get("Site") or row.get("locality_full_name")
    if site:
        lines.append(f"Site/location: {site}")
    if row.get("Year") not in (None, ""):
        lines.append(f"Year: {row.get('Year')}")
    if row.get("Accession") not in (None, ""):
        lines.append(f"Accession: {row.get('Accession')}")
    if row.get("sample_id") not in (None, ""):
        lines.append(f"Sample ID: {row.get('sample_id')}")
    if source:
        lines.append(str(source))
    return "<br>".join(lines)


def _search_identifier_variants(values, id_type):
    variants = []
    seen = set()
    for value in values:
        text = str(value).strip()
        candidates = [text]
        if id_type == "Accession" and text.isdigit():
            candidates.append(text.rstrip("0") or "0")
            if len(text) == 3:
                candidates.append(f"{text}0")
        for candidate in candidates:
            if candidate and candidate not in seen:
                seen.add(candidate)
                variants.append(candidate)
    return variants


def _viewport_from_relayout(relayout_data, current_view=None):
    if not relayout_data:
        return current_view or DEFAULT_MAP_VIEW
    next_view = dict(current_view or DEFAULT_MAP_VIEW)
    center = dict(next_view.get("center") or DEFAULT_MAP_VIEW["center"])
    if "mapbox.center" in relayout_data and isinstance(relayout_data["mapbox.center"], dict):
        relayout_center = relayout_data["mapbox.center"]
        if "lon" in relayout_center and "lat" in relayout_center:
            center = {"lon": relayout_center["lon"], "lat": relayout_center["lat"]}
    if "mapbox.center.lon" in relayout_data:
        center["lon"] = relayout_data["mapbox.center.lon"]
    if "mapbox.center.lat" in relayout_data:
        center["lat"] = relayout_data["mapbox.center.lat"]
    next_view["center"] = center
    if "mapbox.zoom" in relayout_data:
        next_view["zoom"] = relayout_data["mapbox.zoom"]
    return next_view


map_layout = dcc.Tab(
    id="maps-tab",
    value="map-tab",
    label="Tree Sites",
    style={"padding": "15px"},
    children=[
        dcc.Store(id="stored-click-data", data=None, storage_type="session"),
        dcc.Store(id="click-result-store", data=None),
        dcc.Store(id="search-result-store", data=None),
        dcc.Store(id="uploaded-tree-store", data=None, storage_type="session"),
        dcc.Store(id="map-coordinate-store", data=None),
        dcc.Store(id="map-selected-coordinate-store", data=None),
        dcc.Store(id="map-viewport-store", data=DEFAULT_MAP_VIEW, storage_type="session"),
        dcc.Download(id="click-download-csv"),
        dcc.Download(id="search-download-csv"),
        dcc.Download(id="map-download-coordinates"),
        html.Div(
            [
                html.Div(
                    [
                        html.Div(
                            [
                                html.H4("Tree Sites", className="page-title"),
                                html.P(
                                    "Browse all mapped tree datasets, inspect common gardens, and zoom into individual trees only when detail is needed.",
                                    className="page-intro",
                                ),
                            ],
                            className="page-header-block",
                        ),
                        html.Div(
                            [
                                html.H6("Map Controls", className="section-title"),
                                dcc.Dropdown(
                                    id="map-source-dropdown",
                                    options=_initial_map_source_options(),
                                    value=_default_map_source_value(),
                                    clearable=False,
                                    style={"display": "none"},
                                ),
                                html.Label("Locations", className="control-label"),
                                dcc.Dropdown(
                                    id="map-location-filter",
                                    options=[],
                                    value=[],
                                    multi=True,
                                    placeholder="All mapped locations",
                                    persistence=True,
                                    persistence_type="session",
                                ),
                                dcc.Dropdown(
                                    id="map-year-filter",
                                    options=[],
                                    value=[],
                                    multi=True,
                                    placeholder="All years",
                                    style={"display": "none"},
                                ),
                                dcc.Dropdown(
                                    id="map-data-filter-col",
                                    options=[],
                                    value=None,
                                    clearable=True,
                                    style={"display": "none"},
                                ),
                                dcc.Dropdown(
                                    id="map-data-filter-val",
                                    options=[],
                                    value=None,
                                    clearable=True,
                                    style={"display": "none"},
                                ),
                                html.Div(
                                    f"Known garden sites are shown as teal reference markers. Green circles = data sites, gold = UCLA, red = individual trees (zoom {INDIVIDUAL_TREE_ZOOM_THRESHOLD}+), blue = uploaded, purple = search hits.",
                                    className="info-banner",
                                ),
                                html.Div(
                                    [
                                        html.Button("Reset View", id="reset-map", className="btn btn-success btn-sm"),
                                    ],
                                    className="button-row",
                                ),
                            ],
                            className="panel-card",
                        ),
                        html.Div(
                            [
                                html.H6("Upload Tree List", className="section-title"),
                                html.P(
                                    "Upload CSV or TSV rows with Latitude and Longitude to add a temporary tree layer to the map.",
                                    className="section-copy",
                                ),
                                dcc.Upload(
                                    id="map-tree-upload",
                                    children=html.Div(["Drop a tree list here or select a file"]),
                                    className="upload-dropzone",
                                    multiple=False,
                                ),
                                html.Div(
                                    [
                                        html.Button("Clear Upload", id="clear-map-upload-btn", n_clicks=0, className="btn btn-outline-secondary btn-sm"),
                                    ],
                                    className="button-row",
                                ),
                                html.Div(id="map-upload-status"),
                            ],
                            className="panel-card map-tool-card",
                        ),
                        html.Div(
                            [
                                html.H6("Find Trees", className="section-title"),
                                html.P(
                                    "Paste known Accessions or sample IDs. Results appear as purple points and in the results panel.",
                                    className="section-copy",
                                ),
                                html.Label("Identifier type", className="control-label"),
                                dcc.RadioItems(
                                    id="search-id-type",
                                    options=SEARCH_ID_COLUMNS,
                                    value=SEARCH_ID_COLUMNS[0]["value"],
                                    inline=True,
                                    persistence=True,
                                    persistence_type="session",
                                ),
                                dcc.Textarea(
                                    id="search-ids-input",
                                    placeholder="Enter multiple IDs:\n1, 5, 10, 432\n\nOr one per line:\n1\n5\n10\n432",
                                    style={
                                        "width": "100%",
                                        "height": "90px",
                                        "borderRadius": "10px",
                                        "padding": "10px",
                                        "border": "1px solid #c9d7c8",
                                    },
                                    persistence=True,
                                    persistence_type="session",
                                ),
                                html.Div(
                                    [
                                        html.Button("Search", id="search-trees-btn", n_clicks=0, className="btn btn-success"),
                                        html.Button("Clear", id="clear-search-btn", n_clicks=0, className="btn btn-outline-secondary"),
                                    ],
                                    className="button-row",
                                ),
                                dcc.Loading(
                                    id="search-loading",
                                    type="default",
                                    children=html.Div(id="search-status-indicator", style={"minHeight": "20px"}),
                                ),
                            ],
                            className="panel-card map-tool-card",
                        ),
                    ],
                    className="map-sidebar",
                ),
                html.Div(
                    [
                        html.Div(
                            [
                                _summary_card("Data Sites", "Clustered from dataset", "#2d6a4f"),
                                _summary_card("Known Gardens", "Reference sites (always visible)", "#0d9488"),
                                _summary_card("UCLA", "Always highlighted", "#e0a800"),
                                _summary_card("Individual Trees", f"Shown from zoom {INDIVIDUAL_TREE_ZOOM_THRESHOLD}", TREE_MARKER_COLOR),
                                _summary_card("Uploaded Trees", "Added from tree lists", "#0d6efd"),
                            ],
                            className="summary-grid",
                        ),
                        html.Div(
                            [
                                dcc.Graph(
                                    id="california-map",
                                    className="map-graph",
                                    config={
                                        "scrollZoom": True,
                                        "displayModeBar": True,
                                        "modeBarButtonsToRemove": ["lasso2d"],
                                    },
                                ),
                                html.Div(
                                    id="map-availability-panel",
                                    className="map-availability-strip",
                                    children=_make_grid(
                                        pd.DataFrame(columns=["Dataset", "Rows"]),
                                        "map-availability-grid",
                                        height=560,
                                        page_size=25,
                                    ),
                                ),
                            ],
                            className="map-and-availability",
                        ),
                        html.Div(
                            "Warning: detailed tree rendering and large search exports may take a while for broad location selections.",
                            className="warning-banner",
                        ),
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.Div(
                                            [
                                                html.H6("Selected Site & Coordinates", className="section-title"),
                                                html.Button(
                                                    "Clear Selection",
                                                    id="clear-map-selection-btn",
                                                    n_clicks=0,
                                                    className="btn btn-outline-secondary btn-sm",
                                                ),
                                            ],
                                            className="selection-download-header",
                                        ),
                                        html.Div(id="individual-tree-data", className="selection-inspection-area"),
                                        html.Div(
                                            [
                                                html.Div(id="map-coordinate-selection-status", className="coordinate-selection-status"),
                                                html.Div(
                                                    [
                                                        html.Button(
                                                            "Download Coordinates",
                                                            id="download-map-coordinates-btn",
                                                            className="btn btn-success btn-sm",
                                                        ),
                                                    ],
                                                    className="button-row coordinate-download-actions",
                                                ),
                                            ],
                                            className="coordinate-download-section",
                                        ),
                                    ],
                                    className="panel-card selection-download-card",
                                ),
                                dcc.Loading(
                                    id="search-results-loading",
                                    type="default",
                                    children=html.Div(id="search-results-data"),
                                ),
                            ],
                            className="map-results-stack",
                        ),
                    ],
                    className="map-main",
                ),
            ],
            className="map-workspace",
        ),
    ],
)


@callback(
    [
        Output("map-source-dropdown", "value", allow_duplicate=True),
        Output("map-location-filter", "value", allow_duplicate=True),
        Output("map-year-filter", "value", allow_duplicate=True),
        Output("map-data-filter-col", "value", allow_duplicate=True),
        Output("map-data-filter-val", "value", allow_duplicate=True),
        Output("search-id-type", "value", allow_duplicate=True),
        Output("search-ids-input", "value", allow_duplicate=True),
        Output("stored-click-data", "data", allow_duplicate=True),
        Output("click-result-store", "data", allow_duplicate=True),
        Output("search-result-store", "data", allow_duplicate=True),
        Output("uploaded-tree-store", "data", allow_duplicate=True),
        Output("map-coordinate-store", "data", allow_duplicate=True),
        Output("map-selected-coordinate-store", "data", allow_duplicate=True),
        Output("map-viewport-store", "data", allow_duplicate=True),
        Output("map-upload-status", "children", allow_duplicate=True),
        Output("search-results-data", "children", allow_duplicate=True),
        Output("individual-tree-data", "children", allow_duplicate=True),
        Output("map-tree-upload", "contents", allow_duplicate=True),
        Output("map-tree-upload", "filename", allow_duplicate=True),
    ],
    [Input("main-tabs", "value"), Input("reset-map", "n_clicks")],
    prevent_initial_call=True,
)
def reset_tree_sites_state(active_tab, reset_clicks):
    trigger_id = callback_context.triggered[0]["prop_id"].split(".")[0] if callback_context.triggered else None
    if trigger_id == "main-tabs" and active_tab == "map-tab":
        raise PreventUpdate
    return (
        _default_map_source_value(),
        [],
        [],
        None,
        None,
        SEARCH_ID_COLUMNS[0]["value"],
        "",
        None,
        None,
        None,
        None,
        None,
        None,
        DEFAULT_MAP_VIEW,
        html.Div(),
        html.Div(),
        html.Div("Select a site or individual tree to inspect details.", className="placeholder-card"),
        None,
        None,
    )


@callback(
    Output("map-source-dropdown", "options"),
    Input("map-source-dropdown", "id"),
)
def hydrate_map_source_options(_dropdown_id):
    return _map_source_options()


@callback(
    [
        Output("california-map", "figure"),
        Output("stored-click-data", "data"),
        Output("map-coordinate-store", "data"),
    ],
    [
        Input("reset-map", "n_clicks"),
        Input("map-source-dropdown", "value"),
        Input("map-location-filter", "value"),
        Input("map-year-filter", "value"),
        Input("uploaded-tree-store", "data"),
        Input("california-map", "clickData"),
        Input("map-data-filter-col", "value"),
        Input("map-data-filter-val", "value"),
        Input("map-availability-grid", "filterModel"),
    ],
    State("map-viewport-store", "data"),
)
def update_map_and_click_data(reset_clicks, selected_source, selected_locations, selected_years, upload_data, click_data, data_filter_col, data_filter_val, availability_filter_model, viewport):
    trigger_id = callback_context.triggered[0]["prop_id"].split(".")[0] if callback_context.triggered else None

    if trigger_id == "california-map":
        return no_update, click_data, no_update

    fig = go.Figure()
    active_view = DEFAULT_MAP_VIEW if trigger_id == "reset-map" else (viewport or DEFAULT_MAP_VIEW)
    aggregate_query = _build_site_aggregate_query(selected_source, selected_locations, selected_years, data_filter_col, data_filter_val, availability_filter_model)
    try:
        locations_df = _safe_fetch(aggregate_query) if aggregate_query else pd.DataFrame()
    except Exception:
        locations_df = pd.DataFrame()

    if locations_df is None:
        locations_df = pd.DataFrame()

    coordinate_records = []
    coordinates_df = pd.DataFrame()
    coordinate_query = _build_coordinate_query(selected_source, selected_locations, selected_years, data_filter_col, data_filter_val, availability_filter_model)
    if coordinate_query:
        try:
            coordinates_df = _safe_fetch(coordinate_query)
            if coordinates_df is not None and not coordinates_df.empty:
                coordinate_records.extend(coordinates_df.to_dict("records"))
        except Exception:
            coordinates_df = pd.DataFrame()

    if not locations_df.empty:
        def _site_marker_size(count):
            try:
                value = float(count)
            except (TypeError, ValueError):
                return 16
            size = 12 + (value ** 0.5) * 3
            return min(max(size, 12), 36)

        sizes = [_site_marker_size(count) for count in locations_df["tree_count"].tolist()]
        fig.add_trace(
            go.Scattermapbox(
                mode="markers",
                lon=locations_df["avg_longitude"].tolist(),
                lat=locations_df["avg_latitude"].tolist(),
                marker={"size": sizes, "color": "#0b6b3a", "opacity": 0.92},
                hovertext=[
                    f"<b>{row['locality_full_name']}</b><br>{row['tree_count']} tree records<br>Latitude: {_format_coord(row['avg_latitude'])}<br>Longitude: {_format_coord(row['avg_longitude'])}"
                    for _, row in locations_df.iterrows()
                ],
                hoverinfo="text",
                customdata=[[map_table, row["locality_full_name"]] for _, row in locations_df.iterrows()],
                name="Data Sites",
            )
        )
    else:
        fig.add_trace(go.Scattermapbox(mode="markers", lon=[], lat=[], name="Data Sites"))

    fig.add_trace(
        go.Scattermapbox(
            mode="markers",
            lon=[UCLA_COORDINATES["longitude"]],
            lat=[UCLA_COORDINATES["latitude"]],
            marker={"size": 24, "color": "#f2b705", "opacity": 0.98},
            hovertext=["University of California, Los Angeles (UCLA)"],
            hoverinfo="text",
            name="UCLA",
        )
    )
    # Static common garden reference layer (trace index 2 — always visible)
    garden_lons = [v["longitude"] for v in COMMON_GARDEN_SITES.values()]
    garden_lats = [v["latitude"] for v in COMMON_GARDEN_SITES.values()]
    garden_names = list(COMMON_GARDEN_SITES.keys())
    fig.add_trace(
        go.Scattermapbox(
            mode="markers",
            lon=garden_lons,
            lat=garden_lats,
            marker={"size": 18, "color": "#0d9488", "opacity": 0.98, "symbol": "circle"},
            hovertext=[
                f"<b>{name}</b><br>Known garden site<br>Latitude: {_format_coord(COMMON_GARDEN_SITES[name]['latitude'])}<br>Longitude: {_format_coord(COMMON_GARDEN_SITES[name]['longitude'])}"
                for name in garden_names
            ],
            hoverinfo="text",
            customdata=[[name] for name in garden_names],
            name="Known Garden Sites",
        )
    )
    show_tree_layer = active_view.get("zoom", DEFAULT_MAP_VIEW["zoom"]) >= INDIVIDUAL_TREE_ZOOM_THRESHOLD
    tree_layer_df = pd.DataFrame()
    if show_tree_layer and coordinates_df is not None and not coordinates_df.empty:
        tree_layer_df = coordinates_df.dropna(subset=["Latitude", "Longitude"]).head(5000)

    fig.add_trace(
        go.Scattermapbox(
            mode="markers",
            lon=tree_layer_df["Longitude"].tolist() if not tree_layer_df.empty else [],
            lat=tree_layer_df["Latitude"].tolist() if not tree_layer_df.empty else [],
            marker={"size": 15, "color": TREE_MARKER_COLOR, "opacity": 0.97},
            hoverinfo="text",
            hovertext=[
                _tree_hover_text(row)
                for _, row in tree_layer_df.iterrows()
            ] if not tree_layer_df.empty else [],
            customdata=tree_layer_df[["source_table", "Latitude", "Longitude", "locality_full_name"]].values.tolist()
            if not tree_layer_df.empty
            else [],
            name="Individual Trees",
        )
    )
    fig.add_trace(
        go.Scattermapbox(
            mode="markers",
            lon=[],
            lat=[],
            marker={"size": 19, "color": "#6d28d9", "opacity": 0.96, "symbol": "circle"},
            hoverinfo="text",
            hovertext=[],
            name="Search Results",
        )
    )
    uploaded_df = _records_to_coordinate_frame((upload_data or {}).get("records"))
    if not uploaded_df.empty and selected_locations and "locality_full_name" in uploaded_df.columns:
        uploaded_df = uploaded_df[uploaded_df["locality_full_name"].isin(selected_locations)]
    if not uploaded_df.empty and selected_years and "Year" in uploaded_df.columns:
        uploaded_df = uploaded_df[uploaded_df["Year"].astype(str).isin([str(value) for value in selected_years])]
    if not uploaded_df.empty:
        coordinate_records.extend(uploaded_df.to_dict("records"))
        fig.add_trace(
            go.Scattermapbox(
                mode="markers",
                lon=uploaded_df["Longitude"].tolist(),
                lat=uploaded_df["Latitude"].tolist(),
                marker={"size": 16, "color": "#0066ff", "opacity": 0.94},
                hovertext=[
                    _tree_hover_text(row, "Uploaded tree list")
                    for _, row in uploaded_df.iterrows()
                ],
                hoverinfo="text",
                customdata=[
                    ["Uploaded tree list", row.get("Latitude"), row.get("Longitude"), row.get("locality_full_name", "Uploaded trees")]
                    for _, row in uploaded_df.iterrows()
                ],
                name="Uploaded Trees",
            )
        )
    else:
        fig.add_trace(
            go.Scattermapbox(
                mode="markers",
                lon=[],
                lat=[],
                marker={"size": 16, "color": "#0066ff", "opacity": 0.94},
                hoverinfo="text",
                hovertext=[],
                name="Uploaded Trees",
            )
        )

    common_garden_tree_df = _fetch_common_garden_tree_coordinates(selected_locations, selected_years)
    if not common_garden_tree_df.empty:
        coordinate_records.extend(common_garden_tree_df.to_dict("records"))
    fig.add_trace(
        go.Scattermapbox(
            mode="markers",
            lon=common_garden_tree_df["Longitude"].tolist() if not common_garden_tree_df.empty else [],
            lat=common_garden_tree_df["Latitude"].tolist() if not common_garden_tree_df.empty else [],
            marker={"size": 13, "color": COMMON_GARDEN_TREE_COLOR, "opacity": 0.88, "symbol": "square"},
            hovertext=[
                _tree_hover_text(row, "Common Garden data")
                for _, row in common_garden_tree_df.iterrows()
            ] if not common_garden_tree_df.empty else [],
            hoverinfo="text",
            customdata=[
                [COMMON_GARDEN_TREE_TABLE, row.get("Latitude"), row.get("Longitude"), row.get("locality_full_name", "Common Garden tree")]
                for _, row in common_garden_tree_df.iterrows()
            ] if not common_garden_tree_df.empty else [],
            name="Common Garden Trees",
            showlegend=False,
        )
    )

    fig.update_layout(
        mapbox={
            "style": "open-street-map",
            "center": active_view.get("center", DEFAULT_MAP_VIEW["center"]),
            "zoom": active_view.get("zoom", DEFAULT_MAP_VIEW["zoom"]),
        },
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        height=700,
        paper_bgcolor="#eef4ec",
        plot_bgcolor="#eef4ec",
        legend={"orientation": "h", "y": 1.02, "x": 0},
        uirevision="tree-sites-map",
        hovermode="closest",
    )
    return fig, None, coordinate_records


@callback(
    Output("map-viewport-store", "data"),
    [Input("california-map", "relayoutData"), Input("reset-map", "n_clicks")],
    State("map-viewport-store", "data"),
    prevent_initial_call=True,
)
def persist_map_viewport(relayout_data, reset_clicks, current_view):
    trigger_id = callback_context.triggered[0]["prop_id"].split(".")[0] if callback_context.triggered else None
    if trigger_id == "reset-map":
        return DEFAULT_MAP_VIEW
    return _viewport_from_relayout(relayout_data, current_view)


@callback(
    [Output("map-location-filter", "options"), Output("map-location-filter", "value")],
    [Input("map-source-dropdown", "value"), Input("uploaded-tree-store", "data")],
    State("map-location-filter", "value"),
)
def update_location_filter_options(selected_source, upload_data, current_values):
    options_by_value = {}
    query = _build_location_options_query(selected_source)
    if query:
        try:
            df = _safe_fetch(query)
            if df is not None and not df.empty and "locality_full_name" in df.columns:
                for value in df["locality_full_name"].dropna().tolist():
                    options_by_value[str(value)] = {"label": str(value), "value": value}
        except Exception:
            pass

    upload_df = pd.DataFrame((upload_data or {}).get("records") or [])
    if not upload_df.empty and "locality_full_name" in upload_df.columns:
        for value in upload_df["locality_full_name"].dropna().unique().tolist():
            options_by_value[str(value)] = {"label": f"{value} (uploaded)", "value": value}

    common_garden_df = _fetch_common_garden_tree_coordinates()
    if not common_garden_df.empty and "locality_full_name" in common_garden_df.columns:
        for value in common_garden_df["locality_full_name"].dropna().unique().tolist():
            if _is_known_garden_site(value):
                options_by_value[str(value)] = {"label": f"{value} (common garden)", "value": value}

    options = list(options_by_value.values())
    valid_values = {option["value"] for option in options}
    selected = [value for value in (current_values or []) if value in valid_values]
    return options, selected


@callback(
    [Output("map-year-filter", "options"), Output("map-year-filter", "value")],
    [Input("map-source-dropdown", "value"), Input("map-location-filter", "value"), Input("uploaded-tree-store", "data")],
    State("map-year-filter", "value"),
)
def update_year_filter_options(selected_source, selected_locations, upload_data, current_values):
    options_by_value = {}
    query = _build_year_options_query(selected_source, selected_locations)
    if query:
        try:
            df = _safe_fetch(query)
            if df is not None and not df.empty and "Year" in df.columns:
                for value in df["Year"].dropna().tolist():
                    label = str(int(value)) if isinstance(value, (int, float)) and float(value) == int(value) else str(value)
                    options_by_value[str(value)] = {"label": label, "value": value}
        except Exception:
            pass

    upload_df = pd.DataFrame((upload_data or {}).get("records") or [])
    if not upload_df.empty and "Year" in upload_df.columns:
        if selected_locations and "locality_full_name" in upload_df.columns:
            upload_df = upload_df[upload_df["locality_full_name"].astype(str).isin([str(v) for v in selected_locations])]
        for value in upload_df["Year"].dropna().unique().tolist():
            options_by_value[str(value)] = {"label": f"{value} (uploaded)", "value": value}

    common_garden_df = _fetch_common_garden_tree_coordinates(selected_locations=selected_locations)
    if not common_garden_df.empty and "Year" in common_garden_df.columns:
        for value in common_garden_df["Year"].dropna().unique().tolist():
            options_by_value[str(value)] = {"label": f"{value} (common garden)", "value": value}

    options = list(options_by_value.values())
    valid_keys = set(options_by_value.keys())
    selected = [value for value in (current_values or []) if str(value) in valid_keys]
    return options, selected


@callback(
    Output("map-data-filter-col", "options"),
    Input("map-source-dropdown", "value"),
)
def update_data_filter_columns(selected_source):
    """Populate the data-availability filter column dropdown from the map table."""
    table_name = _map_table_name(selected_source)
    if not table_name:
        return []
    try:
        cols = get_table_columns(table_name)
        # Exclude coordinate / name columns that aren’t useful as filters
        skip = {"Latitude", "Longitude", "locality_full_name"}
        return [{"label": c, "value": c} for c in cols if c not in skip]
    except Exception:
        return []


@callback(
    [Output("map-data-filter-val", "options"), Output("map-data-filter-val", "value")],
    [Input("map-source-dropdown", "value"), Input("map-data-filter-col", "value")],
    prevent_initial_call=True,
)
def update_data_filter_values(selected_source, filter_col):
    """Populate the value dropdown with distinct values for the selected filter column."""
    if not filter_col:
        return [], None
    table_name = _map_table_name(selected_source)
    if not table_name:
        return [], None
    try:
        query = f"""
        SELECT DISTINCT TOP 200 [{filter_col}]
        FROM [dbo].[{table_name}]
        WHERE [{filter_col}] IS NOT NULL
        ORDER BY [{filter_col}]
        """
        df = _safe_fetch(query)
        if df is None or df.empty:
            return [], None
        values = df.iloc[:, 0].tolist()
        options = [{"label": str(v), "value": v} for v in values]
        return options, None
    except Exception:
        return [], None

@callback(
    Output("map-availability-panel", "children"),
    [
        Input("map-source-dropdown", "value"),
        Input("uploaded-tree-store", "data"),
        Input("map-location-filter", "value"),
        Input("map-year-filter", "value"),
    ],
)
def update_availability_panel(selected_source, upload_data, selected_locations, selected_years):
    try:
        return _availability_panel_from_upload(selected_source or "__all__", upload_data, selected_locations, selected_years)
    except Exception:
        return html.Div(
            [
                html.H6("Dataset Availability", className="section-title"),
                html.P("Availability details are unavailable right now, but the map can still show uploaded tree lists.", className="section-copy"),
            ],
            className="status-warning",
        )


@callback(
    [
        Output("uploaded-tree-store", "data"),
        Output("map-upload-status", "children"),
        Output("map-tree-upload", "contents", allow_duplicate=True),
        Output("map-tree-upload", "filename", allow_duplicate=True),
    ],
    [Input("map-tree-upload", "contents"), Input("clear-map-upload-btn", "n_clicks")],
    State("map-tree-upload", "filename"),
    prevent_initial_call=True,
)
def handle_map_tree_upload(contents, clear_clicks, filename):
    trigger = callback_context.triggered[0]["prop_id"].split(".")[0] if callback_context.triggered else None
    if trigger == "clear-map-upload-btn":
        return None, html.Div("Uploaded tree list cleared.", className="placeholder-card"), None, None

    records, error = parse_uploaded_tree_file(contents, filename)
    if error:
        return no_update, html.Div(error, className="warning-banner"), no_update, no_update

    df = pd.DataFrame(records)
    preview = _make_table(df.head(MAX_UPLOAD_PREVIEW_ROWS), "map-upload-preview-table", page_size=MAX_UPLOAD_PREVIEW_ROWS)
    return (
        {"records": records, "filename": filename or "uploaded_trees.csv"},
        html.Div(
            [
                _summary_card("Uploaded", f"{len(records):,} plotted tree rows", "#0d6efd"),
                html.Details([html.Summary("Preview uploaded rows"), preview], className="details-panel"),
            ],
            className="panel-card panel-card--compact",
        ),
        no_update,
        no_update,
    )


@callback(
    [
        Output("individual-tree-data", "children"),
        Output("click-result-store", "data"),
        Output("map-selected-coordinate-store", "data"),
    ],
    Input("stored-click-data", "data"),
)
def display_click_data(click_data):
    if not click_data or "points" not in click_data or not click_data["points"]:
        return html.Div(
            [
                html.Div("No site selected", className="selection-card-title"),
                html.Div("Select a site or tree on the map to inspect details. Coordinate download will include all active map coordinates until a selection is made.", className="selection-card-copy"),
            ],
            className="selection-empty-state",
        ), None, None

    try:
        point = click_data["points"][0]
        curve = point.get("curveNumber", 0)
        customdata = point.get("customdata") or []

        if curve == 1:
            return html.Div(
                [
                    _summary_card("UCLA", "University of California, Los Angeles", "#f2b705"),
                    html.P("UCLA is shown as a fixed reference point on the map.", className="section-copy"),
                ],
                className="selection-inspection-content",
            ), None, None

        if curve == 2:
            # Known Garden Sites static layer — no DB query needed
            site_name = (customdata or [None])[0] if customdata else None
            display_name = str(site_name) if site_name else "Known common garden site"
            coords = COMMON_GARDEN_SITES.get(display_name)
            selected = None
            if coords:
                selected = {
                    "records": [
                        {
                            "source_table": "Known Garden Sites",
                            "locality_full_name": display_name,
                            "Site": display_name,
                            "Latitude": coords["latitude"],
                            "Longitude": coords["longitude"],
                        }
                    ],
                    "filename": f"known_garden_{display_name.replace(' ', '_')}_coordinates.csv",
                    "label": display_name,
                    "kind": "Known garden site",
                }
            return html.Div(
                [
                    _summary_card("Common Garden Site", display_name, "#0d9488"),
                    html.P(
                        "This known common garden reference site is selected for coordinate download.",
                        className="section-copy",
                    ),
                ],
                className="selection-inspection-content",
            ), None, selected

        if curve == 6:
            source_table, latitude, longitude, locality_name = customdata
            selected = {
                "records": [
                    {
                        "source_table": source_table,
                        "locality_full_name": locality_name,
                        "Latitude": latitude,
                        "Longitude": longitude,
                    }
                ],
                "filename": f"{str(locality_name).replace(' ', '_')}_common_garden_coordinate.csv",
                "label": locality_name,
                "kind": "Common Garden data point",
            }
            return html.Div(
                [
                    _summary_card("Common Garden Tree", locality_name, COMMON_GARDEN_TREE_COLOR),
                    html.P(
                        "This Common Garden data point is selected for coordinate download.",
                        className="section-copy",
                    ),
                ],
                className="selection-inspection-content",
            ), None, selected

        if curve in (3, 5):  # Individual Trees (3) or Uploaded Trees (5)
            source_table, latitude, longitude, locality_name = customdata
            if source_table == "Uploaded tree list":
                selected = {
                    "records": [
                        {
                            "source_table": source_table,
                            "locality_full_name": locality_name,
                            "Latitude": latitude,
                            "Longitude": longitude,
                        }
                    ],
                    "filename": f"{str(locality_name).replace(' ', '_')}_uploaded_coordinate.csv",
                    "label": locality_name,
                    "kind": "Uploaded tree",
                }
                return html.Div(
                    [
                        _summary_card("Uploaded Tree", locality_name, "#0d6efd"),
                        html.P("This uploaded tree is selected for coordinate download.", className="section-copy"),
                    ],
                    className="selection-inspection-content",
                ), None, selected
            detail_query = _build_detail_query(source_table, latitude=latitude, longitude=longitude)
            df = _safe_fetch(detail_query) if detail_query else pd.DataFrame()
            header_text = f"{locality_name} tree record"
            summary = f"Source dataset: {source_table}"
            filename = f"{source_table}_tree_record.csv"
        else:
            source_table, locality_name = customdata
            detail_query = _build_detail_query(source_table, locality_name=locality_name)
            df = _safe_fetch(detail_query) if detail_query else pd.DataFrame()
            header_text = locality_name
            summary = f"{len(df):,} tree rows in {source_table}" if df is not None else source_table
            filename = f"{source_table}_{str(locality_name).replace(' ', '_')}.csv"

        if df is None or df.empty:
            return html.Div("No data available for this selection.", className="selection-empty-state"), None, None

        store_data = {"records": df.to_dict("records"), "filename": filename}
        selected_data = {
            "records": df.to_dict("records"),
            "filename": filename,
            "label": header_text,
            "kind": "Selected site" if curve not in (3, 5, 6) else "Selected tree",
        }
        return (
            html.Div(
                [
                    _summary_card("Selected Site", header_text, "#1d3557"),
                    _summary_card("Details", summary, "#2d6a4f"),
                    html.P("Use the Coordinate Download card to export this selection, or clear it to download all active map coordinates.", className="section-copy"),
                    html.Details(
                        [
                            html.Summary("View raw rows"),
                            _make_table(df, "tree-data-table"),
                        ],
                        className="details-panel",
                    ),
                ],
                className="selection-inspection-content",
            ),
            store_data,
            selected_data,
        )
    except Exception:
        return html.Div("Details are unavailable for this selection.", className="selection-empty-state"), None, None


@callback(
    Output("california-map", "figure", allow_duplicate=True),
    Input("california-map", "relayoutData"),
    [
        State("map-source-dropdown", "value"),
        State("map-location-filter", "value"),
        State("map-year-filter", "value"),
        State("map-data-filter-col", "value"),
        State("map-data-filter-val", "value"),
        State("map-availability-grid", "filterModel"),
    ],
    prevent_initial_call=True,
)
def toggle_individual_trees(relayout_data, selected_source, selected_locations, selected_years, data_filter_col, data_filter_val, availability_filter_model):
    if not relayout_data:
        return no_update

    zoom = relayout_data.get("mapbox.zoom")
    lon_range = relayout_data.get("mapbox._derived", {}).get("coordinates")
    if zoom is None:
        return no_update

    patched_fig = Patch()

    if zoom >= INDIVIDUAL_TREE_ZOOM_THRESHOLD:
        tree_query = _build_coordinate_query(selected_source, selected_locations, selected_years, data_filter_col, data_filter_val, availability_filter_model)
        if not tree_query:
            return no_update
        tree_query = f"""
SELECT TOP 5000
    source_table,
    Latitude,
    Longitude,
    locality_full_name,
    Accession,
    sample_id
FROM (
    {tree_query}
) q
"""
        try:
            trees_df = _safe_fetch(tree_query)
        except Exception:
            return no_update
        if trees_df is None:
            return no_update

        patched_fig["data"][3]["lat"] = trees_df["Latitude"].tolist()
        patched_fig["data"][3]["lon"] = trees_df["Longitude"].tolist()
        patched_fig["data"][3]["marker"]["size"] = 15
        patched_fig["data"][3]["marker"]["color"] = TREE_MARKER_COLOR
        patched_fig["data"][3]["marker"]["opacity"] = 0.97
        patched_fig["data"][3]["hovertext"] = [
            _tree_hover_text(row)
            for _, row in trees_df.iterrows()
        ]
        patched_fig["data"][3]["customdata"] = trees_df[
            ["source_table", "Latitude", "Longitude", "locality_full_name"]
        ].values.tolist()
    else:
        patched_fig["data"][3]["lat"] = []
        patched_fig["data"][3]["lon"] = []
        patched_fig["data"][3]["hovertext"] = []
        patched_fig["data"][3]["customdata"] = []

    return patched_fig


@callback(
    [
        Output("california-map", "figure", allow_duplicate=True),
        Output("search-results-data", "children"),
        Output("search-result-store", "data"),
        Output("search-status-indicator", "children"),
    ],
    [Input("search-trees-btn", "n_clicks"), Input("clear-search-btn", "n_clicks")],
    [
        State("search-ids-input", "value"),
        State("search-id-type", "value"),
        State("map-source-dropdown", "value"),
        State("map-location-filter", "value"),
        State("map-year-filter", "value"),
        State("map-availability-grid", "filterModel"),
    ],
    prevent_initial_call=True,
)
def search_trees(search_clicks, clear_clicks, input_text, id_type, selected_source, selected_locations, selected_years, availability_filter_model):
    trigger = callback_context.triggered[0]["prop_id"].split(".")[0] if callback_context.triggered else None
    patched_fig = Patch()

    if trigger == "clear-search-btn":
        patched_fig["data"][4]["lat"] = []
        patched_fig["data"][4]["lon"] = []
        patched_fig["data"][4]["hovertext"] = []
        patched_fig["data"][4]["customdata"] = []
        return patched_fig, html.Div("Search results cleared.", className="placeholder-card"), None, ""

    if not input_text or not input_text.strip():
        return no_update, html.Div("Enter one or more identifiers to search.", className="placeholder-card"), no_update, ""

    raw_ids = input_text.replace("\n", ",").split(",")
    ids = _search_identifier_variants([value.strip() for value in raw_ids if value.strip()], id_type)
    if not ids:
        return no_update, html.Div("No valid identifiers were provided.", className="placeholder-card"), no_update, ""

    table_name = _map_table_name(selected_source)
    if not table_name:
        return no_update, html.Div("No mappable datasets are available for search.", className="placeholder-card"), None, ""

    available_columns = set(get_table_columns(table_name))
    locality_col = _resolve_column_name(table_name, "locality_full_name") or _resolve_column_name(table_name, "Locality_full_name")
    if not locality_col:
        return no_update, html.Div("No mappable datasets are available for search.", className="placeholder-card"), None, ""

    optional_selects = []
    for column_name in OPTIONAL_MAP_COLUMNS:
        if column_name in available_columns:
            optional_selects.append(f"[{column_name}]")
        else:
            optional_selects.append(f"NULL AS [{column_name}]")

    where_clause = _build_where_clause(table_name, selected_locations, selected_years, filter_model=availability_filter_model)
    ids_sql = ", ".join(_sql_literal(value) for value in ids)
    id_col = _resolve_column_name(table_name, id_type)
    if id_col:
        where_clause += f" AND [{id_col}] IN ({ids_sql})"

    search_query = f"""
SELECT TOP 10000
    {_sql_literal(table_name)} AS [source_table],
    [{locality_col}] AS [locality_full_name],
    [Latitude],
    [Longitude],
    {', '.join(optional_selects)}
FROM [dbo].[{table_name}]
WHERE {where_clause}
"""
    try:
        df = _safe_fetch(search_query)
    except Exception:
        return no_update, html.Div("Search is unavailable right now. Try a smaller dataset scope or try again later.", className="status-warning"), None, ""

    if df is None or df.empty:
        patched_fig["data"][4]["lat"] = []
        patched_fig["data"][4]["lon"] = []
        patched_fig["data"][4]["hovertext"] = []
        patched_fig["data"][4]["customdata"] = []
        return patched_fig, html.Div("No matching trees were found.", className="placeholder-card"), None, ""

    map_df = df.dropna(subset=["Latitude", "Longitude"])
    patched_fig["data"][4]["lat"] = map_df["Latitude"].tolist()
    patched_fig["data"][4]["lon"] = map_df["Longitude"].tolist()
    patched_fig["data"][4]["marker"]["size"] = 19
    patched_fig["data"][4]["marker"]["color"] = "#6d28d9"
    patched_fig["data"][4]["marker"]["opacity"] = 0.96
    patched_fig["data"][4]["hovertext"] = [
        _tree_hover_text(row)
        for _, row in map_df.iterrows()
    ]
    patched_fig["data"][4]["customdata"] = map_df[["source_table", "Latitude", "Longitude", "locality_full_name"]].values.tolist()

    store_data = {"records": df.to_dict("records"), "filename": "search_results.csv"}
    result_card = html.Div(
        [
            _summary_card("Search Matches", f"{len(df):,} rows", "#6f42c1"),
            _summary_card("Mapped Points", f"{len(map_df):,} plotted", "#2d6a4f"),
            html.Button("Download Filtered CSV", id="search-download-btn", n_clicks=0, className="btn btn-success"),
            html.Details(
                [
                    html.Summary("View raw search results"),
                    _make_table(df, "search-results-table"),
                ],
                className="details-panel",
            ),
        ],
        className="panel-card",
    )
    return patched_fig, result_card, store_data, ""


@callback(
    Output("stored-click-data", "data", allow_duplicate=True),
    Input("clear-map-selection-btn", "n_clicks"),
    prevent_initial_call=True,
)
def clear_map_selection(n_clicks):
    if not n_clicks:
        raise PreventUpdate
    return None


@callback(
    Output("map-coordinate-selection-status", "children"),
    [Input("map-selected-coordinate-store", "data"), Input("map-coordinate-store", "data")],
)
def render_coordinate_selection_status(selected_data, coordinate_records):
    if selected_data and selected_data.get("records"):
        count = len(selected_data.get("records") or [])
        return html.Div(
            [
                html.Div("Current download selection", className="selection-card-label"),
                html.Div(selected_data.get("label") or "Selected map point", className="selection-card-title"),
                html.Div(
                    f"{selected_data.get('kind', 'Selection')} · {count:,} coordinate row{'s' if count != 1 else ''}",
                    className="selection-card-copy",
                ),
            ],
            className="selection-card selection-card--active",
        )

    total = len(coordinate_records or [])
    return html.Div(
        [
            html.Div("Current download selection", className="selection-card-label"),
            html.Div("All active map coordinates", className="selection-card-title"),
            html.Div(
                f"No site selected · {total:,} coordinate row{'s' if total != 1 else ''} ready",
                className="selection-card-copy",
            ),
        ],
        className="selection-card",
    )


@callback(
    Output("click-download-csv", "data"),
    Input("click-download-btn", "n_clicks"),
    State("click-result-store", "data"),
    prevent_initial_call=True,
)
def download_click_csv(n_clicks, store_data):
    if not n_clicks or not store_data:
        return no_update
    df = pd.DataFrame(store_data["records"])
    return dcc.send_data_frame(df.to_csv, store_data["filename"], index=False)


@callback(
    Output("search-download-csv", "data"),
    Input("search-download-btn", "n_clicks"),
    State("search-result-store", "data"),
    prevent_initial_call=True,
)
def download_search_csv(n_clicks, store_data):
    if not n_clicks or not store_data:
        return no_update
    df = pd.DataFrame(store_data["records"])
    return dcc.send_data_frame(df.to_csv, store_data["filename"], index=False)


@callback(
    Output("map-download-coordinates", "data"),
    Input("download-map-coordinates-btn", "n_clicks"),
    [State("map-coordinate-store", "data"), State("map-selected-coordinate-store", "data")],
    prevent_initial_call=True,
)
def download_map_coordinates(n_clicks, records, selected_data):
    if not n_clicks:
        return no_update
    if selected_data and selected_data.get("records"):
        records = selected_data["records"]
        filename = selected_data.get("filename") or "selected_map_coordinates.csv"
    else:
        filename = "active_map_coordinates.csv"
    if not records:
        return no_update
    df = pd.DataFrame(records)
    keep = [column for column in ["source_table", "locality_full_name", "Latitude", "Longitude", "Accession", "sample_id", "Year", "Site"] if column in df.columns]
    if keep:
        df = df[keep + [column for column in df.columns if column not in keep]]
    return dcc.send_data_frame(df.to_csv, filename, index=False)

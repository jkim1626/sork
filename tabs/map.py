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

SEARCH_ID_COLUMNS = [
    {"label": "Accession", "value": "Accession"},
    {"label": "Sample ID", "value": "sample_id"},
]

OPTIONAL_MAP_COLUMNS = ["Accession", "sample_id", "Year", "Site"]
INDIVIDUAL_TREE_ZOOM_THRESHOLD = 8
MAX_UPLOADED_MAP_ROWS = 10000
MAX_UPLOAD_PREVIEW_ROWS = 8
TREE_MARKER_COLOR = "#d90429"
DEFAULT_MAP_VIEW = {"center": {"lon": -119.5, "lat": 37.5}, "zoom": 5}

UCLA_COORDINATES = {
    "latitude": 34.0682,
    "longitude": -118.4455,
}


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


def _table_has_column(column_name):
    table_name = _map_table_name()
    if not table_name:
        return False
    return column_name in set(get_table_columns(table_name))


def _build_where_clause(selected_locations=None, selected_years=None):
    clauses = ["[Latitude] IS NOT NULL", "[Longitude] IS NOT NULL"]
    if selected_locations:
        values = ", ".join(_sql_literal(value) for value in selected_locations)
        clauses.append(f"[locality_full_name] IN ({values})")
    if selected_years and _table_has_column("Year"):
        values = ", ".join(_sql_literal(value) for value in selected_years)
        clauses.append(f"[Year] IN ({values})")
    return " AND ".join(clauses)


def _build_site_aggregate_query(selected_source, selected_locations=None, selected_years=None):
    table_name = _map_table_name(selected_source)
    if not table_name:
        return None
    return f"""
SELECT
    [locality_full_name],
    AVG([Longitude]) AS avg_longitude,
    AVG([Latitude]) AS avg_latitude,
    COUNT(*) AS tree_count
FROM [dbo].[{table_name}]
WHERE {_build_where_clause(selected_locations, selected_years)}
GROUP BY [locality_full_name]
"""


def _build_coordinate_query(selected_source, selected_locations=None, selected_years=None):
    table_name = _map_table_name(selected_source)
    if not table_name:
        return None
    available_columns = set(get_table_columns(table_name))
    optional_selects = []
    for column_name in OPTIONAL_MAP_COLUMNS:
        if column_name in available_columns:
            optional_selects.append(f"[{column_name}]")
        else:
            optional_selects.append(f"NULL AS [{column_name}]")

    return f"""
SELECT
    {_sql_literal(table_name)} AS [source_table],
    [locality_full_name],
    [Latitude],
    [Longitude],
    {', '.join(optional_selects)}
FROM [dbo].[{table_name}]
WHERE {_build_where_clause(selected_locations, selected_years)}
"""


def _build_location_options_query(selected_source):
    table_name = _map_table_name(selected_source)
    if not table_name:
        return None
    return f"""
SELECT DISTINCT [locality_full_name]
FROM [dbo].[{table_name}]
WHERE [locality_full_name] IS NOT NULL AND [Latitude] IS NOT NULL AND [Longitude] IS NOT NULL
ORDER BY [locality_full_name]
"""


def _build_year_options_query(selected_source):
    table_name = _map_table_name(selected_source)
    if not table_name or not _table_has_column("Year"):
        return None
    return f"""
SELECT DISTINCT [Year]
FROM [dbo].[{table_name}]
WHERE [Year] IS NOT NULL
ORDER BY [Year]
"""


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
    rows = []
    if table_name:
        count_df = _safe_fetch(f"SELECT COUNT(*) AS row_count FROM [dbo].[{table_name}]")
        row_count = int(count_df.iloc[0]["row_count"]) if not count_df.empty else 0
        rows.append({"Dataset": table_name, "Rows": f"{row_count:,}"})

    note = "Uploaded tree datasets become visible here automatically when they are written into a mappable table."
    if dat_avail_table:
        note = f"Availability metadata sync is enabled via `{dat_avail_table}` when uploads succeed."

    return html.Div(
        [
            html.H6("Dataset Availability", className="section-title"),
            html.P(note, className="section-copy"),
            _make_grid(pd.DataFrame(rows), "map-availability-grid", height=300, page_size=8),
        ],
        className="panel-card",
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
                className="panel-card panel-card--compact",
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
    return AgGrid(
        id=grid_id,
        rowData=df.to_dict("records"),
        columnDefs=[
            {
                "headerName": str(column),
                "field": str(column),
                "filter": True,
                "sortable": True,
                "resizable": True,
                "minWidth": 150 if column == "Dataset" else 110,
                "flex": 2 if column == "Dataset" else 1,
            }
            for column in df.columns
        ],
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


def _tree_label(row):
    accession = row.get("Accession", "")
    sample_id = row.get("sample_id", "")
    locality = row.get("locality_full_name", "Tree")
    identifier = accession or sample_id
    return f"{locality} ({identifier})" if identifier else str(locality)


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
                                html.Label("Dataset scope", className="control-label"),
                                dcc.Dropdown(
                                    id="map-source-dropdown",
                                    options=_initial_map_source_options(),
                                    value=_default_map_source_value(),
                                    clearable=False,
                                    persistence=True,
                                    persistence_type="session",
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
                                html.Label("Years", className="control-label"),
                                dcc.Dropdown(
                                    id="map-year-filter",
                                    options=[],
                                    value=[],
                                    multi=True,
                                    placeholder="All years",
                                    persistence=True,
                                    persistence_type="session",
                                ),
                                html.Div(
                                    f"Choose a dataset first if filters are empty. Common gardens are green, UCLA is gold, individual trees are red after zoom {INDIVIDUAL_TREE_ZOOM_THRESHOLD}, uploaded trees are blue, and search hits are purple.",
                                    className="info-banner",
                                ),
                                html.Div(
                                    [
                                        html.Button("Reset View", id="reset-map", className="btn btn-success btn-sm"),
                                        html.Button(
                                            "Download Coordinates",
                                            id="download-map-coordinates-btn",
                                            className="btn btn-outline-secondary btn-sm",
                                        ),
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
                                    "Upload CSV or TSV rows with Latitude and Longitude to add a temporary tree layer to the map. Optional columns such as locality_full_name, Site, Accession, sample_id, and Year improve filtering and labels.",
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
                            className="panel-card",
                        ),
                        html.Div(
                            [
                                html.H6("Find Trees", className="section-title"),
                                html.P(
                                    "Paste known Accessions or sample IDs, then search. Results appear as purple points and in a downloadable grid below.",
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
                                    placeholder="Paste IDs here, one per line or comma-separated.",
                                    style={
                                        "width": "100%",
                                        "height": "90px",
                                        "fontFamily": "monospace",
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
                            ],
                            className="panel-card",
                        ),
                        html.Div(id="map-availability-panel", children=html.Div("Loading dataset availability...", className="placeholder-card")),
                        html.Div(id="search-results-data"),
                        html.Div(id="individual-tree-data"),
                    ],
                    className="map-sidebar",
                ),
                html.Div(
                    [
                        html.Div(
                            [
                                _summary_card("Common Gardens", "Clustered statewide view", "#2d6a4f"),
                                _summary_card("UCLA", "Always highlighted", "#e0a800"),
                                _summary_card("Individual Trees", f"Shown from zoom {INDIVIDUAL_TREE_ZOOM_THRESHOLD}", TREE_MARKER_COLOR),
                                _summary_card("Uploaded Trees", "Added from tree lists", "#0d6efd"),
                            ],
                            className="summary-grid",
                        ),
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
                            "Warning: detailed tree rendering and large search exports may take a while on broad dataset scopes.",
                            className="warning-banner",
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
        Output("search-id-type", "value", allow_duplicate=True),
        Output("search-ids-input", "value", allow_duplicate=True),
        Output("stored-click-data", "data", allow_duplicate=True),
        Output("click-result-store", "data", allow_duplicate=True),
        Output("search-result-store", "data", allow_duplicate=True),
        Output("uploaded-tree-store", "data", allow_duplicate=True),
        Output("map-coordinate-store", "data", allow_duplicate=True),
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
        SEARCH_ID_COLUMNS[0]["value"],
        "",
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
    ],
    State("map-viewport-store", "data"),
)
def update_map_and_click_data(reset_clicks, selected_source, selected_locations, selected_years, upload_data, click_data, viewport):
    trigger_id = callback_context.triggered[0]["prop_id"].split(".")[0] if callback_context.triggered else None

    if trigger_id == "california-map":
        return no_update, click_data, no_update

    fig = go.Figure()
    active_view = DEFAULT_MAP_VIEW if trigger_id == "reset-map" else (viewport or DEFAULT_MAP_VIEW)
    aggregate_query = _build_site_aggregate_query(selected_source, selected_locations, selected_years)
    try:
        locations_df = _safe_fetch(aggregate_query) if aggregate_query else pd.DataFrame()
    except Exception:
        locations_df = pd.DataFrame()

    if locations_df is None:
        locations_df = pd.DataFrame()

    coordinate_records = []
    coordinates_df = pd.DataFrame()
    coordinate_query = _build_coordinate_query(selected_source, selected_locations, selected_years)
    if coordinate_query:
        try:
            coordinates_df = _safe_fetch(coordinate_query)
            if coordinates_df is not None and not coordinates_df.empty:
                coordinate_records.extend(coordinates_df.to_dict("records"))
        except Exception:
            coordinates_df = pd.DataFrame()

    if not locations_df.empty:
        counts = locations_df["tree_count"].tolist()
        min_size, max_size = 14, 36
        min_count, max_count = min(counts), max(counts)
        if min_count == max_count:
            sizes = [16] * len(counts)
        else:
            sizes = [
                min_size + (count - min_count) / (max_count - min_count) * (max_size - min_size)
                for count in counts
            ]

        fig.add_trace(
            go.Scattermapbox(
                mode="markers",
                lon=locations_df["avg_longitude"].tolist(),
                lat=locations_df["avg_latitude"].tolist(),
                marker={"size": sizes, "color": "#0b6b3a", "opacity": 0.92},
                hovertext=[
                    f"{row['locality_full_name']}<br>{row['tree_count']} tree records"
                    for _, row in locations_df.iterrows()
                ],
                hoverinfo="text",
                customdata=[[map_table, row["locality_full_name"]] for _, row in locations_df.iterrows()],
                name="Common Gardens",
            )
        )
    else:
        fig.add_trace(go.Scattermapbox(mode="markers", lon=[], lat=[], name="Common Gardens"))

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
                f"Tree: {_tree_label(row)}<br>{row['source_table']}<br>Accession: {row.get('Accession', '')}<br>Sample ID: {row.get('sample_id', '')}"
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
                    f"{row.get('locality_full_name', 'Uploaded trees')}<br>Uploaded tree list<br>Accession: {row.get('Accession', '')}"
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

    options = list(options_by_value.values())
    valid_values = {option["value"] for option in options}
    selected = [value for value in (current_values or []) if value in valid_values]
    return options, selected


@callback(
    [Output("map-year-filter", "options"), Output("map-year-filter", "value")],
    [Input("map-source-dropdown", "value"), Input("uploaded-tree-store", "data")],
    State("map-year-filter", "value"),
)
def update_year_filter_options(selected_source, upload_data, current_values):
    options_by_value = {}
    query = _build_year_options_query(selected_source)
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
        for value in upload_df["Year"].dropna().unique().tolist():
            options_by_value[str(value)] = {"label": f"{value} (uploaded)", "value": value}

    options = list(options_by_value.values())
    valid_keys = set(options_by_value.keys())
    selected = [value for value in (current_values or []) if str(value) in valid_keys]
    return options, selected


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
    [Output("individual-tree-data", "children"), Output("click-result-store", "data")],
    Input("stored-click-data", "data"),
)
def display_click_data(click_data):
    if not click_data or "points" not in click_data or not click_data["points"]:
        return html.Div("Select a site or individual tree to inspect details.", className="placeholder-card"), None

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
                className="panel-card",
            ), None

        if curve in (2, 4):
            source_table, latitude, longitude, locality_name = customdata
            if source_table == "Uploaded tree list":
                return html.Div(
                    [
                        _summary_card("Uploaded Tree", locality_name, "#0d6efd"),
                        html.P("This row came from the current uploaded tree list. Use Download Coordinates to export it with the rest of the active map coordinates.", className="section-copy"),
                    ],
                    className="panel-card",
                ), None
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
            return html.Div("No data available for this selection.", className="placeholder-card"), None

        store_data = {"records": df.to_dict("records"), "filename": filename}
        return (
            html.Div(
                [
                    _summary_card("Selected Site", header_text, "#1d3557"),
                    _summary_card("Details", summary, "#2d6a4f"),
                    html.Button("Download Coordinates CSV", id="click-download-btn", n_clicks=0, className="btn btn-success"),
                    html.Details(
                        [
                            html.Summary("View raw rows"),
                            _make_table(df, "tree-data-table"),
                        ],
                        className="details-panel",
                    ),
                ],
                className="panel-card",
            ),
            store_data,
        )
    except Exception:
        return html.Div("Details are unavailable for this selection.", className="placeholder-card"), None


@callback(
    Output("california-map", "figure", allow_duplicate=True),
    Input("california-map", "relayoutData"),
    [
        State("map-source-dropdown", "value"),
        State("map-location-filter", "value"),
        State("map-year-filter", "value"),
    ],
    prevent_initial_call=True,
)
def toggle_individual_trees(relayout_data, selected_source, selected_locations, selected_years):
    if not relayout_data:
        return no_update

    zoom = relayout_data.get("mapbox.zoom")
    lon_range = relayout_data.get("mapbox._derived", {}).get("coordinates")
    if zoom is None:
        return no_update

    patched_fig = Patch()

    if zoom >= INDIVIDUAL_TREE_ZOOM_THRESHOLD:
        tree_query = _build_coordinate_query(selected_source, selected_locations, selected_years)
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

        patched_fig["data"][2]["lat"] = trees_df["Latitude"].tolist()
        patched_fig["data"][2]["lon"] = trees_df["Longitude"].tolist()
        patched_fig["data"][2]["marker"]["size"] = 15
        patched_fig["data"][2]["marker"]["color"] = TREE_MARKER_COLOR
        patched_fig["data"][2]["marker"]["opacity"] = 0.97
        patched_fig["data"][2]["hovertext"] = [
            f"Tree: {_tree_label(row)}<br>{row['source_table']}<br>Accession: {row.get('Accession', '')}<br>Sample ID: {row.get('sample_id', '')}"
            for _, row in trees_df.iterrows()
        ]
        patched_fig["data"][2]["customdata"] = trees_df[
            ["source_table", "Latitude", "Longitude", "locality_full_name"]
        ].values.tolist()
    else:
        patched_fig["data"][2]["lat"] = []
        patched_fig["data"][2]["lon"] = []
        patched_fig["data"][2]["hovertext"] = []
        patched_fig["data"][2]["customdata"] = []

    return patched_fig


@callback(
    [
        Output("california-map", "figure", allow_duplicate=True),
        Output("search-results-data", "children"),
        Output("search-result-store", "data"),
    ],
    [Input("search-trees-btn", "n_clicks"), Input("clear-search-btn", "n_clicks")],
    [
        State("search-ids-input", "value"),
        State("search-id-type", "value"),
        State("map-source-dropdown", "value"),
        State("map-location-filter", "value"),
        State("map-year-filter", "value"),
    ],
    prevent_initial_call=True,
)
def search_trees(search_clicks, clear_clicks, input_text, id_type, selected_source, selected_locations, selected_years):
    trigger = callback_context.triggered[0]["prop_id"].split(".")[0] if callback_context.triggered else None
    patched_fig = Patch()

    if trigger == "clear-search-btn":
        patched_fig["data"][3]["lat"] = []
        patched_fig["data"][3]["lon"] = []
        patched_fig["data"][3]["hovertext"] = []
        patched_fig["data"][3]["customdata"] = []
        return patched_fig, html.Div("Search results cleared.", className="placeholder-card"), None

    if not input_text or not input_text.strip():
        return no_update, html.Div("Enter one or more identifiers to search.", className="placeholder-card"), no_update

    raw_ids = input_text.replace("\n", ",").split(",")
    ids = [value.strip() for value in raw_ids if value.strip()]
    if not ids:
        return no_update, html.Div("No valid identifiers were provided.", className="placeholder-card"), no_update

    base_query = _build_coordinate_query(selected_source, selected_locations, selected_years)
    if not base_query:
        return no_update, html.Div("No mappable datasets are available for search.", className="placeholder-card"), None

    ids_sql = ", ".join(_sql_literal(value) for value in ids)
    search_query = f"""
SELECT *
FROM (
    {base_query}
) q
WHERE [{id_type}] IN ({ids_sql})
"""
    try:
        df = _safe_fetch(search_query)
    except Exception:
        return no_update, html.Div("Search is unavailable right now. Try a smaller dataset scope or try again later.", className="status-warning"), None

    if df is None or df.empty:
        patched_fig["data"][3]["lat"] = []
        patched_fig["data"][3]["lon"] = []
        patched_fig["data"][3]["hovertext"] = []
        patched_fig["data"][3]["customdata"] = []
        return patched_fig, html.Div("No matching trees were found.", className="placeholder-card"), None

    map_df = df.dropna(subset=["Latitude", "Longitude"])
    patched_fig["data"][3]["lat"] = map_df["Latitude"].tolist()
    patched_fig["data"][3]["lon"] = map_df["Longitude"].tolist()
    patched_fig["data"][3]["marker"]["size"] = 19
    patched_fig["data"][3]["marker"]["color"] = "#6d28d9"
    patched_fig["data"][3]["marker"]["opacity"] = 0.96
    patched_fig["data"][3]["hovertext"] = [
        f"{row['locality_full_name']}<br>{row['source_table']}<br>{id_type}: {row.get(id_type, '')}"
        for _, row in map_df.iterrows()
    ]
    patched_fig["data"][3]["customdata"] = map_df[["source_table", "locality_full_name"]].values.tolist()

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
    return patched_fig, result_card, store_data


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
    State("map-coordinate-store", "data"),
    prevent_initial_call=True,
)
def download_map_coordinates(n_clicks, records):
    if not n_clicks or not records:
        return no_update
    df = pd.DataFrame(records)
    keep = [column for column in ["source_table", "locality_full_name", "Latitude", "Longitude", "Accession", "sample_id", "Year", "Site"] if column in df.columns]
    if keep:
        df = df[keep + [column for column in df.columns if column not in keep]]
    return dcc.send_data_frame(df.to_csv, "active_map_coordinates.csv", index=False)

import logging

import dash
from dash import dcc, html, Input, Output, State, callback, ctx
from dash.exceptions import PreventUpdate
from dash_ag_grid import AgGrid
from database import fetch_data_from_sql
from data_access import (
    DatabaseAccessError,
    fetch_table_rows,
    get_allowed_tables,
    get_column_distinct_values,
)
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

# Table Options
table_options = get_allowed_tables()
logger = logging.getLogger(__name__)


def _friendly_error(title="Data preview unavailable"):
    return html.Div(
        [
            html.H6(title, className="section-title"),
            html.P(
                "The database could not return this view right now. Try a smaller row range, clear filters, or choose another table.",
                className="section-copy",
            ),
        ],
        className="status-warning",
    )


def _empty_state(message):
    return html.Div(message, className="placeholder-card")


def _make_grid(df, grid_id):
    column_defs = [
        {
            "headerName": str(column),
            "field": str(column),
            "filter": True,
            "sortable": True,
            "resizable": True,
            "minWidth": 120,
        }
        for column in df.columns
    ]
    return AgGrid(
        id=grid_id,
        rowData=df.to_dict("records"),
        columnDefs=column_defs,
        defaultColDef={"filter": True, "sortable": True, "resizable": True},
        dashGridOptions={"animateRows": False, "pagination": True, "paginationPageSize": 25},
        className="ag-theme-alpine compact-grid",
        style={"width": "100%", "height": "360px"},
    )


def _get_table_columns_direct(table_name):
    df = fetch_data_from_sql(f"SELECT TOP 1 * FROM [dbo].[{table_name}]")
    if df is None:
        raise DatabaseAccessError(f"Could not fetch columns from '{table_name}'.")
    return df.columns.tolist()


def _get_table_row_count_direct(table_name):
    df = fetch_data_from_sql(f"SELECT COUNT(*) AS row_count FROM [dbo].[{table_name}]")
    if df is None or df.empty:
        raise DatabaseAccessError(f"Could not count rows for '{table_name}'.")
    return int(df.iloc[0]["row_count"])

download_layout = dcc.Tab(
    [
        # Store the tab's active state
        dcc.Store(id="download-tab-active", data=False),
        html.Div(
            [
                html.H4("Data Browser", className="page-title"),
                html.P(
                    "View available tables.",
                    className="page-intro",
                ),
            ],
            className="page-header-block",
        ),
        html.Div(id="download-table-overview", className="file-table-grid"),
        html.Div(
            [
                html.Div(
                    [
                        html.H6("Choose a Table", className="section-title"),
                        dcc.Dropdown(table_options, id="download_table_dropdown", placeholder="Choose a source table"),
                        html.Div(id="download-row-info", className="section-copy"),
                    ],
                    className="panel-card",
                ),
                html.Div(
                    [
                        html.H6("Limit Rows", className="section-title"),
                        dcc.Checklist(
                            id="download-limit-toggle",
                            options=[{"label": " Limit rows", "value": "limit"}],
                            value=["limit"],
                            inline=True,
                        ),
                        html.Div(
                            [
                                html.Label("Start row", className="control-label"),
                                dcc.Input(id="download-start-row", type="number", min=1, value=1, className="number-input"),
                                html.Label("End row", className="control-label"),
                                dcc.Input(id="download-end-row", type="number", min=1, value=100, className="number-input"),
                            ],
                            id="download-row-limit-controls",
                            className="inline-controls",
                        ),
                    ],
                    className="panel-card",
                ),
                html.Div(
                    [
                        html.H6("Simple Filter", className="section-title"),
                        html.P("Optional: choose one column and one or more values before refreshing the preview.", className="section-copy"),
                        dcc.Dropdown(id="download-filter-column", options=[], value=None, placeholder="Filter column"),
                        dcc.Dropdown(id="download-filter-values", options=[], value=[], multi=True, placeholder="Values"),
                    ],
                    className="panel-card",
                ),
                html.Div(
                    [
                        html.H6("Columns", className="section-title"),
                        html.Div(
                            [
                                html.Button("Select All", id="download-select-all-btn", n_clicks=0, className="btn btn-outline-secondary btn-sm"),
                                html.Button("Deselect All", id="download-deselect-all-btn", n_clicks=0, className="btn btn-outline-secondary btn-sm"),
                            ],
                            className="button-row",
                        ),
                        dcc.Checklist(
                            id="download-columns",
                            options=[],
                            value=[],
                            inline=False,
                            labelStyle={"display": "block", "marginBottom": "3px"},
                            className="column-checklist",
                        ),
                    ],
                    className="panel-card",
                ),
                html.Div(
                    [
                        html.Button("Refresh Preview", id="preview-button", className="btn btn-success"),
                        html.Button("Download Flat File", id="download-button", className="btn btn-outline-secondary"),
                        dcc.Download(id="download-dataframe-csv"),
                    ],
                    className="button-row",
                ),
                html.Div(id="download-status"),
                html.Div(
                    [
                        html.H5("Preview Rows", className="section-title"),
                        html.Div(id="download-preview"),
                    ],
                    className="panel-card",
                ),
            ],
            id="download-container",
            className="files-workspace",
            style={"display": "none"},
        ),
    ],
    label="Files",
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
     Output('download-status', 'children', allow_duplicate=True),
     Output('download-container', 'style', allow_duplicate=True)],
    [Input('download-tab-active', 'data')],
    prevent_initial_call=True
)
def reset_download_tab_data(is_active):
    raise PreventUpdate

# Callback to show download container when table is selected
@callback(
    Output("download-container", "style"),
    Input("download_table_dropdown", "value")
)
def show_download_container(selected_table):
    if selected_table:
        return {"display": "block"}
    return {"display": "none"}


@callback(
    Output("download-table-overview", "children"),
    Input("download-tab-active", "data")
)
def render_table_overview(is_active):
    if not is_active:
        raise PreventUpdate
    cards = []
    for table in table_options:
        try:
            row_count = _get_table_row_count_direct(table)
            columns = _get_table_columns_direct(table)
            body = f"{row_count:,} rows · {len(columns):,} columns"
        except DatabaseAccessError as exc:
            logger.exception("Unable to summarize table %s", table)
            body = "Unavailable"
        cards.append(
            html.Div(
                [
                    html.Div(table, className="summary-card-title"),
                    html.Div(body, className="summary-card-body"),
                ],
                className="summary-card file-table-card",
            )
        )
    return cards or html.Div("No source tables are configured for browsing.", className="placeholder-card")

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
        columns = _get_table_columns_direct(selected_table)
        column_options = [{'label': col, 'value': col} for col in columns]
        
        total_rows = _get_table_row_count_direct(selected_table)
        
        row_info = f"{total_rows:,} rows available in this table. The preview only shows a small slice so the page stays fast."
        
        # Return all columns selected by default
        return column_options, columns, row_info, total_rows
    except DatabaseAccessError as e:
        logger.exception("Unable to load file browser metadata for %s", selected_table)
        return [], [], "Table details are unavailable right now.", 100

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


@callback(
    [Output("download-filter-column", "options"), Output("download-filter-column", "value")],
    Input("download_table_dropdown", "value")
)
def update_filter_column_options(selected_table):
    if not selected_table:
        return [], None
    try:
        columns = _get_table_columns_direct(selected_table)
        return [{"label": column, "value": column} for column in columns], None
    except DatabaseAccessError:
        logger.exception("Unable to load filter columns for %s", selected_table)
        return [], None


@callback(
    [Output("download-filter-values", "options"), Output("download-filter-values", "value")],
    [Input("download_table_dropdown", "value"), Input("download-filter-column", "value")]
)
def update_filter_values(selected_table, filter_column):
    if not selected_table or not filter_column:
        return [], []
    try:
        values = get_column_distinct_values(selected_table, filter_column)
        return [{"label": str(value), "value": value} for value in values], []
    except DatabaseAccessError:
        logger.exception("Unable to load filter values for %s.%s", selected_table, filter_column)
        return [], []


@callback(
    Output("download-row-limit-controls", "style"),
    Input("download-limit-toggle", "value")
)
def toggle_download_row_limits(limit_toggle):
    if limit_toggle and "limit" in limit_toggle:
        return {"display": "flex"}
    return {"display": "none"}

# Callback to show data preview
@callback(
    [Output("download-preview", "children"),
     Output("download-status", "children")],
    [Input("preview-button", "n_clicks"),
     Input("download_table_dropdown", "value")],
    [State("download-start-row", "value"),
     State("download-end-row", "value"),
     State("download-columns", "value"),
     State("download-limit-toggle", "value"),
     State("download-filter-column", "value"),
     State("download-filter-values", "value")]
)
def update_preview(n_clicks, selected_table, start_row, end_row, selected_columns, limit_toggle, filter_column, filter_values):
    if not selected_table or not selected_columns:
        return _empty_state("Choose a table to preview source rows."), []
    
    use_limit = limit_toggle and "limit" in limit_toggle
    if use_limit:
        if not start_row or start_row < 1:
            start_row = 1
        if not end_row or end_row < start_row:
            end_row = start_row + 99
        row_count = end_row - start_row + 1
    else:
        start_row = 1
        row_count = 100

    filters = {filter_column: filter_values} if filter_column and filter_values else None
    
    try:
        preview_df = fetch_table_rows(
            selected_table,
            selected_columns,
            start_row=start_row,
            row_count=row_count,
            max_rows=100,
            filters=filters,
        )

        if preview_df.empty:
            return _empty_state("No rows matched this range or filter."), html.Div("Adjust the row range or clear filters.", className="section-copy")
        
        preview = [
            html.P(f"Previewing {len(preview_df):,} rows. Sort or filter columns inside the grid.", className="section-copy"),
            _make_grid(preview_df, "download-preview-grid"),
        ]
        status = html.Div(
            f"Previewing up to 100 rows for {selected_table}. Filters are applied before the row limit.",
            className="section-copy",
        )
        return preview, status
    except DatabaseAccessError as e:
        logger.exception("Unable to generate file preview for %s", selected_table)
        return _friendly_error(), html.Div("Preview could not be generated.", className="section-copy")

# Callback to download CSV data
@callback(
    [Output("download-dataframe-csv", "data"),
     Output("download-status", "children", allow_duplicate=True)],
    [Input("download-button", "n_clicks")],
    [State("download_table_dropdown", "value"),
     State("download-start-row", "value"),
     State("download-end-row", "value"),
     State("download-columns", "value"),
     State("download-limit-toggle", "value"),
     State("download-filter-column", "value"),
     State("download-filter-values", "value")],
    prevent_initial_call=True
)
def download_csv(n_clicks, selected_table, start_row, end_row, selected_columns, limit_toggle, filter_column, filter_values):
    if not n_clicks or not selected_table or not selected_columns:
        raise PreventUpdate
    
    use_limit = limit_toggle and "limit" in limit_toggle
    if use_limit:
        if not start_row or start_row < 1:
            start_row = 1
        if not end_row or end_row < start_row:
            end_row = start_row + 999
        row_count = end_row - start_row + 1
    else:
        start_row = 1
        try:
            row_count = _get_table_row_count_direct(selected_table)
        except DatabaseAccessError:
            logger.exception("Unable to count rows for %s before download", selected_table)
            return None, _friendly_error("Download unavailable")

    filters = {filter_column: filter_values} if filter_column and filter_values else None
    
    try:
        df = fetch_table_rows(
            selected_table,
            selected_columns,
            start_row=start_row,
            row_count=row_count,
            filters=filters,
        )
        
        if df.empty:
            return None, html.Div("No rows matched that range.", style={"color": "#8a6d3b"})

        filename = f"{selected_table}_rows_{start_row}_to_{start_row + len(df) - 1}.csv"
        return (
            dcc.send_data_frame(df.to_csv, filename, index=False),
            html.Div(f"Prepared {len(df)} rows for download.", style={"color": "#666"}),
        )
    except DatabaseAccessError as e:
        logger.exception("Unable to download flat file for %s", selected_table)
        return None, _friendly_error("Download unavailable")

import logging

from dash import dcc, html, Input, Output, State, callback
from dash.exceptions import PreventUpdate
from dash_ag_grid import AgGrid
from database import fetch_data_from_sql
from data_access import (
    DatabaseAccessError,
    fetch_table_rows,
    get_allowed_tables,
    get_table_display_name,
)
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

# Table Options - create options with descriptive labels
_table_list = get_allowed_tables()
table_options = [
    {"label": get_table_display_name(table), "value": table}
    for table in _table_list
]
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
                    "Choose a database table to preview or download as a flat file.",
                    className="page-intro",
                ),
            ],
            className="page-header-block",
        ),
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
                        html.Div(
                            [
                                html.H6("Limit Rows", className="section-title"),
                                dcc.Checklist(
                                    id="download-limit-toggle",
                                    options=[{"label": " Limit preview rows", "value": "limit"}],
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
                                html.Div(id="download-limit-warning"),
                            ],
                            className="panel-card",
                        ),
                        html.Div(
                            [
                                html.Button("Refresh Preview", id="preview-button", n_clicks=0, className="btn btn-success"),
                                html.Button("Download Flat File", id="download-button", className="btn btn-outline-secondary"),
                                dcc.Download(id="download-dataframe-csv"),
                            ],
                            className="button-row",
                        ),
                        html.Div(
                            "Row limits only affect the preview; downloads include all rows and columns.",
                            className="section-copy",
                        ),
                        dcc.Loading(
                            id="download-status-loading",
                            type="default",
                            children=html.Div(id="download-status"),
                        ),
                        html.Div(
                            [
                                html.H5("Preview Rows", className="section-title"),
                                dcc.Loading(
                                    id="download-preview-loading",
                                    type="default",
                                    children=html.Div(id="download-preview"),
                                ),
                            ],
                            className="panel-card",
                        ),
                    ],
                    id="download-container",
                    style={"display": "none"},
                ),
            ],
            className="files-workspace",
        ),
    ],
    label="Files",
    id="download-tab",
    style={"padding": "15px"}
)

# Track tab selection state
@callback(
    Output('download-tab-active', 'data'),
    [Input('main-tabs', 'value'), Input('flat-files-subtabs', 'value')]
)
def set_download_tab_active(main_tab, sub_tab):
    # Active if we are on the Flat Files tab AND the download subtab is selected
    return main_tab == 'flat-files-tab' and sub_tab == 'download-subtab'

# Reset when tab is switched
@callback(
    [Output('download_table_dropdown', 'value', allow_duplicate=True),
     Output('download-start-row', 'value', allow_duplicate=True),
     Output('download-end-row', 'value', allow_duplicate=True),
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
    Output("download-row-info", "children"),
    [Input("download_table_dropdown", "value")]
)
def update_table_info(selected_table):
    if not selected_table:
        return ""
    
    try:
        columns = _get_table_columns_direct(selected_table)
        total_rows = _get_table_row_count_direct(selected_table)
        return f"{total_rows:,} rows and {len(columns):,} columns available in this table."
    except DatabaseAccessError as e:
        logger.exception("Unable to load file browser metadata for %s", selected_table)
        return "Table details are unavailable right now."


@callback(
    [Output("download-row-limit-controls", "style"),
     Output("download-limit-warning", "children")],
    Input("download-limit-toggle", "value")
)
def toggle_download_row_limits(limit_toggle):
    if limit_toggle and "limit" in limit_toggle:
        return {"display": "flex"}, None
    return {"display": "none"}, html.Div(
        "Row limiting is off. Previewing the full table may take time for large datasets.",
        className="status-warning compact-warning",
    )


@callback(
    Output("download-button", "children"),
    Input("download_table_dropdown", "value")
)
def update_download_button_label(selected_table):
    if not selected_table:
        return "Download Flat File"

    try:
        total_rows = _get_table_row_count_direct(selected_table)
        return f"Download Entire Dataset ({total_rows:,} rows)"
    except DatabaseAccessError:
        logger.exception("Unable to count rows for %s while labeling download button", selected_table)
        return "Download Entire Dataset"

# Callback to show data preview
@callback(
    [Output("download-preview", "children"),
     Output("download-status", "children")],
    [Input("preview-button", "n_clicks"),
     Input("download_table_dropdown", "value")],
    [State("download-start-row", "value"),
     State("download-end-row", "value"),
     State("download-limit-toggle", "value")]
)
def update_preview(n_clicks, selected_table, start_row, end_row, limit_toggle):
    if not selected_table:
        return _empty_state("Choose a table to preview source rows."), []

    try:
        selected_columns = _get_table_columns_direct(selected_table)
        use_limit = limit_toggle and "limit" in limit_toggle
        if use_limit:
            if not start_row or start_row < 1:
                start_row = 1
            if not end_row or end_row < start_row:
                end_row = start_row + 99
            row_count = end_row - start_row + 1
            preview_max_rows = row_count
            requested_text = f"rows {start_row:,}-{end_row:,}"
        else:
            start_row = 1
            row_count = _get_table_row_count_direct(selected_table)
            preview_max_rows = row_count
            requested_text = "the entire dataset"

        preview_df = fetch_table_rows(
            selected_table,
            selected_columns,
            start_row=start_row,
            row_count=row_count,
            max_rows=preview_max_rows,
        )

        if preview_df.empty:
            return _empty_state("No rows are available in this table."), html.Div("Choose another table.", className="section-copy")

        preview = [
            html.P(
                f"Previewing {len(preview_df):,} rows from {requested_text}. Sort or filter columns inside the grid.",
                className="section-copy",
            ),
            _make_grid(preview_df, "download-preview-grid"),
        ]
        status = html.Div(
            f"Preview loaded for {selected_table}.",
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
    [State("download_table_dropdown", "value")],
    prevent_initial_call=True
)
def download_csv(n_clicks, selected_table):
    if not n_clicks or not selected_table:
        raise PreventUpdate

    start_row = 1
    try:
        row_count = _get_table_row_count_direct(selected_table)
        selected_columns = _get_table_columns_direct(selected_table)
    except DatabaseAccessError:
        logger.exception("Unable to count rows for %s before download", selected_table)
        return None, _friendly_error("Download unavailable")
    
    try:
        df = fetch_table_rows(
            selected_table,
            selected_columns,
            start_row=start_row,
            row_count=row_count,
        )
        
        if df.empty:
            return None, html.Div("No rows are available for this table.", style={"color": "#8a6d3b"})

        filename = f"{selected_table}_all_rows.csv"
        return (
            dcc.send_data_frame(df.to_csv, filename, index=False),
            html.Div(f"Prepared the entire dataset for download ({len(df):,} rows).", style={"color": "#666"}),
        )
    except DatabaseAccessError as e:
        logger.exception("Unable to download flat file for %s", selected_table)
        return None, _friendly_error("Download unavailable")

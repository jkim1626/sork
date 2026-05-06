import logging

from dash import dcc, html, Input, Output, State, callback
from dash.exceptions import PreventUpdate
import dash
import pandas as pd
import io
import base64
from dash_ag_grid import AgGrid
from data_access import (
    DatabaseAccessError,
    append_dataframe_to_table,
    get_allowed_tables,
    get_table_columns,
    get_table_schema_preview,
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


def _status(message, kind="warning", title=None):
    children = []
    if title:
        children.append(html.H6(title, className="section-title"))
    children.append(html.P(message, className="section-copy"))
    return html.Div(children, className=f"status-{kind}")


def _make_grid(df, grid_id, height=320):
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
                "minWidth": 120,
            }
            for column in df.columns
        ],
        defaultColDef={"filter": True, "sortable": True, "resizable": True},
        dashGridOptions={"pagination": True, "paginationPageSize": 10, "animateRows": False},
        className="ag-theme-alpine compact-grid",
        style={"width": "100%", "height": f"{height}px"},
    )


def _make_simple_table(df):
    header = html.Thead(html.Tr([html.Th(str(column)) for column in df.columns]))
    body = html.Tbody(
        [
            html.Tr([html.Td("" if pd.isna(value) else str(value)) for value in row])
            for row in df.itertuples(index=False, name=None)
        ]
    )
    return html.Div(
        html.Table([header, body], className="simple-data-table"),
        className="simple-data-table-wrap",
    )

upload_layout = dcc.Tab(
    [
        # Store the tab's active state
        dcc.Store(id="upload-tab-active", data=False),
        html.Div(
            [
                html.H4("Upload Data", className="page-title"),
                html.P(
                    "Add CSV rows to an approved database table. The file must use the same column names and order shown in the table structure preview.",
                    className="page-intro",
                ),
            ],
            className="page-header-block",
        ),
        html.Div(
            [
                html.Div(
                    [
                        html.H6("Target Table", className="section-title"),
                        dcc.Dropdown(
                            table_options,
                            id="upload_table_dropdown",
                            placeholder="Choose a destination table",
                            maxHeight=420,
                        ),
                        html.P("Choose where these rows should be appended.", className="section-copy"),
                    ],
                    className="panel-card upload-target-panel",
                ),
                html.Div(
                    [
                        html.Div(
                            [
                                html.H6("CSV File", className="section-title"),
                                dcc.Upload(
                                    id='upload-csv',
                                    children=html.Div("Drop a CSV file here or select one"),
                                    className="upload-dropzone",
                                    multiple=False,
                                ),
                            ],
                            className="panel-card",
                        ),
                        html.Div(id="table-structure-info"),
                        html.Div(id="upload-status"),
                        html.Div(id="csv-preview"),
                        html.Div(
                            [
                                html.Button("Upload to Database", id="upload-button", disabled=True, className="btn btn-success"),
                            ],
                            className="button-row",
                        ),
                        html.Div(id="upload-result"),
                    ],
                    id="upload-container",
                    className="upload-workspace",
                    style={"display": "none"},
                ),
            ],
            className="upload-workspace",
        ),
    ],
    label="Upload",
    id="upload-tab",
    style={"padding": "15px"}
)

# Track tab selection state
@callback(
    Output('upload-tab-active', 'data'),
    [Input('main-tabs', 'value'), Input('flat-files-subtabs', 'value')]
)
def set_upload_tab_active(main_tab, sub_tab):
    # Active if we are on the Flat Files tab AND the upload subtab is selected
    return main_tab == 'flat-files-tab' and sub_tab == 'upload-subtab'

# Reset when tab is switched
@callback(
    [Output('upload_table_dropdown', 'value', allow_duplicate=True),
     Output('upload-csv', 'contents', allow_duplicate=True),
     Output('upload-button', 'disabled', allow_duplicate=True),
     Output('table-structure-info', 'children', allow_duplicate=True),
     Output('upload-status', 'children', allow_duplicate=True),
     Output('csv-preview', 'children', allow_duplicate=True),
     Output('upload-result', 'children', allow_duplicate=True),
     Output('upload-container', 'style', allow_duplicate=True)],
    [Input('upload-tab-active', 'data')],
    prevent_initial_call=True
)
def reset_upload_tab_data(is_active):
    raise PreventUpdate

# Callback to show upload container when table is selected
@callback(
    Output("upload-container", "style"),
    Input("upload_table_dropdown", "value")
)
def show_upload_container(selected_table):
    if selected_table:
        return {"display": "block"}
    return {"display": "none"}

# Callback to display table structure information
@callback(
    Output("table-structure-info", "children"),
    Input("upload_table_dropdown", "value")
)
def display_table_structure(selected_table):
    if not selected_table:
        return []
    
    try:
        # Get a sample row to determine columns and types
        schema_df = get_table_schema_preview(selected_table)
        
        # Create table structure information
        structure_info = [
            html.H6("Destination Table Structure", className="section-title"),
            html.P(f"This table has {len(schema_df)} columns. Your CSV must match this order.", className="section-copy"),
            _make_grid(
                schema_df.rename(columns={"COLUMN_NAME": "Column", "DATA_TYPE": "Data Type"}),
                "upload-schema-grid",
                height=280,
            ),
        ]
        
        return html.Div(structure_info, className="panel-card")
    except DatabaseAccessError as e:
        logger.exception("Unable to load upload table structure for %s", selected_table)
        return _status("Table structure is unavailable right now. Choose another table or try again later.", "warning", "Table structure unavailable")

# Function to parse CSV content
def parse_csv(contents):
    if contents is None:
        return None, None
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    
    try:
        decoded_text = decoded.decode('utf-8-sig')
        df = pd.read_csv(io.StringIO(decoded_text))
        if df.empty:
            return None, "The CSV was read successfully but contains no data rows."
        return df, None
    except Exception as e:
        logger.exception("Unable to parse uploaded CSV")
        return None, "The CSV could not be read. Confirm it is a valid comma-separated file with a header row."

# Callback to validate CSV file and display preview
@callback(
    [Output("csv-preview", "children"),
     Output("upload-status", "children"),
     Output("upload-button", "disabled")],
    [Input("upload-csv", "contents"),
     Input("upload_table_dropdown", "value")],
    [State("upload-csv", "filename")]
)
def validate_and_preview_csv(contents, selected_table, filename):
    if contents is None or selected_table is None:
        return [], [], True
    
    try:
        table_columns = get_table_columns(selected_table)
        
        # Parse the uploaded CSV
        df, error = parse_csv(contents)
        if error:
            return [], _status(error, "error", "CSV could not be read"), True
        
        # Verify column names and order match. The database insert maps by name now,
        # so this prevents silent misloads when a same-width CSV is arranged differently.
        if len(df.columns) != len(table_columns):
            return get_preview_table(df), html.Div([
                html.H6("Validation Error", className="section-title"),
                html.P(
                    f"{filename or 'This CSV'} has {len(df.columns)} columns, but '{selected_table}' expects {len(table_columns)}.",
                    className="section-copy",
                ),
                html.P("Column counts must match to proceed.", className="section-copy"),
                html.P(f"Expected order: {', '.join(table_columns)}", className="section-copy")
            ], className="status-error"), True
        if list(df.columns) != table_columns:
            return get_preview_table(df), html.Div([
                html.H6("Validation Error", className="section-title"),
                html.P("Column names and order must match the destination table before upload.", className="section-copy"),
                html.P(f"Expected order: {', '.join(table_columns)}", className="section-copy"),
                html.P(f"Uploaded order: {', '.join(map(str, df.columns))}", className="section-copy")
            ], className="status-error"), True
        
        missing_rows = int(df.isnull().any(axis=1).sum())
        if missing_rows > 0:
            warning = html.Div([
                html.H6("Ready with Warnings", className="section-title"),
                html.P(
                    f"{filename or 'This CSV'} has {missing_rows} row(s) with missing values. Empty cells will be uploaded as NULL.",
                    className="section-copy",
                ),
                html.P(f"Expected destination columns: {', '.join(table_columns)}", className="section-copy"),
                html.P("Preview below shows data as it will be uploaded.", className="section-copy")
            ], className="status-warning")
        else:
            warning = html.Div([
                html.H6("Ready to Upload", className="section-title"),
                html.P(f"{filename or 'This CSV'} with {len(df)} rows is ready for '{selected_table}'.", className="section-copy"),
                html.P(f"Expected destination columns: {', '.join(table_columns)}", className="section-copy")
            ], className="status-success")
        
        return get_preview_table(df), warning, False
        
    except DatabaseAccessError as e:
        logger.exception("Unable to validate upload for %s", selected_table)
        return [], _status("Validation is unavailable right now. Try another table or try again later.", "warning", "Validation unavailable"), True

# Helper function to create preview table
def get_preview_table(df):
    preview_rows = min(5, len(df))
    df_preview = df.head(preview_rows)
    
    return [
        html.Div(
            [
                html.H6("CSV Preview", className="section-title"),
                html.P(f"Showing first {preview_rows} of {len(df)} rows.", className="section-copy"),
                _make_simple_table(df_preview),
            ],
            className="panel-card",
        )
    ]
# Callback to handle database upload
@callback(
    Output("upload-result", "children"),
    [Input("upload-button", "n_clicks")],
    [State("upload-csv", "contents"),
     State("upload_table_dropdown", "value"),
     State("upload-csv", "filename")]
)
def upload_to_database(n_clicks, contents, selected_table, filename):
    if not n_clicks or contents is None or selected_table is None:
        raise PreventUpdate
    
    try:
        df, error = parse_csv(contents)
        if error:
            return _status(error, "error", "Upload Error")
        
        uploaded_rows = append_dataframe_to_table(selected_table, df)
        
        return html.Div([
            html.H6("Upload Successful", className="section-title"),
            html.P(
                f"Successfully uploaded {uploaded_rows} rows from '{filename or 'uploaded file'}' to '{selected_table}'.",
                className="section-copy",
            )
        ], className="status-success")
        
    except DatabaseAccessError as e:
        logger.exception("Unable to upload CSV to %s", selected_table)
        return _status("Upload failed before rows were added. Check that the file still matches the destination table and try again.", "error", "Upload Error")

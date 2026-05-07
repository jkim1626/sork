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
    append_dataframe_to_holding_table,
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


def _schema_for_display(schema_df):
    df = schema_df.copy()
    if df.empty:
        return pd.DataFrame(columns=["Position", "Column", "Type", "Required", "Structure"])

    def format_type(row):
        dtype = str(row.get("DATA_TYPE", ""))
        max_len = row.get("CHARACTER_MAXIMUM_LENGTH")
        precision = row.get("NUMERIC_PRECISION")
        scale = row.get("NUMERIC_SCALE")
        if dtype.lower() in {"varchar", "nvarchar", "char", "nchar", "binary", "varbinary"} and pd.notna(max_len):
            length = "max" if int(max_len) == -1 else str(int(max_len))
            return f"{dtype}({length})"
        if dtype.lower() in {"decimal", "numeric"} and pd.notna(precision):
            return f"{dtype}({int(precision)},{int(scale or 0)})"
        return dtype

    display = pd.DataFrame(
        {
            "Position": df["ORDINAL_POSITION"] if "ORDINAL_POSITION" in df.columns else range(1, len(df) + 1),
            "Column": df["COLUMN_NAME"],
            "Type": df.apply(format_type, axis=1),
            "Required": df.get("IS_NULLABLE", pd.Series(["YES"] * len(df))).map(lambda v: "Yes" if str(v).upper() == "NO" else "No"),
            "Notes": df.get("SCHEMA_SOURCE", pd.Series(["INFORMATION_SCHEMA"] * len(df))).map(
                lambda source: "Type metadata unavailable; column name/order verified from source table."
                if source == "SOURCE_PREVIEW"
                else "Keep this exact Excel header and column order."
            ),
        }
    )
    return display


def _build_template_workbook(selected_table, schema_df):
    columns = schema_df["COLUMN_NAME"].tolist()
    schema_display = _schema_for_display(schema_df)
    readme = pd.DataFrame(
        [
            {"Item": "Target source table", "Value": selected_table},
            {"Item": "Required format", "Value": ".xlsx workbook with a Data sheet"},
            {"Item": "Review flow", "Value": "Rows are staged for review and are not written directly to source tables."},
        ]
    )
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(columns=columns).to_excel(writer, index=False, sheet_name="Data")
        schema_display.to_excel(writer, index=False, sheet_name="Schema")
        readme.to_excel(writer, index=False, sheet_name="README")
    output.seek(0)
    return output.getvalue()

upload_layout = dcc.Tab(
    [
        # Store the tab's active state
        dcc.Store(id="upload-tab-active", data=False),
        html.Div(
            [
                html.H4("Upload Data", className="page-title"),
                html.P(
                    "Upload Excel rows for review. Use the template so columns match the selected table.",
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
                        html.P("Choose the table format your workbook should follow.", className="section-copy"),
                    ],
                    className="panel-card upload-target-panel",
                ),
                html.Div(
                    [
                        html.Div(
                            [
                                html.H6("Excel File", className="section-title"),
                                html.P("Use a .xlsx workbook with headers that match the template exactly. The first sheet or a sheet named Data will be parsed.", className="section-copy"),
                                dcc.Upload(
                                    id='upload-csv',
                                    children=html.Div("Drop an .xlsx file here or select one"),
                                    className="upload-dropzone",
                                    multiple=False,
                                ),
                            ],
                            className="panel-card",
                        ),
                        html.Div(
                            [
                                html.Button("Download .xlsx Template", id="upload-template-button", n_clicks=0, className="btn btn-outline-secondary"),
                                dcc.Download(id="upload-template-download"),
                            ],
                            className="button-row",
                        ),
                        html.Div(id="table-structure-info"),
                        html.Div(id="upload-status"),
                        html.Div(id="csv-preview"),
                        html.Div(
                            [
                                html.Button("Upload to Holding Table", id="upload-button", disabled=True, className="btn btn-success"),
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
        schema_df = get_table_schema_preview(selected_table)
        schema_display = _schema_for_display(schema_df)
        
        structure_info = [
            html.H6("Expected Upload Structure", className="section-title"),
            html.P(
                f"This upload type expects {len(schema_display)} columns. Keep the Excel headers and order exactly as shown.",
                className="section-copy",
            ),
            html.P(
                "If database type metadata is unavailable, the preview still shows the verified source columns and marks type details as unavailable.",
                className="section-copy",
            ),
            html.P(
                "Uploaded rows are staged for review before they are added to source data.",
                className="section-copy",
            ),
            _make_grid(
                schema_display,
                "upload-schema-grid",
                height=340,
            ),
        ]
        
        return html.Div(structure_info, className="panel-card")
    except DatabaseAccessError as e:
        logger.exception("Unable to load upload table structure for %s", selected_table)
        return _status("Table structure is unavailable right now. Choose another table or try again later.", "warning", "Table structure unavailable")

def parse_excel(contents, filename=None):
    if contents is None:
        return None, None
    if not (filename or "").lower().endswith(".xlsx"):
        return None, "Uploads must be Excel .xlsx files. Download the template and save your rows as .xlsx before uploading."

    content_type, content_string = contents.split(',', 1)
    decoded = base64.b64decode(content_string)
    
    try:
        workbook = pd.ExcelFile(io.BytesIO(decoded), engine="openpyxl")
        sheet_name = "Data" if "Data" in workbook.sheet_names else workbook.sheet_names[0]
        df = pd.read_excel(workbook, sheet_name=sheet_name)
        df = df.dropna(how="all")
        if df.empty:
            return None, "The Excel workbook was read successfully but contains no data rows."
        return df, None
    except Exception as e:
        logger.exception("Unable to parse uploaded Excel workbook")
        return None, "The Excel file could not be read. Confirm it is a valid .xlsx workbook with a header row."

# Callback to validate Excel file and display preview
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
        
        df, error = parse_excel(contents, filename)
        if error:
            return [], _status(error, "error", "Excel file could not be read"), True
        
        # Verify column names and order match. The database insert maps by name now,
        # so this prevents silent misloads when a same-width workbook is arranged differently.
        if len(df.columns) != len(table_columns):
            return get_preview_table(df), html.Div([
                html.H6("Validation Error", className="section-title"),
                html.P(f"{filename or 'This workbook'} has {len(df.columns)} columns, but '{selected_table}' expects {len(table_columns)}.", className="section-copy"),
                html.P("Column counts must match to proceed.", className="section-copy"),
                html.P(f"Expected order: {', '.join(table_columns)}", className="section-copy")
            ], className="status-error"), True
        if list(df.columns) != table_columns:
            return get_preview_table(df), html.Div([
                html.H6("Validation Error", className="section-title"),
                html.P("Column names and order must match the template before upload.", className="section-copy"),
                html.P(f"Expected order: {', '.join(table_columns)}", className="section-copy"),
                html.P(f"Uploaded order: {', '.join(map(str, df.columns))}", className="section-copy")
            ], className="status-error"), True
        
        missing_rows = int(df.isnull().any(axis=1).sum())
        if missing_rows > 0:
            warning = html.Div([
                html.H6("Ready with Warnings", className="section-title"),
                html.P(
                    f"{filename or 'This workbook'} has {missing_rows} row(s) with missing values. Empty cells will be uploaded as NULL.",
                    className="section-copy",
                ),
                html.P(f"Expected destination columns: {', '.join(table_columns)}", className="section-copy"),
                html.P("Preview below shows the rows that will be staged for review.", className="section-copy")
            ], className="status-warning")
        else:
            warning = html.Div([
                html.H6("Ready to Upload", className="section-title"),
                html.P(f"{filename or 'This workbook'} with {len(df)} rows is ready to stage for review.", className="section-copy"),
                html.P(f"Expected source columns: {', '.join(table_columns)}", className="section-copy")
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
                html.H6("Excel Preview", className="section-title"),
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
        df, error = parse_excel(contents, filename)
        if error:
            return _status(error, "error", "Upload Error")
        
        upload_result = append_dataframe_to_holding_table(selected_table, df, filename=filename)
        
        return html.Div([
            html.H6("Upload Staged", className="section-title"),
            html.P(
                f"Staged {upload_result['rows']} rows from '{filename or 'uploaded file'}' for review.",
                className="section-copy",
            ),
        ], className="status-success")
        
    except DatabaseAccessError as e:
        logger.exception("Unable to stage Excel upload for %s", selected_table)
        return _status("Upload failed before rows were staged. Check that the workbook still matches the template and try again.", "error", "Upload Error")


@callback(
    Output("upload-template-download", "data"),
    Input("upload-template-button", "n_clicks"),
    State("upload_table_dropdown", "value"),
    prevent_initial_call=True,
)
def download_upload_template(n_clicks, selected_table):
    if not n_clicks or not selected_table:
        raise PreventUpdate

    try:
        schema_df = get_table_schema_preview(selected_table)
        workbook_bytes = _build_template_workbook(selected_table, schema_df)
        filename = f"{selected_table}_upload_template.xlsx"
        return dcc.send_bytes(
            workbook_bytes,
            filename,
            type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except DatabaseAccessError:
        logger.exception("Unable to generate upload template for %s", selected_table)
        raise PreventUpdate

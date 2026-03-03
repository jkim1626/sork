from dash import dcc, html, Input, Output, State, callback, callback_context, dash_table, Patch, no_update
import plotly.graph_objects as go
import pandas as pd
from dotenv import load_dotenv
import os
from database import fetch_data_from_sql

# Load environment variables
load_dotenv(override=True)
map_table = os.getenv("MAP_TABLE")

# User can filter trees by accession/sample ID - public querying data
SEARCH_ID_COLUMNS = [
    {'label': ' Accession', 'value': 'Accession'},
    {'label': ' Sample ID', 'value': 'sample_id'},
]

UCLA_coordinates = {
    "latitude": 34.0682,
    "longitude": -118.4455
}

map_layout = dcc.Tab(
    id="maps-tab",
    value="map-tab",
    children=[
        html.Br(),
        html.H4("Maternal Tree Locations", style={"marginBottom": "5px"}),
        html.P("Click on a tree site to see details about the trees at that location.",
               style={"fontSize": "0.9em", "color": "#666", "marginBottom": "15px"}),
        
        html.Div([
            html.Div([
                # Header for the map
                html.Div([
                    html.Button("Reset View", id="reset-map", 
                               style={
                                   "backgroundColor": "#e9ebe8",
                                   "color": "white",
                                   "border": "1px solid #133817",
                                   "borderRadius": "4px",
                                   "padding": "5px 10px",
                                   "marginRight": "10px"
                               }),
                ], style={"marginBottom": "15px"}),
                
                # track clicked data
                dcc.Store(id='stored-click-data', data=None),
                dcc.Store(id='click-result-store', data=None),
                dcc.Store(id='search-result-store', data=None),
                dcc.Download(id='click-download-csv'),
                dcc.Download(id='search-download-csv'),

                # The map itself
                dcc.Graph(
                    id='california-map',
                    style={'height': '70vh'},
                    config={
                        'scrollZoom': True,
                        'displayModeBar': True,
                        'modeBarButtonsToRemove': ['lasso2d']
                    }
                ),
                
                # Instructions for interacting with the map
                html.Div([
                    html.P([
                        html.Strong("Map Navigation:"),
                        html.Br(),
                        "• Use the mouse wheel or pinch gesture to zoom in/out",
                        html.Br(),
                        "• Click and drag to pan the map",
                        html.Br(),
                        "• Click 'Reset View' to return to the default view of California",
                        html.Br(),
                        "• Click the camera icon on the top right to download the plot",
                        html.Br(),
                    ], style={"fontSize": "0.9em", "color": "#666"})
                ], style={"marginTop": "15px"})
            ], className="col-12")
        ], className="row"),

        # Search panel
        html.Br(),
        html.Div([
            html.H5("Search Trees by ID", style={"marginBottom": "12px"}),
            dcc.RadioItems(
                id='search-id-type',
                options=SEARCH_ID_COLUMNS,
                value=SEARCH_ID_COLUMNS[0]['value'],
                inline=True,
                style={"marginBottom": "10px"}
            ),
            dcc.Textarea(
                id='search-ids-input',
                placeholder='Paste IDs here, one per line or comma-separated...',
                style={
                    'width': '100%', 'height': '80px',
                    'marginBottom': '10px', 'fontFamily': 'monospace',
                    'borderRadius': '4px', 'border': '1px solid #ccc', 'padding': '6px'
                }
            ),
            html.Button('Search', id='search-trees-btn', n_clicks=0, style={
                'backgroundColor': '#4a7c59', 'color': 'white',
                'border': 'none', 'borderRadius': '4px',
                'padding': '6px 16px', 'marginRight': '8px', 'cursor': 'pointer'
            }),
            html.Button('Clear Table', id='clear-search-btn', n_clicks=0, style={
                'backgroundColor': '#e9ebe8', 'color': '#333',
                'border': '1px solid #aaa', 'borderRadius': '4px',
                'padding': '6px 16px', 'cursor': 'pointer',
                'display': 'none'
            }),
        ], style={
            "marginTop": "10px", "padding": "15px",
            "backgroundColor": "#f8f9fa", "borderRadius": "8px",
            "border": "1px solid #dee2e6"
        }),

        # Search results
        html.Div(id='search-results-data', style={"marginTop": "15px", "width": "100%"}),

        # Section for displaying the trees at each tree site
        html.Div(id='individual-tree-data', style={"marginTop": "15px", "width": "100%"}),
    ],
    label="Tree Sites",
    style={"padding": "15px"}
)

# Callback to handle both map updates and click data
@callback(
    [Output('california-map', 'figure'),
     Output('stored-click-data', 'data')],
    [Input('reset-map', 'n_clicks'),
     Input('california-map', 'clickData')]
)
def update_map_and_click_data(reset_clicks, clickData):
    # Determine which input triggered the callback
    ctx = callback_context
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
    
    # Create the base map figure
    fig = go.Figure()

    # Fetch coordinates and tree counts for map
    locations_df = fetch_data_from_sql(f"""
        SELECT locality_full_name,
               AVG(Longitude) AS avg_longitude,
               AVG(Latitude) AS avg_latitude,
               COUNT(*) AS tree_count
        FROM dbo.[{map_table}]
        GROUP BY locality_full_name
    """)

    lon_list = locations_df['avg_longitude'].tolist()
    lat_list = locations_df['avg_latitude'].tolist()
    text_list = locations_df['locality_full_name'].tolist()
    counts = locations_df['tree_count'].tolist()

    # Scale marker sizes based on tree count
    min_size, max_size = 3, 30
    min_count, max_count = min(counts), max(counts)
    if min_count == max_count:
        sizes = [15] * len(counts)
    else:
        sizes = [
            min_size + (c - min_count) / (max_count - min_count) * (max_size - min_size)
            for c in counts
        ]

    hover_text = [f"{name}<br>{count} trees" for name, count in zip(text_list, counts)]

    # Garden markers sized by tree count
    fig.add_trace(go.Scattermapbox(
        mode="markers+text",
        lon=lon_list,
        lat=lat_list,
        text=text_list,
        customdata=text_list,
        textposition="top right",
        marker={'size': sizes, 'color': '#2e7d32'},
        hovertext=hover_text,
        hoverinfo='text',
        name="Planting Sites"
    ))

    # UCLA marker, color in yellow
    fig.add_trace(go.Scattermapbox(
        mode="markers+text",
        lon=[UCLA_coordinates['longitude']],
        lat=[UCLA_coordinates['latitude']],
        text=["University of California, Los Angeles (UCLA)"],
        textposition="top right",
        marker={'size': 14, 'color': '#FFB300'},
        hoverinfo='text',
        name="UCLA"
    ))

    # Placeholder trace for individual trees (populated when zoomed in)
    fig.add_trace(go.Scattermapbox(
        mode="markers",
        lon=[],
        lat=[],
        marker={'size': 7, 'color': '#e53935'},
        hoverinfo='text',
        hovertext=[],
        name="Individual Trees"
    ))

    # Placeholder trace for search results (populated on search)
    fig.add_trace(go.Scattermapbox(
        mode="markers",
        lon=[],
        lat=[],
        marker={'size': 14, 'color': '#9c27b0', 'symbol': 'circle'},
        hoverinfo='text',
        hovertext=[],
        name="Search Results"
    ))

    # Set up the map layout
    fig.update_layout(
        mapbox={
            'style': 'open-street-map',  
            'center': {'lon': -119.5, 'lat': 37.5},  # Center of California
            'zoom': 5  # Default zoomed in view
        },
        margin={'l': 0, 'r': 0, 't': 0, 'b': 0},
        height=600,
        paper_bgcolor="#e5ecf6",
        plot_bgcolor="#e5ecf6"
    )
    
    # Update click data when map is clicked (don't rebuild entire map)
    if trigger_id == 'california-map':
        return no_update, clickData
    
    # If reset button was clicked or initial load, return the figure with no click data
    return fig, None

# Display information about the clicked tree site
_CLEAR_BTN_VISIBLE = {
    'backgroundColor': '#e9ebe8', 'color': '#333',
    'border': '1px solid #aaa', 'borderRadius': '4px',
    'padding': '6px 16px', 'cursor': 'pointer', 'display': 'inline-block'
}
_CLEAR_BTN_HIDDEN = {**_CLEAR_BTN_VISIBLE, 'display': 'none'}

_DOWNLOAD_BTN_STYLE = {
    'backgroundColor': '#4a7c59', 'color': 'white',
    'border': 'none', 'borderRadius': '4px',
    'padding': '5px 14px', 'cursor': 'pointer',
    'fontSize': '0.85em', 'marginBottom': '12px'
}

@callback(
    [Output('individual-tree-data', 'children'),
     Output('click-result-store', 'data')],
    [Input('stored-click-data', 'data')]
)
def display_click_data(clickData):
    if clickData and 'points' in clickData and len(clickData['points']) > 0:
        try:
            point = clickData['points'][0]
            curve = point.get('curveNumber', 0)

            columns = fetch_data_from_sql(f"SELECT TOP 1 * FROM dbo.[{map_table}]").columns.tolist()
            columns_string = ', '.join(columns)

            if curve == 2:
                lat, lon, locality_name = point.get('customdata')
                df = fetch_data_from_sql(
                    f"SELECT {columns_string} FROM dbo.[{map_table}] WHERE Latitude = {lat} AND Longitude = {lon}"
                )
                header_text = f"Tree at {locality_name}"
                subheader = None
                filename = f"tree_{locality_name.replace(' ', '_')}.csv"
            else:
                locality_name = point['text']
                df = fetch_data_from_sql(
                    f"SELECT {columns_string} FROM dbo.[{map_table}] WHERE locality_full_name = '{locality_name}'"
                )
                header_text = f"Trees at {locality_name}"
                subheader = f"Found {len(df)} trees at this location"
                filename = f"trees_{locality_name.replace(' ', '_')}.csv"

            if df.empty:
                return html.Div([
                    html.H5("No data available", style={"marginBottom": "10px", "color": "#dc3545"})
                ]), None

            store_data = {'records': df.to_dict('records'), 'filename': filename}

            return html.Div([
                html.Div([
                    html.H5(header_text, style={
                        "display": "inline-block",
                        "backgroundColor": "#72b7eb",
                        "color": "white",
                        "padding": "10px",
                        "borderRadius": "5px",
                        "marginRight": "12px",
                        "marginBottom": "15px",
                    }),
                    html.Button("Download CSV", id='click-download-btn',
                                n_clicks=0, style=_DOWNLOAD_BTN_STYLE),
                ]),
                html.P(subheader, style={"fontWeight": "bold", "marginBottom": "15px"}) if subheader else None,
                dash_table.DataTable(
                    id='tree-data-table',
                    columns=[{"name": col, "id": col} for col in df.columns],
                    data=df.to_dict('records'),
                    style_table={'overflowX': 'auto', 'width': '100%'},
                    style_cell={'textAlign': 'left', 'padding': '8px', 'whiteSpace': 'normal', 'height': 'auto'},
                    style_header={'backgroundColor': '#f8f9fa', 'fontWeight': 'bold', 'borderBottom': '2px solid #dee2e6'},
                    style_data_conditional=[{'if': {'row_index': 'odd'}, 'backgroundColor': '#f2f2f2'}],
                    page_size=10,
                ),
            ]), store_data
        except Exception as e:
            return html.Div([
                html.H5("Error retrieving data", style={"color": "#dc3545"}),
                html.P(f"An error occurred: {str(e)}")
            ]), None

    return html.P("Click on a tree site to see details about the trees at that location.",
                  style={"fontSize": "0.9em", "color": "#666"}), None


INDIVIDUAL_TREE_ZOOM_THRESHOLD = 12 # zoom level at which to show individual trees

@callback(
    Output('california-map', 'figure', allow_duplicate=True),
    Input('california-map', 'relayoutData'),
    prevent_initial_call=True
)
def toggle_individual_trees(relayoutData):
    if not relayoutData:
        return no_update

    zoom = relayoutData.get('mapbox.zoom')
    if zoom is None:
        return no_update

    patched_fig = Patch()

    if zoom >= INDIVIDUAL_TREE_ZOOM_THRESHOLD:
        # fetch individual tree data when zoomed in
        trees_df = fetch_data_from_sql(f"""
            SELECT Latitude, Longitude, locality_full_name, Accession
            FROM dbo.[{map_table}]
            WHERE Latitude IS NOT NULL AND Longitude IS NOT NULL
        """)

        # hover text for individual trees should show locality and accession
        hover = []
        for _, row in trees_df.iterrows():
            hover.append(f"{row['locality_full_name']}<br>Accession: {row['Accession']}")

        patched_fig['data'][2]['lat'] = trees_df['Latitude'].tolist()
        patched_fig['data'][2]['lon'] = trees_df['Longitude'].tolist()
        patched_fig['data'][2]['hovertext'] = hover
        patched_fig['data'][2]['customdata'] = list(zip(
            trees_df['Latitude'], trees_df['Longitude'], trees_df['locality_full_name']
        ))
    else:
        # clear data when zoomed out
        patched_fig['data'][2]['lat'] = []
        patched_fig['data'][2]['lon'] = []
        patched_fig['data'][2]['hovertext'] = []
        patched_fig['data'][2]['customdata'] = [[]]

    return patched_fig

# use in callback to make table from the searched trees df
def _make_table(df):
    return dash_table.DataTable(
        columns=[{"name": col, "id": col} for col in df.columns],
        data=df.to_dict('records'),
        style_table={'overflowX': 'auto', 'width': '100%'},
        style_cell={'textAlign': 'left', 'padding': '8px', 'whiteSpace': 'normal', 'height': 'auto'},
        style_header={'backgroundColor': '#f8f9fa', 'fontWeight': 'bold', 'borderBottom': '2px solid #dee2e6'},
        style_data_conditional=[{'if': {'row_index': 'odd'}, 'backgroundColor': '#f2f2f2'}],
        page_size=10,
    )


@callback(
    [Output('california-map', 'figure', allow_duplicate=True),
     Output('search-results-data', 'children'),
     Output('search-result-store', 'data'),
     Output('clear-search-btn', 'style')],
    [Input('search-trees-btn', 'n_clicks'),
     Input('clear-search-btn', 'n_clicks')],
    [State('search-ids-input', 'value'),
     State('search-id-type', 'value')],
    prevent_initial_call=True
)
def search_trees(search_clicks, clear_clicks, input_text, id_type):
    ctx = callback_context
    trigger = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None

    patched_fig = Patch()

    if trigger == 'clear-search-btn':
        patched_fig['data'][3]['lat'] = []
        patched_fig['data'][3]['lon'] = []
        patched_fig['data'][3]['hovertext'] = []
        return patched_fig, html.Div(), None, _CLEAR_BTN_HIDDEN

    if not input_text or not input_text.strip():
        return no_update, html.P("Enter IDs and click Search.", style={"color": "#666", "fontSize": "0.9em"}), no_update, _CLEAR_BTN_HIDDEN

    # Parse and sanitize IDs (strip whitespace, remove single quotes)
    raw_ids = input_text.replace('\n', ',').split(',')
    ids = [i.strip().replace("'", "") for i in raw_ids if i.strip()]

    if not ids:
        return no_update, html.P("No valid IDs entered.", style={"color": "#666", "fontSize": "0.9em"}), no_update, _CLEAR_BTN_HIDDEN

    ids_sql = ', '.join(f"'{i}'" for i in ids)
    columns = fetch_data_from_sql(f"SELECT TOP 1 * FROM dbo.[{map_table}]").columns.tolist()
    columns_string = ', '.join(columns)

    try:
        df = fetch_data_from_sql(f"""
            SELECT {columns_string}
            FROM dbo.[{map_table}]
            WHERE [{id_type}] IN ({ids_sql})
        """)
    except Exception as e:
        return no_update, html.Div([
            html.H5("Error running search", style={"color": "#dc3545"}),
            html.P(str(e))
        ]), None, _CLEAR_BTN_HIDDEN

    if df.empty:
        patched_fig['data'][3]['lat'] = []
        patched_fig['data'][3]['lon'] = []
        patched_fig['data'][3]['hovertext'] = []
        return patched_fig, html.P(
            f"No trees found for the given {id_type}(s).",
            style={"color": "#dc3545", "fontWeight": "bold"}
        ), None, _CLEAR_BTN_HIDDEN

    # Update search result markers on map (only rows with coordinates)
    map_df = df.dropna(subset=['Latitude', 'Longitude'])
    hover = [f"{row.get('locality_full_name', '')}<br>{id_type}: {row.get(id_type, '')}"
             for _, row in map_df.iterrows()]
    patched_fig['data'][3]['lat'] = map_df['Latitude'].tolist()
    patched_fig['data'][3]['lon'] = map_df['Longitude'].tolist()
    patched_fig['data'][3]['hovertext'] = hover

    store_data = {'records': df.to_dict('records'), 'filename': 'search_results.csv'}

    return patched_fig, html.Div([
        html.Div([
            html.H5(f"Search Results — {len(df)} tree(s) found", style={
                "display": "inline-block",
                "backgroundColor": "#7b1fa2",
                "color": "white", "padding": "10px", "borderRadius": "5px",
                "marginRight": "12px", "marginBottom": "15px",
            }),
            html.Button("Download CSV", id='search-download-btn',
                        n_clicks=0, style=_DOWNLOAD_BTN_STYLE),
        ]),
        _make_table(df),
    ]), store_data, _CLEAR_BTN_VISIBLE


@callback(
    Output('click-download-csv', 'data'),
    Input('click-download-btn', 'n_clicks'),
    State('click-result-store', 'data'),
    prevent_initial_call=True
)
def download_click_csv(n_clicks, store_data):
    if not n_clicks or not store_data:
        return no_update
    df = pd.DataFrame(store_data['records'])
    return dcc.send_data_frame(df.to_csv, store_data['filename'], index=False)


@callback(
    Output('search-download-csv', 'data'),
    Input('search-download-btn', 'n_clicks'),
    State('search-result-store', 'data'),
    prevent_initial_call=True
)
def download_search_csv(n_clicks, store_data):
    if not n_clicks or not store_data:
        return no_update
    df = pd.DataFrame(store_data['records'])
    return dcc.send_data_frame(df.to_csv, store_data['filename'], index=False)
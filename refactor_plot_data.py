import re

# Load the file
with open("tabs/joins.py", "r") as f:
    content = f.read()

# 1. Update stat_test_options inline array 
search_str = """stat_test_options = [
    {'label': 'Linear Regression', 'value': 'linear_regression'},
    {'label': 'Principal Component Analysis (PCA)', 'value': 'pca'},
    {'label': 'Summary Statistics', 'value': 'summary_stats'}
]"""
replace_str = """stat_test_options = [
    {'label': 'Linear Regression', 'value': 'linear_regression'},
    {'label': 'Principal Component Analysis (PCA)', 'value': 'pca'},
    {'label': 'Summary Statistics', 'value': 'summary_stats'},
    {'label': 'Plot Data (No Test)', 'value': 'plot_data'}
]"""
content = content.replace(search_str, replace_str)


# 2. Add plotting layout within test-container
layout_search = """                        # Summary Statistics"""
layout_replace = """                        # Plot Data (No Test)
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
                        
                        # Summary Statistics"""

content = content.replace(layout_search, layout_replace)

# 3. Add to populate_stats_options callback signatures
pop_search = """     Output("summary-variable", "options"),
     Output("stats-test-dropdown", "value"),
     Output("lr-x-variable", "value"),
     Output("lr-y-variable", "value"),
     Output("pca-variables", "value"),
     Output("summary-variable", "value"),
     Output("lr-output-content", "children", allow_duplicate=True),
     Output("pca-output-content", "children", allow_duplicate=True),
     Output("summary-output-content", "children", allow_duplicate=True)],"""

pop_replace = """     Output("summary-variable", "options"),
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
     Output("pd-output-content", "children", allow_duplicate=True)],"""

content = content.replace(pop_search, pop_replace)

pop_allcols_search = """    for c in df.columns:
        if c == '__select__':
            continue"""

pop_allcols_replace = """    all_options = []
    for c in df.columns:
        if c == '__select__':
            continue
        all_options.append({"label": c, "value": c})"""

content = content.replace(pop_allcols_search, pop_allcols_replace)

pop_ret_search = """        options, options, options, options,
        None, None, None, None, None,
        html.Div(), html.Div(), html.Div()"""

pop_ret_replace = """        options, all_options, all_options,
        None, None, None, None, None, None, None,
        html.Div(), html.Div(), html.Div(), html.Div()"""
content = content.replace(pop_ret_search, pop_ret_replace)

# 4. show_test_container
show_search = """    [Output("test-container", "style", allow_duplicate=True),
     Output("linear-regression-div", "style"),
     Output("pca-div", "style"),
     Output("summary-stats-div", "style"),
     Output('lr-output-content', 'children', allow_duplicate=True),
     Output('pca-output-content', 'children', allow_duplicate=True),
     Output('summary-output-content', 'children', allow_duplicate=True)],
    [Input("stats-test-dropdown", "value")],"""

show_replace = """    [Output("test-container", "style", allow_duplicate=True),
     Output("linear-regression-div", "style"),
     Output("pca-div", "style"),
     Output("summary-stats-div", "style"),
     Output("plot-data-div", "style"),
     Output('lr-output-content', 'children', allow_duplicate=True),
     Output('pca-output-content', 'children', allow_duplicate=True),
     Output('summary-output-content', 'children', allow_duplicate=True),
     Output('pd-output-content', 'children', allow_duplicate=True)],
    [Input("stats-test-dropdown", "value")],"""
content = content.replace(show_search, show_replace)

show_logic_search = """    if not selected_test:
        return {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}, empty_output, empty_output, empty_output
    
    lr_style = {"display": "block"} if selected_test == "linear_regression" else {"display": "none"}
    pca_style = {"display": "block"} if selected_test == "pca" else {"display": "none"}
    summary_style = {"display": "block"} if selected_test == "summary_stats" else {"display": "none"}
    
    return {"display": "block"}, lr_style, pca_style, summary_style, empty_output, empty_output, empty_output"""

show_logic_replace = """    if not selected_test:
        return {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}, empty_output, empty_output, empty_output, empty_output
    
    lr_style = {"display": "block"} if selected_test == "linear_regression" else {"display": "none"}
    pca_style = {"display": "block"} if selected_test == "pca" else {"display": "none"}
    summary_style = {"display": "block"} if selected_test == "summary_stats" else {"display": "none"}
    plot_data_style = {"display": "block"} if selected_test == "plot_data" else {"display": "none"}
    
    return {"display": "block"}, lr_style, pca_style, summary_style, plot_data_style, empty_output, empty_output, empty_output, empty_output"""
content = content.replace(show_logic_search, show_logic_replace)

# 5. Add Plot Data functionality 
plot_callback_addition = """
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
"""
content += plot_callback_addition

with open("tabs/joins.py", "w") as f:
    f.write(content)

print("Plot data added to joins.py")

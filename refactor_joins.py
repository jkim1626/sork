import re

with open("tabs/joins.py", "r") as f:
    content = f.read()

# 1. Imports and constants
imports_to_add = """
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
    {'label': 'Summary Statistics', 'value': 'summary_stats'}
]
"""
content = content.replace("from dash_ag_grid import AgGrid\n", "from dash_ag_grid import AgGrid\n" + imports_to_add)

# 2. Change tab label
content = content.replace('label="Table Joins",', 'label="Select and Filter",')

# 3. Add to joins_layout children
layout_addition = """
                # -------------------------------------------------------------
                # Statistical Analysis Section (Appended to Joins Tab)
                # -------------------------------------------------------------
                html.Div([
                    html.H4("Statistical Analysis on Resulting Data", style={"marginBottom": "20px"}),

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
"""
target = 'dcc.Download(id="download-join-tab-all-csv")\n                    ])\n                ])\n            ]\n        )\n    ]\n)'
if target not in content:
    print("Could not find layout target")
content = content.replace(target, 'dcc.Download(id="download-join-tab-all-csv")\n                    ])\n                ]),\n' + layout_addition + '\n            ]\n        )\n    ]\n)')

callbacks_to_add = """

# ====== STATISTICAL CALLBACKS ======

@callback(
    [Output("stats-main-container", "style", allow_duplicate=True),
     Output("lr-x-variable", "options"),
     Output("lr-y-variable", "options"),
     Output("pca-variables", "options"),
     Output("summary-variable", "options"),
     Output("stats-test-dropdown", "value"),
     Output("lr-x-variable", "value"),
     Output("lr-y-variable", "value"),
     Output("pca-variables", "value"),
     Output("summary-variable", "value"),
     Output("lr-output-content", "children", allow_duplicate=True),
     Output("pca-output-content", "children", allow_duplicate=True),
     Output("summary-output-content", "children", allow_duplicate=True)],
    [Input('join-tab-grid', 'rowData')],
    prevent_initial_call=True
)
def populate_stats_options(row_data):
    # This runs when grid row data is first loaded/updated. Let's provide options based on numeric columns in row_data.
    if not row_data:
        return {"display": "none"}, [], [], [], [], None, None, None, None, None, html.Div(), html.Div(), html.Div()
    
    df = pd.DataFrame(row_data)
    numeric_cols = []
    
    for c in df.columns:
        if c == '__select__':
            continue
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
        options, options, options, options,
        None, None, None, None, None,
        html.Div(), html.Div(), html.Div()
    )

@callback(
    [Output("test-container", "style", allow_duplicate=True),
     Output("linear-regression-div", "style"),
     Output("pca-div", "style"),
     Output("summary-stats-div", "style"),
     Output('lr-output-content', 'children', allow_duplicate=True),
     Output('pca-output-content', 'children', allow_duplicate=True),
     Output('summary-output-content', 'children', allow_duplicate=True)],
    [Input("stats-test-dropdown", "value")],
    prevent_initial_call=True
)
def show_test_container(selected_test):
    empty_output = html.Div()
    if not selected_test:
        return {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}, empty_output, empty_output, empty_output
    
    lr_style = {"display": "block"} if selected_test == "linear_regression" else {"display": "none"}
    pca_style = {"display": "block"} if selected_test == "pca" else {"display": "none"}
    summary_style = {"display": "block"} if selected_test == "summary_stats" else {"display": "none"}
    
    return {"display": "block"}, lr_style, pca_style, summary_style, empty_output, empty_output, empty_output

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
    df = fetch_data_from_sql(query)
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

"""
content += callbacks_to_add

with open("tabs/joins.py", "w") as f:
    f.write(content)

print("joins.py updated successfully.")

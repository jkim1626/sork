from dash import dcc, html, Input, Output, State, callback
import dash
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
from scipy import stats
from database import fetch_data_from_sql
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
import dash_bootstrap_components as dbc
from dotenv import load_dotenv
import os
from cache_config import cache

# Load environment variables
load_dotenv(override=True)

# Table Options
table_options = os.getenv("TABLE_OPTIONS").split(",")


# Statistical test options
stat_test_options = [
    {'label': 'Linear Regression', 'value': 'linear_regression'},
    {'label': 'Principal Component Analysis (PCA)', 'value': 'pca'},
    {'label': 'Summary Statistics', 'value': 'summary_stats'}
]

# Create the layout for the stats tab
stats_layout = dcc.Tab(
    label="Tab 3",
    id="stats-tab",
    style={"padding": "15px"},
    children=[
        # Store the tab's active state
        dcc.Store(id="stats-tab-active", data=False),
        html.Br(),
        html.H4("Statistical Analysis", style={"marginBottom": "20px"}),
        html.Div([
            html.Button("Use Joined Dataset", id="use-joined-button", n_clicks=0),
            dcc.Store(id="use-joined-flag", data=False),  # Flag to track button click
            html.Div(id="joined-dataset-status", style={"marginTop": "10px", "color": "#007bff"})
        ]),
            

        # Table selection
        html.Label("Step 1: Select a table", style={"fontWeight": "bold", "marginBottom": "5px", "fontSize": "16px"}), 
        dcc.Dropdown(table_options, id="stats-table-dropdown", placeholder="Select a table"),
        
        # Test selection
        html.Div([
            html.Label("Step 2: Select analysis type", style={"fontWeight": "bold", "marginTop": "20px", "marginBottom": "5px", "fontSize": "16px"}),
            dcc.Dropdown(stat_test_options, id="stats-test-dropdown", placeholder="Select statistical test"),
        ], id="test-selection-div", style={"display": "none"}),
        
        # Containers for each test type
        html.Div([
            # Linear Regression
            html.Div([
                html.Label("Step 3: Select variables for Linear Regression", style={"fontWeight": "bold", "marginTop": "20px", "marginBottom": "5px"}),
                html.Div([
                    html.Label("X-axis (independent variable):", style={"marginRight": "10px"}),
                    dcc.Dropdown(id="lr-x-variable", placeholder="Select x variable"),
                ], style={"marginBottom": "10px"}),
                html.Div([
                    html.Label("Y-axis (dependent variable):", style={"marginRight": "10px"}),
                    dcc.Dropdown(id="lr-y-variable", placeholder="Select y variable"),
                ], style={"marginBottom": "10px"}),
                html.Button("Generate Regression", id="run-lr-button", 
                           style={
                               "backgroundColor": "#007bff",
                               "color": "white",
                               "border": "none",
                               "borderRadius": "4px",
                               "padding": "5px 15px",
                               "marginTop": "10px"
                           }),
                html.Div(id="lr-output", style={"marginTop": "20px"})
            ], id="linear-regression-div", style={"display": "none"}),
            
            # PCA
            html.Div([
                html.Label("Step 3: Select variables for PCA", style={"fontWeight": "bold", "marginTop": "20px", "marginBottom": "5px"}),
                html.Div([
                    html.Label("Select numeric columns:", style={"marginRight": "10px"}),
                    dcc.Dropdown(id="pca-variables", placeholder="Select variables", multi=True),
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
                html.Button("Generate PCA", id="run-pca-button", 
                           style={
                               "backgroundColor": "#007bff",
                               "color": "white",
                               "border": "none",
                               "borderRadius": "4px",
                               "padding": "5px 15px",
                               "marginTop": "10px"
                           }),
                html.Div(id="pca-output", style={"marginTop": "20px"})
            ], id="pca-div", style={"display": "none"}),
            
            # Summary Statistics
            html.Div([
                html.Label("Step 3: Select variable for Summary Statistics", style={"fontWeight": "bold", "marginTop": "20px", "marginBottom": "5px"}),
                html.Div([
                    html.Label("Select a numeric column:", style={"marginRight": "10px"}),
                    dcc.Dropdown(id="summary-variable", placeholder="Select variable"),
                ], style={"marginBottom": "10px"}),
                html.Button("Generate Summary", id="run-summary-button", 
                           style={
                               "backgroundColor": "#007bff",
                               "color": "white",
                               "border": "none",
                               "borderRadius": "4px",
                               "padding": "5px 15px",
                               "marginTop": "10px"
                           }),
                html.Div(id="summary-output", style={"marginTop": "20px"})
            ], id="summary-stats-div", style={"display": "none"}),
            
        ], id="test-container", style={"display": "none"}),
        
        # Placeholder message
        html.Div(id="stats-placeholder", children=[
            html.Div(
                html.H5("Select a table and analysis type to begin", 
                        style={"textAlign": "center", "marginTop": "50px", "color": "#666"})
            )
        ]),
    ]
)

# Track tab selection state
@callback(
    Output('stats-tab-active', 'data'),
    [Input('main-tabs', 'value')]
)
def set_stats_tab_active(tab_value):
    return tab_value == 'stats-tab'

# Reset all components when tab is switched
@callback(
    [Output('stats-table-dropdown', 'value', allow_duplicate=True),
     Output('stats-test-dropdown', 'value', allow_duplicate=True),
     Output('lr-x-variable', 'value', allow_duplicate=True),
     Output('lr-y-variable', 'value', allow_duplicate=True),
     Output('pca-variables', 'value', allow_duplicate=True),
     Output('summary-variable', 'value', allow_duplicate=True),
     Output('lr-output', 'children', allow_duplicate=True),
     Output('pca-output', 'children', allow_duplicate=True),
     Output('summary-output', 'children', allow_duplicate=True)],
    [Input('stats-tab-active', 'data')],
    prevent_initial_call=True
)
def reset_stats_tab_data(is_active):
    if not is_active:
        # Reset all controls when leaving the tab
        return None, None, None, None, None, None, html.Div(), html.Div(), html.Div()
    else:
        # Don't reset when entering the tab
        return [dash.no_update] * 9

# Reset dependent controls when table changes
@callback(
    [Output('stats-test-dropdown', 'value', allow_duplicate=True),
     Output('lr-x-variable', 'value', allow_duplicate=True),
     Output('lr-y-variable', 'value', allow_duplicate=True),
     Output('pca-variables', 'value', allow_duplicate=True),
     Output('summary-variable', 'value', allow_duplicate=True),
     Output('lr-output', 'children', allow_duplicate=True),
     Output('pca-output', 'children', allow_duplicate=True),
     Output('summary-output', 'children', allow_duplicate=True),
     Output('test-selection-div', 'style'),
     Output('test-container', 'style'),
     Output('stats-placeholder', 'style')],
    [Input('stats-table-dropdown', 'value')],
    prevent_initial_call=True
)
def reset_on_table_change(selected_table):
    if selected_table:
        # Reset analysis-related controls but show test selection
        return None, None, None, None, None, html.Div(), html.Div(), html.Div(), {"display": "block"}, {"display": "none"}, {"display": "none"}
    else:
        # Hide everything when no table is selected
        return None, None, None, None, None, html.Div(), html.Div(), html.Div(), {"display": "none"}, {"display": "none"}, {"display": "block"}

# Callback to show appropriate test container based on selection
@callback(
    [Output("test-container", "style", allow_duplicate=True),
     Output("linear-regression-div", "style"),
     Output("pca-div", "style"),
     Output("summary-stats-div", "style"),
     Output('lr-output', 'children', allow_duplicate=True),
     Output('pca-output', 'children', allow_duplicate=True),
     Output('summary-output', 'children', allow_duplicate=True)],
    [Input("stats-test-dropdown", "value")],
    prevent_initial_call=True
)
def show_test_container(selected_test):
    # Reset outputs when test type changes
    empty_output = html.Div()
    
    if not selected_test:
        return {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}, empty_output, empty_output, empty_output
    
    lr_style = {"display": "block"} if selected_test == "linear_regression" else {"display": "none"}
    pca_style = {"display": "block"} if selected_test == "pca" else {"display": "none"}
    summary_style = {"display": "block"} if selected_test == "summary_stats" else {"display": "none"}
    
    return {"display": "block"}, lr_style, pca_style, summary_style, empty_output, empty_output, empty_output

# Function to get numeric columns from a table
def get_numeric_columns(table_name):
    try:
        # Get a sample of data to determine column types
        df = fetch_data_from_sql(f"SELECT TOP 100 * FROM [dbo].[{table_name}]")
        
        # Filter to only numeric columns
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        return numeric_cols
    except Exception as e:
        print(f"Error getting numeric columns: {e}")
        return []

# Callback to populate dropdowns with numeric columns
@callback(
    [Output("lr-x-variable", "options"),
     Output("lr-y-variable", "options"),
     Output("pca-variables", "options"),
     Output("summary-variable", "options")],
    [Input("stats-table-dropdown", "value")], 
    State("joined-dataset-store", "data")
)
def update_variable_options(selected_table, joined_data):
    if not selected_table:
        empty_options = []
        return empty_options, empty_options, empty_options, empty_options
    
    try:
        if selected_table == "__joined__" and joined_data:
            df = pd.DataFrame(cache.get(joined_data))
        else:
            df = fetch_data_from_sql(f"SELECT TOP 100 * FROM [dbo].[{selected_table}]")

        if df is None or df.empty:
            return empty_options, empty_options, empty_options, empty_options
    
        numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
        options = [{"label": col, "value": col} for col in numeric_cols]
        
        return options, options, options, options
    except Exception as e:
        print(f"Error fetching variables: {e}")
        return [], []

# Linear Regression Callback
@callback(
    Output("lr-output", "children", allow_duplicate=True),
    [Input("run-lr-button", "n_clicks")],
    [State("stats-table-dropdown", "value"),
     State("lr-x-variable", "value"),
     State("lr-y-variable", "value"), 
     State("joined-dataset-store", "data")],
     State("use-joined-flag", "data"),
    prevent_initial_call=True
)
def generate_linear_regression(n_clicks, selected_table, x_var, y_var, joined_data, use_joined):
    if n_clicks is None or not selected_table or not x_var or not y_var:
        return html.Div()
    
    try:
        # If join, use cached data
        if use_joined and joined_data:
            cached_df = pd.DataFrame(cache.get(joined_data))
            if cached_df is None:
                return html.Div([
                    html.H5("Cache Miss", style={"color": "red"}),
                    html.P("Cached dataset not found. Please re-run the join or reload data.")
                ])
            df = cached_df[[x_var, y_var]].dropna()
        else:
            # Fetch the data
            query = f"SELECT [{x_var}], [{y_var}] FROM [dbo].[{selected_table}] WHERE [{x_var}] IS NOT NULL AND [{y_var}] IS NOT NULL"
            df = fetch_data_from_sql(query)
        
        # Check if we have enough data
        """if df is None or df.empty:
            return html.Div([
                html.H5("Insufficient Data", style={"color": "red"}),
                html.P("Not enough valid data points for regression analysis.")
            ])"""

        # Calculate regression
        x = df[x_var].values
        y = df[y_var].values
        
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
        
        # Generate prediction line
        x_range = np.linspace(min(x), max(x), 100)
        y_pred = slope * x_range + intercept
        
        # Create the plot
        fig = go.Figure()
        
        # Add scatter plot of data
        fig.add_trace(go.Scatter(
            x=x, 
            y=y, 
            mode='markers',
            name='Data Points',
            marker=dict(
                color='blue',
                opacity=0.6,
                size=8
            )
        ))
        
        # Add regression line
        fig.add_trace(go.Scatter(
            x=x_range,
            y=y_pred,
            mode='lines',
            name='Regression Line',
            line=dict(color='red', width=2)
        ))
        
        # Update layout
        r_squared = r_value**2
        equation = f"y = {slope:.4f}x + {intercept:.4f}"
        
        fig.update_layout(
            title=f"Linear Regression: {y_var} vs {x_var}",
            xaxis_title=x_var,
            yaxis_title=y_var,
            height=500,
            paper_bgcolor="#e5ecf6",
            plot_bgcolor="#f9f9f9",
            annotations=[
                dict(
                    x=0.02,
                    y=0.98,
                    xref="paper",
                    yref="paper",
                    text=f"Equation: {equation}<br>R² = {r_squared:.4f}<br>p-value = {p_value:.4f}",
                    showarrow=False,
                    bgcolor="rgba(255, 255, 255, 0.8)",
                    bordercolor="rgba(0, 0, 0, 0.2)",
                    borderwidth=1,
                    borderpad=10,
                    font=dict(size=12)
                )
            ]
        )
        
        # Add statistics summary
        stats_table = html.Div([
            html.H5("Regression Statistics", style={"marginTop": "20px"}),
            html.Table([
                html.Thead(
                    html.Tr([
                        html.Th("Metric", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                        html.Th("Value", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"})
                    ])
                ),
                html.Tbody([
                    html.Tr([
                        html.Td("Slope", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                        html.Td(f"{slope:.6f}", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"})
                    ]),
                    html.Tr([
                        html.Td("Intercept", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                        html.Td(f"{intercept:.6f}", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"})
                    ]),
                    html.Tr([
                        html.Td("R-squared", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                        html.Td(f"{r_squared:.6f}", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"})
                    ]),
                    html.Tr([
                        html.Td("p-value", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                        html.Td(f"{p_value:.6f}", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"})
                    ]),
                    html.Tr([
                        html.Td("Standard Error", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                        html.Td(f"{std_err:.6f}", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"})
                    ]),
                    html.Tr([
                        html.Td("Sample Size", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                        html.Td(f"{len(df)}", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"})
                    ]),
                ])
            ], style={"borderCollapse": "collapse", "width": "100%", "marginBottom": "20px"})
        ])
        
        return html.Div([
            dcc.Graph(figure=fig),
            stats_table
        ])
    
    except Exception as e:
        return html.Div([
            html.H5("Error", style={"color": "red"}),
            html.P(f"An error occurred: {str(e)}")
        ])
    
# PCA Callback
@callback(
    Output("pca-output", "children", allow_duplicate=True),
    [Input("run-pca-button", "n_clicks")],
    [State("stats-table-dropdown", "value"),
     State("pca-variables", "value"),
     State("pca-dimensions", "value"),
     State("joined-dataset-store", "data")],
    State("use-joined-flag", "data"),
    prevent_initial_call=True
)
def generate_pca(n_clicks, selected_table, variables, dimensions, joined_data, use_joined):
    if n_clicks is None or not selected_table or not variables or len(variables) < 2:
        return html.Div()
    
    try:
        # Fetch the data
        # If join, use cached data
        if use_joined and joined_data:
            cached_df = pd.DataFrame(cache.get(joined_data))
            if cached_df is None:
                return html.Div([
                    html.H5("Cache Miss", style={"color": "red"}),
                    html.P("Cached dataset not found. Please re-run the join or reload data.")
                ])
            df = cached_df
        else:
            columns = ", ".join([f"[{var}]" for var in variables])
            query = f"SELECT {columns} FROM [dbo].[{selected_table}]"
            df = fetch_data_from_sql(query)
        
        # Drop rows with NaN values
        df = df.dropna()
        
        # Check if we have enough data
        if len(df) < 3:
            return html.Div([
                html.H5("Insufficient Data", style={"color": "red"}),
                html.P("Not enough valid data points for PCA analysis.")
            ])
        
        # Scale the data
        scaler = StandardScaler()
        scaled_data = scaler.fit_transform(df)
        
        # Determine number of components
        n_components = min(3, len(variables))
        
        # Perform PCA
        pca = PCA(n_components=n_components)
        pca_result = pca.fit_transform(scaled_data)
        
        # Create a DataFrame with PCA results
        pca_df = pd.DataFrame(
            data=pca_result,
            columns=[f'PC{i+1}' for i in range(n_components)]
        )
        
        # Calculate explained variance
        explained_variance = pca.explained_variance_ratio_ * 100
        
        # Create the plot
        if dimensions == '3d' and n_components >= 3:
            fig = px.scatter_3d(
                pca_df, 
                x='PC1', 
                y='PC2', 
                z='PC3',
                title="3D PCA Visualization",
                labels={
                    'PC1': f'PC1 ({explained_variance[0]:.2f}%)',
                    'PC2': f'PC2 ({explained_variance[1]:.2f}%)',
                    'PC3': f'PC3 ({explained_variance[2]:.2f}%)'
                },
                opacity=0.7
            )
        else:
            fig = px.scatter(
                pca_df, 
                x='PC1', 
                y='PC2',
                title="2D PCA Visualization",
                labels={
                    'PC1': f'PC1 ({explained_variance[0]:.2f}%)',
                    'PC2': f'PC2 ({explained_variance[1]:.2f}%)'
                },
                opacity=0.7
            )
        
        fig.update_layout(
            height=600,
            paper_bgcolor="#e5ecf6",
            plot_bgcolor="#f9f9f9"
        )
        
        # Create loading plot and variance table
        loadings = pca.components_
        loading_df = pd.DataFrame(loadings.T, columns=[f'PC{i+1}' for i in range(n_components)], index=variables)
        
        # Create variance explanation table
        variance_table = html.Div([
            html.H5("Explained Variance", style={"marginTop": "20px"}),
            html.Table([
                html.Thead(
                    html.Tr([
                        html.Th("Component", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                        html.Th("Variance Explained (%)", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                        html.Th("Cumulative Variance (%)", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"})
                    ])
                ),
                html.Tbody([
                    html.Tr([
                        html.Td(f"PC{i+1}", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                        html.Td(f"{explained_variance[i]:.2f}%", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                        html.Td(f"{np.sum(explained_variance[:i+1]):.2f}%", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"})
                    ]) for i in range(n_components)
                ])
            ], style={"borderCollapse": "collapse", "width": "100%", "marginBottom": "20px"})
        ])
        
        # Create loadings table
        loadings_table = html.Div([
            html.H5("Variable Loadings", style={"marginTop": "20px"}),
            html.Table([
                html.Thead(
                    html.Tr([
                        html.Th("Variable", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                    ] + [
                        html.Th(f"PC{i+1}", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"})
                        for i in range(n_components)
                    ])
                ),
                html.Tbody([
                    html.Tr([
                        html.Td(var, style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                    ] + [
                        html.Td(f"{loading_df.loc[var, f'PC{i+1}']:.4f}", 
                                style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"})
                        for i in range(n_components)
                    ]) for var in variables
                ])
            ], style={"borderCollapse": "collapse", "width": "100%", "marginBottom": "20px"})
        ])
        
        return html.Div([
            dcc.Graph(figure=fig),
            variance_table,
            loadings_table
        ])
    
    except Exception as e:
        return html.Div([
            html.H5("Error", style={"color": "red"}),
            html.P(f"An error occurred: {str(e)}")
        ])

# Summary Statistics Callback
@callback(
    Output("summary-output", "children", allow_duplicate=True),
    [Input("run-summary-button", "n_clicks")],
    [State("stats-table-dropdown", "value"),
     State("summary-variable", "value"),
     State("joined-dataset-store", "data")],
    State("use-joined-flag", "data"),
    prevent_initial_call=True
)
def generate_summary_statistics(n_clicks, selected_table, variable, joined_data, use_joined):
    if n_clicks is None or not selected_table or not variable:
        return html.Div()
    
    try:
        if use_joined and joined_data:
            cached_df = pd.DataFrame(cache.get(joined_data))
            if cached_df is None:
                return html.Div([
                    html.H5("Cache Miss", style={"color": "red"}),
                    html.P("Cached dataset not found. Please re-run the join or reload data.")
                ])
            df = cached_df
            if variable not in df.columns:
                return html.Div([
                    html.H5("Column Not Found", style={"color": "red"}),
                    html.P(f"The variable '{variable}' is not in the joined dataset.")
                ])
        else:
            # Fetch the data
            query = f"SELECT [{variable}] FROM [dbo].[{selected_table}] WHERE [{variable}] IS NOT NULL"
            df = fetch_data_from_sql(query)
            
        # Check if we have enough data
        if len(df) < 1:
            return html.Div([
                html.H5("Insufficient Data", style={"color": "red"}),
                html.P("No valid data points for summary statistics.")
            ])
        
        # Calculate statistics
        data = df[variable]
        summary = {
            'Count': len(data),
            'Mean': data.mean(),
            'Median': data.median(),
            'Standard Deviation': data.std(),
            'Minimum': data.min(),
            'Maximum': data.max(),
            '25th Percentile': data.quantile(0.25),
            '75th Percentile': data.quantile(0.75),
            'IQR': data.quantile(0.75) - data.quantile(0.25),
            'Skewness': data.skew(),
            'Kurtosis': data.kurtosis()
        }
        
        # Create box plot
        fig_box = go.Figure()
        fig_box.add_trace(go.Box(
            y=data,
            name=variable,
            boxpoints='all',
            jitter=0.3,
            pointpos=-1.8,
            marker=dict(
                color='blue',
                opacity=0.6,
                size=4
            ),
            line=dict(color='darkblue')
        ))
        
        fig_box.update_layout(
            title=f"Box Plot for {variable}",
            yaxis_title=variable,
            height=400,
            paper_bgcolor="#e5ecf6",
            plot_bgcolor="#f9f9f9",
            margin=dict(l=40, r=40, t=40, b=40)
        )
        
        # Create histogram
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(
            x=data,
            histnorm='probability density',
            name=variable,
            marker=dict(color='darkblue')
        ))
        
        # Add mean and median lines
        fig_hist.add_vline(x=summary['Mean'], line_dash="solid", line_color="red", 
                        annotation_text="Mean", annotation_position="top right")
        fig_hist.add_vline(x=summary['Median'], line_dash="dash", line_color="green", 
                        annotation_text="Median", annotation_position="top left")
        
        fig_hist.update_layout(
            title=f"Distribution of {variable}",
            xaxis_title=variable,
            yaxis_title="Density",
            height=400,
            paper_bgcolor="#e5ecf6",
            plot_bgcolor="#f9f9f9",
            margin=dict(l=40, r=40, t=40, b=40)
        )
        
        # Create summary statistics table
        stats_table = html.Div([
            html.H5("Summary Statistics", style={"marginTop": "20px"}),
            html.Table([
                html.Thead(
                    html.Tr([
                        html.Th("Statistic", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                        html.Th("Value", style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"})
                    ])
                ),
                html.Tbody([
                    html.Tr([
                        html.Td(stat, style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"}),
                        html.Td(f"{value:.6f}" if isinstance(value, float) else f"{value}", 
                                style={"padding": "8px", "textAlign": "left", "borderBottom": "1px solid #ddd"})
                    ]) for stat, value in summary.items()
                ])
            ], style={"borderCollapse": "collapse", "width": "100%", "marginBottom": "20px"})
        ])
        
        return html.Div([
            dcc.Graph(figure=fig_box, style={"marginBottom": "20px"}),
            dcc.Graph(figure=fig_hist, style={"marginBottom": "20px"}),
            stats_table
        ])
        
    except Exception as e:
        return html.Div([
            html.H5("Error", style={"color": "red"}),
            html.P(f"An error occurred: {str(e)}")
        ])
    
@callback(
    Output("use-joined-flag", "data"),
    Output("joined-dataset-status", "children"),
    Output("use-joined-button", "children"),
    Input("use-joined-button", "n_clicks"),
    State("joined-dataset-store", "data"),
    State("use-joined-flag", "data"),
    prevent_initial_call=True
)
def enable_joined_dataset(n_clicks, joined_data, current_flag):
    if joined_data is None:
        return False, "No joined dataset found.", "Use joined dataset"
    if current_flag is None:
        current_flag = False

    new_flag = not current_flag
    if new_flag:
        label = "Disable Joined Dataset"
        status_message = "Joined dataset enabled for analysis."
        print(f'Cache key: {joined_data}')
    else:
        label = "Use Joined Dataset"
        status_message = "Joined dataset disabled."

    return new_flag, status_message, label

@callback(
    Output("stats-table-dropdown", "value"),
    Input("use-joined-flag", "data"),
    State("stats-table-dropdown", "options"),
    prevent_initial_call=True
)
def update_dropdown_on_join_flag(use_joined, table_options):
    if use_joined:
        # Set a special placeholder value to signal "joined dataset"
        # Add cache key to table_options
        return "__joined__"
    return dash.no_update

@callback(
    Output("stats-table-dropdown", "options"),
    Input("use-joined-flag", "data"),
    State("joined-dataset-store", "data")
)
def update_table_options(use_joined, joined_data):
    options = [{"label": table, "value": table} for table in table_options]
    # If the joined dataset is available, add it to options
    if use_joined and joined_data:
        options.insert(0, {"label": "Joined Dataset", "value": "__joined__"})

    return options
import dash
from dash import dcc, html, Input, Output, callback, callback_context, dash_table
import plotly.graph_objects as go
import pandas as pd
from dotenv import load_dotenv
import os
from database import fetch_data_from_sql

# Load environment variables
load_dotenv(override=True)
map_table = os.getenv("MAP_TABLE")

UCLA_coordinates = {
    "latitude": 34.0682,
    "longitude": -118.4455
}

map_layout = dcc.Tab(
    id="maps-tab",
    value="map-tab",
    label="Tab 1",
    style={"padding": "15px"},
    children = [
        html.Br(),
        html.Br(),
        html.Br(),
        html.Br(),
        html.Br(),
        html.Div(
            html.H2("[Insert your tables here]", className="text-center fw-bold"),
            style={
                "backgroundColor": "white",
                "padding": "50px 20px",
                "maxWidth": "1000px",     # or whatever width you want
                "margin": "0 auto"        # centers the div horizontally
            }
        ),  
        html.Br(),
        html.Br(),
        html.Br(),
        html.Br(),
        html.Br(),
        html.Div(
            html.H2("[Insert your maps here]", className="text-center fw-bold"),
            style={
                "backgroundColor": "white",
                "padding": "50px 20px",
                "maxWidth": "1000px",     # or whatever width you want
                "margin": "0 auto"        # centers the div horizontally
            }
        ),  
        html.Br(),
        html.Br(),
        html.Br(),
        html.Br(),
        html.Br(),
        html.Div(
            html.H2("[Insert your figures here]", className="text-center fw-bold"),
            style={
                "backgroundColor": "white",
                "padding": "50px 20px",
                "maxWidth": "1000px",     # or whatever width you want
                "margin": "0 auto"        # centers the div horizontally
            }
        ),  
    ]
)
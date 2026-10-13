import re

with open("tabs/joins.py", "r") as f:
    content = f.read()

# 1. Add bootstrap row wrapper and left/right divs
# We need to wrap everything after the store elements inside a row.
# the existing container starts at html.Div( [ # Introduction section

layout_start_search = """        dcc.Store(id='joins-metadata-store', data={}),  # Cache metadata (column lists)
        html.Div(
            ["""

layout_start_replace = """        dcc.Store(id='joins-metadata-store', data={}),  # Cache metadata (column lists)
        html.Div(className="row", children=[
            # LEFT COLUMN: Selection
            html.Div(className="col-md-4", style={"height": "100vh", "overflowY": "auto", "paddingRight": "20px", "borderRight": "2px solid #eee"}, children=[
"""
content = content.replace(layout_start_search, layout_start_replace)

# 2. Add the right column wrapper right before the results div
# The results div is id="join-tab-results-div" but we also need to include the row count input and error messages that show after execute

# Actually, the right column should probably contain the row-count, execute-error, results-div, and stats-main-container
# They appear right after join-tab-execute-button-div
split_point_search = """                ], id="join-tab-execute-button-div", style={"display": "none", "textAlign": "center", "marginTop": "20px", "marginBottom": "20px"}),

                # Row count input """

split_point_replace = """                ], id="join-tab-execute-button-div", style={"display": "none", "textAlign": "center", "marginTop": "20px", "marginBottom": "20px"}),
            ]), # END LEFT COLUMN
            
            # RIGHT COLUMN: Results & Analysis
            html.Div(className="col-md-8", style={"height": "100vh", "overflowY": "auto", "paddingLeft": "20px"}, children=[

                # Row count input """
content = content.replace(split_point_search, split_point_replace)

# 3. Close the right column
# The original layout ends with:
#                 ], id="stats-main-container", style={"display": "none", "padding": "20px", "backgroundColor": "#ffffff", "borderRadius": "8px", "border": "1px solid #e0e0e0", "marginTop": "20px"})
#
#             ]
#         )

end_search = """                ], id="stats-main-container", style={"display": "none", "padding": "20px", "backgroundColor": "#ffffff", "borderRadius": "8px", "border": "1px solid #e0e0e0", "marginTop": "20px"})

            ]"""

end_replace = """                ], id="stats-main-container", style={"display": "none", "padding": "20px", "backgroundColor": "#ffffff", "borderRadius": "8px", "border": "1px solid #e0e0e0", "marginTop": "20px"})

            ]) # END RIGHT COLUMN
        ]) # END ROW"""
content = content.replace(end_search, end_replace)


# 4. Change default checkbox state from "All Selected" to "Empty"
# This happens in populate_columns_on_core_change callback
cb_ret_search = """        # Default is to select all
        return (c_opts, core_cols, 
                t_opts, tree_cols, 
                g_opts, gardens_cols,"""
cb_ret_replace = """        # Default is to select NO columns (empty lists)
        return (c_opts, [], 
                t_opts, [], 
                g_opts, [],"""
content = content.replace(cb_ret_search, cb_ret_replace)


with open("tabs/joins.py", "w") as f:
    f.write(content)

print("Layout split successfully!")

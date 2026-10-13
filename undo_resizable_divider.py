import re

with open("tabs/joins.py", "r") as f:
    code = f.read()

# 1. Update Layout container back to row
code = code.replace(
    'html.Div(className="d-flex w-100", id="join-split-container", style={"height": "85vh", "flexDirection": "row"}, children=[',
    'html.Div(className="row mx-0", style={"maxWidth": "98%", "margin": "0 auto", "padding": "0 20px"}, children=['
)

# 2. Update Left Column back
code = code.replace(
    'html.Div(id="join-left-pane", style={"flex": "0 0 auto", "width": "25%", "minWidth": "15%", "maxWidth": "85%", "overflowX": "hidden", "overflowY": "auto", "paddingRight": "20px"}, children=[',
    'html.Div(className="col-md-3", style={"height": "85vh", "overflowY": "auto", "paddingRight": "20px", "borderRight": "2px solid #eee"}, children=['
)

# 3. Remove divider and update right column back
search_right = '''            ]), # END LEFT COLUMN

            # FULL HEIGHT DRAGGABLE DIVIDER
            html.Div(id="join-drag-divider", style={
                "width": "6px", 
                "cursor": "col-resize", 
                "backgroundColor": "#f4f4f4", 
                "borderLeft": "1px solid #ddd",
                "borderRight": "1px solid #ddd",
                "zIndex": 10,
                "transition": "background-color 0.2s"
            }),
            
            # RIGHT COLUMN: Results & Analysis
            html.Div(id="join-right-pane", style={"flex": "1 1 auto", "overflowY": "auto", "paddingLeft": "20px", "width": 0}, children=['''

replace_right = '''            ]), # END LEFT COLUMN
            
            # RIGHT COLUMN: Results & Analysis
            html.Div(className="col-md-9", style={"height": "85vh", "overflowY": "auto", "paddingLeft": "20px"}, children=['''

code = code.replace(search_right, replace_right)

# 4. Remove the clientside_callback
search_cb = """
# Drag and drop split-pane logic
clientside_callback(
    '''
    function(id) {
        setTimeout(function() {
            var divider = document.getElementById('join-drag-divider');
            var leftPane = document.getElementById('join-left-pane');
            var container = document.getElementById('join-split-container');
            
            if(!divider || !leftPane || !container) return;
            
            if(divider.dataset.listenerAttached) return;
            divider.dataset.listenerAttached = 'true';
            
            var isResizing = false;
            
            // Mouse events for Document (handles fast drags outside divider div)
            divider.addEventListener('mousedown', function(e) {
                isResizing = true;
                document.body.style.cursor = 'col-resize';
                divider.style.backgroundColor = '#007bff';
                e.preventDefault();
            });
            
            document.addEventListener('mousemove', function(e) {
                if (!isResizing) return;
                var containerOffsetLeft = container.getBoundingClientRect().left;
                var newWidth = e.clientX - containerOffsetLeft;
                
                var minW = container.getBoundingClientRect().width * 0.15;
                var maxW = container.getBoundingClientRect().width * 0.85;
                if(newWidth < minW) newWidth = minW;
                if(newWidth > maxW) newWidth = maxW;
                
                leftPane.style.width = newWidth + 'px';
            });
            
            document.addEventListener('mouseup', function(e) {
                if (isResizing) {
                    isResizing = false;
                    document.body.style.cursor = '';
                    divider.style.backgroundColor = '#f4f4f4';
                }
            });
        }, 1000);
        return window.dash_clientside.no_update;
    }
    ''',
    Output('join-drag-divider', 'data-dummy'),
    Input('join-drag-divider', 'id')
)
"""
code = code.replace(search_cb, "")

# 5. Restore imports
code = code.replace("from dash import dcc, html, Input, Output, State, callback, ctx, clientside_callback",
                    "from dash import dcc, html, Input, Output, State, callback, ctx")

with open("tabs/joins.py", "w") as f:
    f.write(code)

print("Splitpane callback and HTML removed successfully!")

import re

with open("tabs/joins.py", "r") as f:
    code = f.read()

# 1. Update imports
if "clientside_callback" not in code:
    code = code.replace("from dash import dcc, html, Input, Output, State, callback, ctx",
                        "from dash import dcc, html, Input, Output, State, callback, ctx, clientside_callback")

# 2. Update Layout container
search_container = 'html.Div(className="d-flex w-100", style={"height": "85vh", "flexDirection": "row"}, children=['
replace_container = 'html.Div(className="d-flex w-100", id="join-split-container", style={"height": "85vh", "flexDirection": "row"}, children=['
code = code.replace(search_container, replace_container)

# 3. Update Left Column
search_left = 'html.Div(style={"flex": "0 0 auto", "width": "25%", "minWidth": "15%", "maxWidth": "60%", "resize": "horizontal", "overflow": "auto", "paddingRight": "20px", "borderRight": "2px solid #ccc"}, children=['
replace_left = 'html.Div(id="join-left-pane", style={"flex": "0 0 auto", "width": "25%", "minWidth": "15%", "maxWidth": "85%", "overflowX": "hidden", "overflowY": "auto", "paddingRight": "20px"}, children=['
code = code.replace(search_left, replace_left)

# 4. Add Divider and update Right Column
search_right = '''            ]), # END LEFT COLUMN
            
            # RIGHT COLUMN: Results & Analysis
            html.Div(style={"flex": "1 1 auto", "overflowY": "auto", "paddingLeft": "20px"}, children=['''
replace_right = '''            ]), # END LEFT COLUMN

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
code = code.replace(search_right, replace_right)


callback_code = """
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

if "document.getElementById('join-drag-divider')" not in code:
    code += callback_code

with open("tabs/joins.py", "w") as f:
    f.write(code)

print("Splitpane callback injected successfully!")

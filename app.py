from dash import dcc, html, Dash, callback, Input, Output, State
from dash.dependencies import Input, Output
from tabs.upload import upload_layout
from tabs.download import download_layout
from tabs.map import map_layout
from tabs.joins import joins_layout
from components.shell import build_app_bar, build_content_frame, build_footer, build_tabs
import copy
import os
import secrets
from dotenv import load_dotenv
from flask import Flask, redirect, session
from authlib.integrations.flask_client import OAuth
from urllib.parse import parse_qs

load_dotenv(override=True)

# Initialize OAuth
server = Flask(__name__)
server.secret_key = os.getenv("APP_SECRET_KEY", "default-secret")

oauth = OAuth(server)
auth0 = oauth.register(
    'auth0',
    client_id=os.getenv("AUTH0_CLIENT_ID"),
    client_secret=os.getenv("AUTH0_CLIENT_SECRET"),
    api_base_url=f"https://{os.getenv('AUTH0_DOMAIN')}",
    access_token_url=f"https://{os.getenv('AUTH0_DOMAIN')}/oauth/token",
    authorize_url=f"https://{os.getenv('AUTH0_DOMAIN')}/authorize",
    client_kwargs={
        'scope': 'openid profile email',
    }, 
    server_metadata_url=f"https://{os.getenv('AUTH0_DOMAIN')}/.well-known/openid-configuration"
)

@server.route('/login')
def login():
    nonce = secrets.token_urlsafe(16)
    session['nonce'] = nonce
    return auth0.authorize_redirect(redirect_uri=os.getenv("AUTH0_CALLBACK_URL"), nonce=nonce)

@server.route('/callback')
def callback_handling():
    try:
        token = auth0.authorize_access_token()
        nonce = session.get('nonce')
        userinfo = auth0.parse_id_token(token, nonce=nonce)
        session['user'] = userinfo
        session.pop('nonce', None)
        return redirect('/')
    except Exception as e:
        print(f'Auth error: {e}')
        return redirect('/unauthorized')


@server.route('/logout')
def logout():
    session.clear()
    return redirect(
        f"https://{os.getenv('AUTH0_DOMAIN')}/v2/logout?"
        f"returnTo=http://127.0.0.1:8050&"
        f"client_id={os.getenv('AUTH0_CLIENT_ID')}"
    )

@server.route('/unauthorized')
def unauthorized():
    session.clear()
    return redirect(
        f"https://{os.getenv('AUTH0_DOMAIN')}/v2/logout?"
        f"returnTo=http://127.0.0.1:8050/?error=invalid_credentials&"
        f"client_id={os.getenv('AUTH0_CLIENT_ID')}"
    )

css = ["https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/css/bootstrap.min.css"]
app = Dash(name="Sork Lab Dashboard", server=server, external_stylesheets=css, suppress_callback_exceptions=True)

app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        <link href="https://fonts.googleapis.com/css2?family=Gowun+Batang&display=swap" rel="stylesheet">
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

FLAT_FILE_SUBTAB_STYLE = {
    "alignItems": "center",
    "background": "rgba(255, 255, 255, 0.54)",
    "border": "1px solid rgba(33, 79, 51, 0.12)",
    "borderRadius": "6px",
    "boxSizing": "border-box",
    "color": "#214f33",
    "cursor": "pointer",
    "display": "inline-flex",
    "fontWeight": "700",
    "height": "38px",
    "justifyContent": "center",
    "lineHeight": "1.2",
    "minWidth": "150px",
    "maxWidth": "190px",
    "padding": "0 18px",
}

FLAT_FILE_SUBTAB_SELECTED_STYLE = {
    **FLAT_FILE_SUBTAB_STYLE,
    "background": "#ffffff",
    "border": "1px solid rgba(33, 79, 51, 0.32)",
    "boxShadow": "0 6px 14px rgba(24, 47, 32, 0.08)",
}

# Create a combined flat-file tab with upload and download as sub-tabs
flat_files_layout = dcc.Tab(
    [
        dcc.Tabs(
            id="flat-files-subtabs",
            value="download-subtab",
            children=[
                dcc.Tab(
                    download_layout.children,
                    label="Download/Browse",
                    id="download-subtab",
                    style=FLAT_FILE_SUBTAB_STYLE,
                    selected_style=FLAT_FILE_SUBTAB_SELECTED_STYLE,
                ),
                dcc.Tab(
                    upload_layout.children,
                    label="Upload",
                    id="upload-subtab",
                    style=FLAT_FILE_SUBTAB_STYLE,
                    selected_style=FLAT_FILE_SUBTAB_SELECTED_STYLE,
                ),
            ],
            vertical=False,
            mobile_breakpoint=0,
            style={"display": "flex", "flexDirection": "row", "alignItems": "center", "justifyContent": "center", "gap": "10px", "width": "100%"},
            parent_style={"display": "flex", "flex": "1 1 auto", "flexDirection": "column"},
            className="flat-files-subtabs",
            parent_className="flat-files-subtabs__parent",
        )
    ],
    label="Flat File Downloads/Uploads",
    id="flat-files-tab",
    style={"padding": "15px", "display": "flex", "flexDirection": "column", "flex": "1 1 auto", "minHeight": 0}
)

TAB_SPECS = [
    ("Select and Filter", joins_layout),
    ("Tree Sites", map_layout),
    ("Flat File Downloads/Uploads", flat_files_layout),
]

# Guest-facing tab set — Select & Filter and Map only (no uploads or flat-file downloads)
GUEST_TAB_SPECS = [
    ("Select and Filter", joins_layout),
    ("Tree Sites", map_layout),
]


def build_user_actions():
    return [
        html.Div(
            className="user-chip",
            children=[
                html.Div("SL", className="user-chip__avatar"),
                html.Div(id='user-info', className="user-chip__text"),
            ],
        ),
        html.A(
            html.Button("Logout", className="btn btn-outline-secondary btn-sm logout-button"),
            href="/logout",
            className="logout-link",
        ),
    ]


def build_authenticated_layout():
    return html.Div(
        className="app-shell",
        children=[
            dcc.Location(id='url', refresh=False),
            build_app_bar("Dashboard", actions=build_user_actions()),
            html.Main(
                className="app-shell__body",
                children=[
                    build_content_frame(
                        [
                            html.Div(
                                className="content-frame__header",
                                children=[
                                    html.Div(
                                        [
                                            html.P("Research Workspace", className="content-frame__eyebrow"),
                                            html.H2("Shared data tools", className="content-frame__title"),
                                            html.P(
                                                "Browse tree sites, join datasets, upload data, and export curated slices from one shell.",
                                                className="content-frame__subtitle",
                                            ),
                                        ]
                                    )
                                ],
                            ),
                            build_tabs(TAB_SPECS, tabs_id='main-tabs', active_value='joins-tab'),
                        ]
                    )
                ],
            ),
            build_footer("Sork Lab Dashboard © 2025"),
        ],
    )


def build_guest_layout():
    return html.Div(
        className="app-shell",
        children=[
            dcc.Location(id='url', refresh=False),
            build_app_bar(
                "Dashboard",
                actions=[
                    html.Span(
                        "Log in for full access, including data uploads and flat-file downloads.",
                        className="login-access-note",
                    ),
                    html.A(
                        html.Button("Login", className="btn btn-primary btn-sm login-button"),
                        href="/login",
                    )
                ],
            ),
            html.Main(
                className="app-shell__body",
                children=[
                    build_content_frame(
                        [
                            html.Div(
                                className="content-frame__header",
                                children=[
                                    html.Div(
                                        [
                                            html.P("Public Access", className="content-frame__eyebrow"),
                                            html.H2("Shared data tools", className="content-frame__title"),
                                            html.P(
                                                "Browse and filter public data without an account.",
                                                className="content-frame__subtitle",
                                            ),
                                        ]
                                    ),
                                    html.Div(id='error-message', className="login-panel__error"),
                                ],
                            ),
                            build_tabs(GUEST_TAB_SPECS, tabs_id='main-tabs', active_value='joins-tab'),
                        ]
                    )
                ],
            ),
            build_footer("Sork Lab Dashboard © 2025"),
        ],
    )


def serve_layout():

    if 'user' in session:
        return build_authenticated_layout()
    return build_guest_layout()
        

app.layout = serve_layout
app.validation_layout = html.Div([
    build_authenticated_layout(),
    html.Div(id="error-message"),
])





# ===== CALLBACKS =====
@app.callback(
    Output('user-info', 'children'),
    Input('main-tabs', 'value')
)
def display_user(tab):
    if 'user' in session:
        return f"Logged in as {session['user']['name']}"
    return "Not logged in"


@app.callback(
    Output('error-message', 'children'),
    Input('url', 'search')
)
def display_error_message(search):
    if search:
        query_params = parse_qs(search.lstrip('?'))
        if 'error' in query_params:
            return html.Div("Login failed: Invalid username or password.", style={'color': 'red', 'textAlign': 'center', 'marginTop': '20px'})
    return ""

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)

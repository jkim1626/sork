import copy

from dash import dcc, html


def clone_tab(tab_component, *, label=None):
    tab_copy = copy.deepcopy(tab_component)
    if label is not None:
        tab_copy.label = label
    if getattr(tab_copy, "value", None) is None and getattr(tab_copy, "id", None):
        tab_copy.value = tab_copy.id
    tab_copy.style = {
        "alignItems": "center",
        "border": "1px solid transparent",
        "borderRadius": "999px",
        "boxSizing": "border-box",
        "display": "inline-flex",
        "height": "40px",
        "justifyContent": "center",
        "lineHeight": "1.2",
        "marginRight": "6px",
        "padding": "0 16px",
        "background": "transparent",
    }
    tab_copy.selected_style = {
        "alignItems": "center",
        "border": "1px solid rgba(33, 79, 51, 0.15)",
        "borderRadius": "999px",
        "boxSizing": "border-box",
        "display": "inline-flex",
        "height": "40px",
        "justifyContent": "center",
        "lineHeight": "1.2",
        "marginRight": "6px",
        "padding": "0 16px",
        "background": "linear-gradient(135deg, #edf5ec 0%, #dbe9db 100%)",
        "color": "#214f33",
    }
    return tab_copy


def build_app_bar(title, actions=None):
    return html.Header(
        className="app-bar",
        children=[
            html.Div(
                className="app-bar__inner",
                children=[
                    html.Div(
                        className="app-bar__brand",
                        children=[
                            html.Div("S", className="app-bar__mark"),
                            html.Div(
                                children=[
                                    html.P("Sork Lab", className="app-bar__eyebrow"),
                                    html.H1(title, className="app-bar__title"),
                                ]
                            ),
                        ],
                    ),
                    html.Div(actions or [], className="app-bar__actions"),
                ],
            )
        ],
    )


def build_content_frame(children, *, class_name=""):
    frame_class = "content-frame"
    if class_name:
        frame_class = f"{frame_class} {class_name}"
    return html.Section(className=frame_class, children=children)


def build_footer(text):
    return html.Footer(
        className="app-footer",
        children=html.Div(text, className="app-footer__inner"),
    )


def build_tabs(tab_specs, *, tabs_id, active_value):
    tabs = [clone_tab(tab, label=label) for label, tab in tab_specs]
    return dcc.Tabs(
        id=tabs_id,
        value=active_value,
        children=tabs,
        className="dashboard-tabs",
        parent_className="dashboard-tabs__parent",
    )

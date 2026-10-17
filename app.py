from __future__ import annotations

from pathlib import Path
import sys

import networkx as nx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from orgchart.auth import authenticate as authenticate_user, configured_users
from orgchart.data_loader import load_observable_data
from orgchart.evaluation import evaluate_predictions
from orgchart.inference import InferenceConfig, infer_company
from orgchart.normalization import normalize_title

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT / "src"))


def authenticate():
    try:
        users = configured_users()
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
    if not users:
        st.error("Authentication is not configured. Set ORGCHART_USERS_JSON with username, PBKDF2 password hash, role, and optional company scope.")
        st.code('ORGCHART_USERS_JSON = \'[{"username":"admin","password_hash":"pbkdf2_sha256$...","role":"admin"}]\'')
        st.stop()
    if "current_user" not in st.session_state:
        st.title("Org Chart Inference Platform")
        with st.form("login"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in")
        if submitted:
            user = authenticate_user(username, password, users)
            if user:
                st.session_state.current_user = {"username": user.username, "role": user.role, "company_ids": user.company_ids}
                st.rerun()
            st.error("Invalid username or password.")
        st.stop()
    session_user = st.session_state.current_user
    if session_user["username"].casefold() not in users:
        st.session_state.pop("current_user", None)
        st.rerun()
    if st.sidebar.button("Sign out"):
        st.session_state.pop("current_user", None)
        st.rerun()
    st.sidebar.caption(f"Signed in: {session_user['username']} · {session_user['role']}")
    from orgchart.auth import User
    return User(session_user["username"], session_user["role"], tuple(session_user["company_ids"]))


@st.cache_data(show_spinner="Loading observable company data…")
def load_data(data_dir: str):
    return load_observable_data(Path(data_dir))


@st.cache_data(show_spinner="Inferring relationships…")
def infer_cached(employees_csv: bytes, taxonomy_csv: bytes) -> pd.DataFrame:
    employees = pd.read_csv(pd.io.common.BytesIO(employees_csv))
    taxonomy = pd.read_csv(pd.io.common.BytesIO(taxonomy_csv))
    return infer_company(employees, InferenceConfig(), taxonomy)


def _apply_checks(applied_key: str, widget_keys: tuple[tuple[str, str], ...]) -> None:
    st.session_state[applied_key] = [label for label, key in widget_keys if st.session_state.get(key, False)]


def _cancel_checks(applied_key: str, widget_keys: tuple[tuple[str, str], ...]) -> None:
    selected = set(st.session_state.get(applied_key, []))
    for label, key in widget_keys:
        st.session_state[key] = label in selected


def _apply_threshold(widget_key: str, applied_key: str) -> None:
    st.session_state[applied_key] = st.session_state[widget_key]


def _cancel_threshold(widget_key: str, applied_key: str) -> None:
    st.session_state[widget_key] = st.session_state.get(applied_key, 0.0)


def chart(employees: pd.DataFrame, predictions: pd.DataFrame) -> go.Figure:
    graph = nx.DiGraph()
    graph.add_nodes_from(employees.employee_id)
    graph.add_edges_from((row.manager_employee_id, row.employee_id) for row in predictions[predictions.status == "accepted"].itertuples())
    positions = {}
    roots = [node for node in graph if graph.in_degree(node) == 0]
    cursor = 0.0

    def place_subtree(node: str, depth: int) -> float:
        nonlocal cursor
        children = sorted(graph.successors(node), key=lambda item: names.get(item, item))
        if not children:
            x = cursor
            cursor += 1.0
        else:
            child_x = [place_subtree(child, depth + 1) for child in children]
            x = sum(child_x) / len(child_x)
        positions[node] = (x, -depth)
        return x

    names = employees.set_index("employee_id").full_name.to_dict()
    for root in sorted(roots, key=lambda item: names.get(item, item)):
        place_subtree(root, 0)
        cursor += 1.5
    for node in graph:
        if node not in positions:
            positions[node] = (cursor, 0)
            cursor += 1.0
    titles = employees.set_index("employee_id").job_title.fillna("Title unavailable").to_dict()
    edge_x, edge_y = [], []
    for source, target in graph.edges:
        x0, y0 = positions[source]
        x1, y1 = positions[target]
        curve_steps = 16
        for step in range(curve_steps + 1):
            t = step / curve_steps
            inverse = 1 - t
            edge_x.append(inverse**3 * x0 + 3 * inverse**2 * t * x0 + 3 * inverse * t**2 * x1 + t**3 * x1)
            edge_y.append(inverse**3 * y0 + 3 * inverse**2 * t * (y0 - 0.35) + 3 * inverse * t**2 * (y1 + 0.35) + t**3 * y1)
        edge_x.append(None)
        edge_y.append(None)
    node_ids = list(graph.nodes)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=edge_x, y=edge_y, mode="lines", line={"color": "#aab4c0", "width": 1}, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=[positions[node][0] for node in node_ids], y=[positions[node][1] for node in node_ids], mode="markers+text", text=[names[node] for node in node_ids], textposition="bottom center", hovertext=[f"{names[node]}<br>{titles[node]}<br>{node}" for node in node_ids], hoverinfo="text", marker={"size": 16, "color": "#326cf4"}))
    fig.update_layout(showlegend=False, height=max(500, min(950, len(node_ids) * 8)), margin={"l": 25, "r": 25, "t": 25, "b": 80}, xaxis={"visible": False}, yaxis={"visible": False}, plot_bgcolor="white")
    return fig


st.set_page_config(page_title="Org Chart Inference", page_icon="🏢", layout="wide")
current_user = authenticate()
try:
    companies, employees_all, taxonomy = load_data(str(DATA))
except (OSError, ValueError) as exc:
    st.error(f"Could not load dataset: {exc}. Generate it with `python scripts/generate_dataset.py`.")
    st.stop()
st.title("Org Chart Inference Platform")
st.caption("Explainable manager suggestions. Evidence scores are rankings, not calibrated probabilities.")
company_options = companies.apply(lambda row: f"{row.company_name} · {row.company_id}", axis=1)
selected_company = st.selectbox("Select a company", company_options, key="company")
company_id = selected_company.rsplit("·", 1)[-1].strip()
company = companies[companies.company_id == company_id].iloc[0]
employees = employees_all[employees_all.company_id == company_id].copy()
predictions = infer_cached(employees.to_csv(index=False).encode("utf-8"), (DATA / "title_taxonomy.csv").read_bytes())
st.caption(f"{company.industry} · {company.stage} · {company.employee_count} employees · {company.structure_type}")

tabs = ["Org Chart", "Employee Explorer", "Unresolved", "Evaluation"]
tab_views = st.tabs(tabs)
chart_tab, explorer_tab, unresolved_tab, evaluation_tab = tab_views[:4]
with chart_tab:
    counts = st.columns(4)
    for col, label, number in zip(counts, ["Employees", "Accepted links", "Ambiguous", "Unresolved"], [len(employees), (predictions.status == "accepted").sum(), (predictions.status == "ambiguous").sum(), (predictions.status == "unresolved").sum()]):
        col.metric(label, int(number))
    departments = sorted(employees.department.dropna().unique())
    seniorities = sorted(employees.seniority_level.dropna().unique())
    defaults = ["executive", "director"]
    default_department = "Engineering" if "Engineering" in departments else departments[0] if departments else None
    company_key = company_id.replace("-", "_")
    department_applied_key = f"department_applied_{company_key}"
    designation_applied_key = f"designation_applied_{company_key}"
    score_applied_key = f"score_applied_{company_key}"
    st.session_state.setdefault(department_applied_key, [default_department] if default_department else [])
    st.session_state.setdefault(designation_applied_key, [value for value in defaults if value in seniorities])
    st.session_state.setdefault(score_applied_key, 0.0)
    controls = st.columns([2.2, 2.2, 1.8, 4])
    with controls[0]:
        st.markdown("**Department**")
        with st.popover(f"Choose departments ({len(st.session_state[department_applied_key])})", use_container_width=True):
            department_widgets = tuple((value, f"department_draft_{company_key}_{index}") for index, value in enumerate(departments))
            for value, key in department_widgets:
                st.session_state.setdefault(key, value in st.session_state[department_applied_key])
            with st.form(f"department_form_{company_key}"):
                for value, key in department_widgets:
                    st.checkbox(value, key=key)
                buttons = st.columns(2)
                buttons[0].form_submit_button("Apply", on_click=_apply_checks, args=(department_applied_key, department_widgets), use_container_width=True)
                buttons[1].form_submit_button("Cancel", on_click=_cancel_checks, args=(department_applied_key, department_widgets), use_container_width=True)
    with controls[1]:
        st.markdown("**Designation**")
        with st.popover(f"Choose designations ({len(st.session_state[designation_applied_key])})", use_container_width=True):
            designation_widgets = tuple((value, f"designation_draft_{company_key}_{index}") for index, value in enumerate(seniorities))
            for value, key in designation_widgets:
                st.session_state.setdefault(key, value in st.session_state[designation_applied_key])
            with st.form(f"designation_form_{company_key}"):
                for value, key in designation_widgets:
                    st.checkbox(value.replace("_", " ").title(), key=key)
                buttons = st.columns(2)
                buttons[0].form_submit_button("Apply", on_click=_apply_checks, args=(designation_applied_key, designation_widgets), use_container_width=True)
                buttons[1].form_submit_button("Cancel", on_click=_cancel_checks, args=(designation_applied_key, designation_widgets), use_container_width=True)
    with controls[2]:
        st.markdown("**Evidence score**")
        with st.popover(f"Minimum: {st.session_state[score_applied_key]:.2f}", use_container_width=True):
            score_widget_key = f"score_draft_{company_key}"
            st.session_state.setdefault(score_widget_key, st.session_state[score_applied_key])
            with st.form(f"score_form_{company_key}"):
                st.slider("Minimum evidence", 0.0, 1.0, 0.0, 0.05, key=score_widget_key)
                buttons = st.columns(2)
                buttons[0].form_submit_button("Apply", on_click=_apply_threshold, args=(score_widget_key, score_applied_key), use_container_width=True)
                buttons[1].form_submit_button("Cancel", on_click=_cancel_threshold, args=(score_widget_key, score_applied_key), use_container_width=True)
    with controls[3]:
        st.markdown("**Search employee**")
        search = st.text_input("Name or title", key="chart_search", label_visibility="collapsed", placeholder="Search name or title").casefold()
    department_filter = st.session_state[department_applied_key]
    designation_filter = st.session_state[designation_applied_key]
    minimum_score = st.session_state[score_applied_key]
    mask = employees.department.isin(department_filter) & employees.seniority_level.isin(designation_filter)
    if search:
        mask &= employees.full_name.fillna("").str.casefold().str.contains(search, regex=False) | employees.job_title.fillna("").str.casefold().str.contains(search, regex=False)
    candidates = predictions[predictions.employee_id.isin(employees.loc[mask, "employee_id"]) & (predictions.evidence_score.fillna(0) >= minimum_score)]
    chart_ids = set(candidates.employee_id) | set(candidates.manager_employee_id.dropna())
    chart_people = employees[employees.employee_id.isin(chart_ids)]
    chart_predictions = candidates[candidates.manager_employee_id.isin(chart_ids)]
    if chart_people.empty:
        st.info("No employees match these filters.")
    else:
        st.plotly_chart(chart(chart_people, chart_predictions), use_container_width=True)

with explorer_tab:
    view = employees.merge(predictions, on=["company_id", "employee_id"])
    view.insert(view.columns.get_loc("job_title") + 1, "normalized_title", view.job_title.map(lambda title: normalize_title(title, taxonomy)["canonical_title"]))
    view["inferred_manager"] = view.manager_employee_id.map(employees.set_index("employee_id").full_name)
    st.dataframe(view[["full_name", "job_title", "normalized_title", "department", "seniority_level", "inferred_manager", "evidence_score", "status", "reason"]], use_container_width=True, hide_index=True)
    evidence_employee = st.selectbox("Inspect relationship evidence", employees.employee_id, format_func=lambda value: f"{employees.loc[employees.employee_id == value, 'full_name'].iloc[0]} · {value}", key="evidence_employee")
    st.json(predictions[predictions.employee_id == evidence_employee].iloc[0].to_dict())

with unresolved_tab:
    pending = predictions[predictions.status != "accepted"].merge(employees, on=["company_id", "employee_id"])
    if pending.empty:
        st.success("No unresolved relationships for this company.")
    else:
        st.dataframe(pending[["full_name", "job_title", "department", "status", "candidate_employee_id", "evidence_score", "runner_up_score", "score_margin", "reason"]], use_container_width=True, hide_index=True)

with evaluation_tab:
    metadata_path = DATA / "dataset_metadata.csv"
    metadata = pd.read_csv(metadata_path) if metadata_path.exists() else pd.DataFrame()
    is_modified = not metadata.empty and ((metadata.key == "user_modified") & (metadata.value.astype(str).str.lower() == "true")).any()
    truth_path = DATA / "ground_truth.csv"
    if is_modified:
        st.info("Evaluation is disabled because employee records were edited after synthetic ground truth was generated.")
    elif truth_path.exists():
        truth = pd.read_csv(truth_path)
        metrics = evaluate_predictions(predictions, truth[truth.company_id == company_id])
        metric_cols = st.columns(5)
        for col, key in zip(metric_cols, ["edge_precision", "edge_recall", "f1", "employee_coverage", "abstention_rate"]):
            col.metric(key.replace("_", " ").title(), f"{metrics[key]:.1%}")
        st.caption("Synthetic ground truth is used only for evaluation, never for inference.")
    else:
        st.info("No ground truth is available in this deployment.")


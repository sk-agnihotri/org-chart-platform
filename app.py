from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import streamlit as st

from orgchart.auth import authenticate as authenticate_user, configured_users
from orgchart.chart_view import render_org_chart_svg
from orgchart.data_loader import load_observable_data
from orgchart.evaluation import evaluate_predictions
from orgchart.inference import InferenceConfig, infer_company
from orgchart.normalization import build_title_alias_lookup, normalize_title
from orgchart.review_features import (
    company_narrative,
    compare_employees,
    health_findings,
    make_review_queue,
    relationship_evidence,
    snapshot_directories,
    structural_summary,
)

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


def _apply_checks(applied_key: str, widget_keys: tuple[tuple[str, str], ...], popover_key: str) -> None:
    st.session_state[applied_key] = [label for label, key in widget_keys if st.session_state.get(key, False)]
    st.session_state[popover_key] = False


def _cancel_checks(applied_key: str, widget_keys: tuple[tuple[str, str], ...], popover_key: str) -> None:
    selected = set(st.session_state.get(applied_key, []))
    for label, key in widget_keys:
        st.session_state[key] = label in selected
    st.session_state[popover_key] = False


def _apply_threshold(widget_key: str, applied_key: str, popover_key: str) -> None:
    st.session_state[applied_key] = st.session_state[widget_key]
    st.session_state[popover_key] = False


def _cancel_threshold(widget_key: str, applied_key: str, popover_key: str) -> None:
    st.session_state[widget_key] = st.session_state.get(applied_key, 0.0)
    st.session_state[popover_key] = False


def _clear_chart_filters(department_key: str, designation_key: str, score_key: str, score_widget_key: str, departments: list[str], designations: list[str], department_widgets: tuple[tuple[str, str], ...], designation_widgets: tuple[tuple[str, str], ...]) -> None:
    st.session_state[department_key] = departments
    st.session_state[designation_key] = designations
    st.session_state[score_key] = 0.0
    st.session_state[score_widget_key] = 0.0
    for label, key in department_widgets:
        st.session_state[key] = label in departments
    for label, key in designation_widgets:
        st.session_state[key] = label in designations
    st.session_state["chart_search"] = ""


def _data_as_of() -> str:
    metadata_path = DATA / "dataset_metadata.csv"
    if metadata_path.exists():
        metadata = pd.read_csv(metadata_path)
        if {"key", "value"}.issubset(metadata.columns):
            date_rows = metadata[metadata.key.astype(str).str.casefold().isin({"dataset_date", "generated_at_utc", "data_as_of"})]
            if not date_rows.empty:
                return str(date_rows.iloc[0].value)
    return "not recorded in dataset metadata"


def _display(value, fallback: str) -> str:
    return fallback if pd.isna(value) or not str(value).strip() else str(value)


def _reporting_chain(employee_id: str, predictions: pd.DataFrame, employees: pd.DataFrame) -> list[str]:
    names = employees.set_index("employee_id").full_name.to_dict()
    managers = predictions[predictions.status == "accepted"].set_index("employee_id").manager_employee_id.to_dict()
    chain = []
    visited = set()
    current = employee_id
    while current and current not in visited and current in names:
        visited.add(current)
        chain.append(str(names[current]))
        current = managers.get(current)
    return list(reversed(chain))


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

tabs = ["Org Chart", "Employee Explorer", "Review Queue", "Company Insights", "Compare Versions", "Evaluation"]
tab_views = st.tabs(tabs)
chart_tab, explorer_tab, review_tab, insights_tab, compare_tab, evaluation_tab = tab_views
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
        department_popover_key = f"department_popover_{company_key}"
        with st.popover(f"Choose departments ({len(st.session_state[department_applied_key])})", use_container_width=True, key=department_popover_key, on_change="rerun"):
            department_widgets = tuple((value, f"department_draft_{company_key}_{index}") for index, value in enumerate(departments))
            for value, key in department_widgets:
                st.session_state[key] = value in st.session_state[department_applied_key]
            with st.form(f"department_form_{company_key}"):
                for value, key in department_widgets:
                    st.checkbox(value, key=key)
                buttons = st.columns(2)
                buttons[0].form_submit_button("Apply", on_click=_apply_checks, args=(department_applied_key, department_widgets, department_popover_key), use_container_width=True)
                buttons[1].form_submit_button("Cancel", on_click=_cancel_checks, args=(department_applied_key, department_widgets, department_popover_key), use_container_width=True)
    with controls[1]:
        st.markdown("**Designation**")
        designation_popover_key = f"designation_popover_{company_key}"
        with st.popover(f"Choose designations ({len(st.session_state[designation_applied_key])})", use_container_width=True, key=designation_popover_key, on_change="rerun"):
            designation_widgets = tuple((value, f"designation_draft_{company_key}_{index}") for index, value in enumerate(seniorities))
            for value, key in designation_widgets:
                st.session_state[key] = value in st.session_state[designation_applied_key]
            with st.form(f"designation_form_{company_key}"):
                for value, key in designation_widgets:
                    st.checkbox(value.replace("_", " ").title(), key=key)
                buttons = st.columns(2)
                buttons[0].form_submit_button("Apply", on_click=_apply_checks, args=(designation_applied_key, designation_widgets, designation_popover_key), use_container_width=True)
                buttons[1].form_submit_button("Cancel", on_click=_cancel_checks, args=(designation_applied_key, designation_widgets, designation_popover_key), use_container_width=True)
    with controls[2]:
        st.markdown("**Evidence score**")
        score_popover_key = f"score_popover_{company_key}"
        with st.popover(f"Minimum: {st.session_state[score_applied_key]:.2f}", use_container_width=True, key=score_popover_key, on_change="rerun"):
            score_widget_key = f"score_draft_{company_key}"
            st.session_state.setdefault(score_widget_key, st.session_state[score_applied_key])
            with st.form(f"score_form_{company_key}"):
                st.slider("Minimum evidence", 0.0, 1.0, 0.0, 0.05, key=score_widget_key)
                buttons = st.columns(2)
                buttons[0].form_submit_button("Apply", on_click=_apply_threshold, args=(score_widget_key, score_applied_key, score_popover_key), use_container_width=True)
                buttons[1].form_submit_button("Cancel", on_click=_cancel_threshold, args=(score_widget_key, score_applied_key, score_popover_key), use_container_width=True)
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
        st.button(
            "Clear chart filters",
            key=f"clear_chart_{company_key}",
            on_click=_clear_chart_filters,
            args=(department_applied_key, designation_applied_key, score_applied_key, score_widget_key, departments, seniorities, department_widgets, designation_widgets),
        )
    else:
        st.caption("Solid curved links show accepted inferred relationships. The tree is a suggestion, not verified reporting data.")
        st.components.v1.html(render_org_chart_svg(chart_people, chart_predictions), height=780, scrolling=False)

with explorer_tab:
    view = employees.merge(predictions, on=["company_id", "employee_id"])
    title_aliases = build_title_alias_lookup(taxonomy)
    view.insert(view.columns.get_loc("job_title") + 1, "normalized_title", view.job_title.map(lambda title: normalize_title(title, title_aliases=title_aliases)["canonical_title"]))
    view["inferred_manager"] = view.manager_employee_id.map(employees.set_index("employee_id").full_name)
    display_columns = ["full_name", "job_title", "normalized_title", "department", "seniority_level", "inferred_manager", "evidence_score", "status", "reason"]
    explore_cols = st.columns(2)
    explorer_departments = ["All departments", *sorted(employees.department.dropna().unique())]
    selected_explorer_department = explore_cols[0].selectbox("Department", explorer_departments, key=f"explorer_department_{company_id}")
    explorer_designations = sorted(employees.seniority_level.dropna().unique())
    selected_explorer_designations = explore_cols[1].multiselect("Designation", explorer_designations, default=explorer_designations, key=f"explorer_designation_{company_id}")
    if selected_explorer_department != "All departments":
        view = view[view.department == selected_explorer_department]
    view = view[view.seniority_level.isin(selected_explorer_designations)]
    st.dataframe(view[display_columns], use_container_width=True, hide_index=True)
    context_date = _data_as_of()
    export = view[display_columns].copy()
    export.insert(0, "dataset_as_of", context_date)
    export.insert(1, "company", company.company_name)
    st.download_button("Download company employee view (CSV)", export.to_csv(index=False).encode("utf-8"), file_name=f"{company_id}-org-view.csv", mime="text/csv")
    st.caption(f"Export context: {company.company_name} · data as of {context_date} · inference version {predictions.algorithm_version.iloc[0] if not predictions.empty else 'n/a'}.")
    evidence_employee = st.selectbox("Inspect relationship evidence", employees.employee_id, format_func=lambda value: f"{employees.loc[employees.employee_id == value, 'full_name'].iloc[0]} · {value}", key="evidence_employee")
    selected = predictions[predictions.employee_id == evidence_employee].iloc[0]
    person = employees.loc[employees.employee_id == evidence_employee].iloc[0]
    st.markdown(f"**{person.full_name}** · {_display(person.job_title, 'Title unavailable')} · {_display(person.department, 'Department unavailable')}")
    st.markdown(f"**Inference:** {selected.status.title()} · evidence score {selected.evidence_score if pd.notna(selected.evidence_score) else 'unavailable'} · {selected.reason}")
    evidence_table, candidate = relationship_evidence(selected, employees)
    if candidate is None:
        st.info("No eligible manager candidate was found for this employee.")
    else:
        candidate_cols = st.columns(2)
        candidate_cols[0].markdown(f"**Top candidate:** {candidate.full_name} · {_display(candidate.job_title, 'Title unavailable')} · {_display(candidate.department, 'Department unavailable')}")
        runner_id = selected.get("runner_up_employee_id")
        if pd.notna(runner_id) and runner_id in set(employees.employee_id):
            runner = employees.loc[employees.employee_id == runner_id].iloc[0]
            candidate_cols[1].markdown(f"**Alternative:** {runner.full_name} · score {selected.runner_up_score:.3f}")
    if not evidence_table.empty:
        st.dataframe(evidence_table, use_container_width=True, hide_index=True)
    st.caption("Scores are weighted ranking signals, not calibrated probabilities or verified facts.")
    chain = _reporting_chain(evidence_employee, predictions, employees)
    st.markdown(f"**Inferred path to root:** {' → '.join(chain) if chain else 'No accepted path is available.'}")

with review_tab:
    st.subheader("Relationship review queue")
    st.caption("Includes ambiguous and unresolved links plus accepted links with evidence scores below 0.85. Review marks last only for this browser session.")
    reviewed_key = f"reviewed_{company_id}"
    reviewed_ids = set(st.session_state.get(reviewed_key, []))
    queue = make_review_queue(employees, predictions, reviewed_ids)
    if queue.empty:
        st.success("No relationships currently meet the review-queue rules.")
    else:
        hide_reviewed = st.checkbox("Hide reviewed items", value=False, key=f"hide_reviewed_{company_id}")
        reasons = sorted(queue.review_reason.unique())
        chosen_reasons = st.multiselect("Review reason", reasons, default=reasons, key=f"review_reasons_{company_id}")
        visible_queue = queue[queue.review_reason.isin(chosen_reasons)]
        if hide_reviewed:
            visible_queue = visible_queue[~visible_queue.reviewed]
        queue_columns = ["full_name", "job_title", "department", "status", "candidate_employee_id", "evidence_score", "runner_up_score", "review_reason", "reviewed"]
        st.dataframe(visible_queue[queue_columns], use_container_width=True, hide_index=True)
        if not visible_queue.empty:
            selected_review_id = st.selectbox("Select a relationship to review", visible_queue.employee_id, format_func=lambda value: f"{visible_queue.loc[visible_queue.employee_id == value, 'full_name'].iloc[0]} · {value}", key=f"review_selected_{company_id}")
            selected_review = visible_queue.loc[visible_queue.employee_id == selected_review_id].iloc[0]
            st.info(f"{selected_review.review_reason} {selected_review.reason}")
            if selected_review_id in reviewed_ids:
                if st.button("Undo reviewed", key=f"unreview_{company_id}_{selected_review_id}"):
                    st.session_state[reviewed_key] = sorted(reviewed_ids - {selected_review_id})
                    st.rerun()
            elif st.button("Mark reviewed", key=f"review_{company_id}_{selected_review_id}"):
                st.session_state[reviewed_key] = sorted(reviewed_ids | {selected_review_id})
                st.rerun()

with insights_tab:
    st.subheader("Company structure signals")
    findings = health_findings(employees, predictions)
    narratives = company_narrative(employees, predictions, findings)
    st.caption(f"Inferred from dataset dated {_data_as_of()}. These prompts identify records to inspect; they do not establish organizational problems.")
    for message in narratives:
        st.markdown(f"- {message}")
    insight_cols = st.columns(5)
    structure = structural_summary(employees, predictions)
    insight_cols[0].metric("Accepted links", int((predictions.status == "accepted").sum()))
    insight_cols[1].metric("Ambiguous", int((predictions.status == "ambiguous").sum()))
    insight_cols[2].metric("Unresolved", int((predictions.status == "unresolved").sum()))
    insight_cols[3].metric("Review prompts", len(findings))
    insight_cols[4].metric("Inferred layers", structure["reporting_layers"])
    if findings.empty:
        st.success("No profile or span-of-control prompts were found by the current checks.")
    else:
        st.dataframe(findings, use_container_width=True, hide_index=True)

with compare_tab:
    st.subheader("Compare dataset versions")
    snapshots = snapshot_directories(DATA)
    if not snapshots:
        st.info("No historical snapshots yet. Before replacing the observable CSV dataset, run `python scripts/snapshot_dataset.py <version-name>`, commit `data/snapshots/`, and redeploy.")
    else:
        snapshot_choice = st.selectbox("Previous version", snapshots, format_func=lambda path: path.name, key=f"snapshot_{company_id}")
        previous_employees = pd.read_csv(snapshot_choice / "employees.csv")
        previous_employees = previous_employees[previous_employees.company_id == company_id]
        previous_taxonomy_path = snapshot_choice / "title_taxonomy.csv"
        previous_taxonomy = pd.read_csv(previous_taxonomy_path) if previous_taxonomy_path.exists() else taxonomy
        previous_predictions = infer_cached(previous_employees.to_csv(index=False).encode("utf-8"), previous_taxonomy.to_csv(index=False).encode("utf-8")) if not previous_employees.empty else pd.DataFrame()
        changes = compare_employees(employees, previous_employees, predictions, previous_predictions)
        summary = changes.Change.value_counts() if not changes.empty else pd.Series(dtype="int64")
        delta_cols = st.columns(4)
        for col, label in zip(delta_cols, ["Joined", "Departed", "Inferred manager changed", "Profile changes"]):
            col.metric(label, int(summary.get(label, 0) if label != "Profile changes" else sum(summary.get(kind, 0) for kind in ["Title changed", "Department changed", "Designation changed"])))
        if changes.empty:
            st.success("No employee or inferred reporting changes found between these versions.")
        else:
            st.dataframe(changes, use_container_width=True, hide_index=True)
            st.download_button("Download version comparison (CSV)", changes.to_csv(index=False).encode("utf-8"), file_name=f"{company_id}-version-comparison.csv", mime="text/csv")
        st.caption("Manager changes are recalculated using the current inference algorithm and are comparisons of suggestions, not verified reporting changes.")

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


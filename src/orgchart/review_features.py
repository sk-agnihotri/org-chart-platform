from __future__ import annotations

from pathlib import Path

import networkx as nx
import pandas as pd


EVIDENCE_LABELS = {
    "seniority_compatibility": "Seniority compatibility",
    "functional_alignment": "Functional alignment",
    "department_alignment": "Department alignment",
    "organizational_plausibility": "Managerial plausibility",
    "attribute_completeness": "Attribute completeness",
}


def relationship_evidence(prediction: pd.Series, employees: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series | None]:
    lookup = employees.set_index("employee_id")
    candidate_id = prediction.get("candidate_employee_id")
    if pd.isna(candidate_id) or candidate_id not in lookup.index:
        return pd.DataFrame(columns=["Signal", "Score", "Interpretation"]), None
    candidate = lookup.loc[candidate_id]
    raw = prediction.get("evidence") or {}
    evidence = []
    for key, label in EVIDENCE_LABELS.items():
        score = raw.get(key)
        evidence.append({"Signal": label, "Score": score, "Interpretation": _interpret_signal(key, score)})
    evidence.extend([
        {"Signal": "Seniority gap", "Score": prediction.get("seniority_gap"), "Interpretation": "Candidate is above the employee in the title taxonomy."},
        {"Signal": "Score margin", "Score": prediction.get("score_margin"), "Interpretation": "Difference between the top two candidate scores (or top score when there is one)."},
    ])
    return pd.DataFrame(evidence), candidate


def _interpret_signal(key: str, value: float | None) -> str:
    if value is None or pd.isna(value):
        return "Unavailable"
    descriptions = {
        "seniority_compatibility": "Seniority levels form a plausible reporting gap.",
        "functional_alignment": "Normalized title functions align.",
        "department_alignment": "Department values align or one is missing.",
        "organizational_plausibility": "Candidate title is recognized as a management role.",
        "attribute_completeness": "Relevant title and department fields are present.",
    }
    return descriptions.get(key, "Scoring signal")


def health_findings(employees: pd.DataFrame, predictions: pd.DataFrame) -> pd.DataFrame:
    findings = []
    profile = employees.set_index("employee_id")
    predictions_by_id = predictions.set_index("employee_id")
    reports = predictions[predictions.manager_employee_id.notna()].groupby("manager_employee_id").employee_id.nunique()
    for employee in employees.itertuples(index=False):
        person = profile.loc[employee.employee_id]
        prediction = predictions_by_id.loc[employee.employee_id] if employee.employee_id in predictions_by_id.index else None
        if _missing(person.get("job_title")):
            findings.append(_finding(employee, "Missing title", "Add or verify this employee's job title."))
        if _missing(person.get("department")):
            findings.append(_finding(employee, "Missing department", "Add or verify the employee's department."))
        if prediction is not None and prediction.status in {"ambiguous", "unresolved"}:
            findings.append(_finding(employee, "Unresolved relationship", str(prediction.reason)))
        count = int(reports.get(employee.employee_id, 0))
        if count > 10:
            findings.append(_finding(employee, "Wide span of control", f"{count} accepted direct reports; review whether this team is intentionally broad."))
    return pd.DataFrame(findings, columns=["employee_id", "Employee", "Department", "Finding", "Review prompt"])


def _finding(employee, finding: str, prompt: str) -> dict:
    return {"employee_id": employee.employee_id, "Employee": employee.full_name, "Department": employee.department, "Finding": finding, "Review prompt": prompt}


def company_narrative(employees: pd.DataFrame, predictions: pd.DataFrame, findings: pd.DataFrame) -> list[str]:
    total = len(employees)
    accepted = int((predictions.status == "accepted").sum()) if not predictions.empty else 0
    ambiguous = int((predictions.status == "ambiguous").sum()) if not predictions.empty else 0
    unresolved = int((predictions.status == "unresolved").sum()) if not predictions.empty else 0
    messages = [f"The inferred structure contains {accepted} accepted links across {total} employees."]
    summary = structural_summary(employees, predictions)
    messages.append(f"Accepted links span {summary['reporting_layers']} inferred reporting layers; {summary['without_accepted_manager']} employees have no accepted manager link.")
    if ambiguous or unresolved:
        messages.append(f"{ambiguous} relationships are ambiguous and {unresolved} are unresolved; review these before treating the chart as complete.")
    if not findings.empty:
        frequent = findings.Finding.value_counts().head(2)
        messages.extend(f"{int(count)} employees flagged for: {label.lower()}." for label, count in frequent.items())
    if not ambiguous and not unresolved and findings.empty:
        messages.append("No structural review prompts were found by the current checks.")
    return messages


def structural_summary(employees: pd.DataFrame, predictions: pd.DataFrame) -> dict[str, int]:
    graph = nx.DiGraph()
    graph.add_nodes_from(employees.employee_id)
    if not predictions.empty:
        accepted = predictions[predictions.status == "accepted"]
        graph.add_edges_from((row.manager_employee_id, row.employee_id) for row in accepted.itertuples())
    roots = [node for node in graph if graph.in_degree(node) == 0]
    depth = nx.dag_longest_path_length(graph) if graph.number_of_edges() else 0
    no_manager = int(sum(graph.in_degree(node) == 0 for node in graph))
    return {"reporting_layers": int(depth + 1 if graph else 0), "root_count": len(roots), "without_accepted_manager": no_manager}


def make_review_queue(employees: pd.DataFrame, predictions: pd.DataFrame, reviewed_ids: set[str]) -> pd.DataFrame:
    if predictions.empty:
        return pd.DataFrame()
    queue = predictions.merge(employees, on=["company_id", "employee_id"], how="left")
    low_score = queue.evidence_score.fillna(0) < 0.85
    queue = queue[(queue.status != "accepted") | low_score].copy()
    queue["review_reason"] = queue.apply(_review_reason, axis=1)
    queue["reviewed"] = queue.employee_id.isin(reviewed_ids)
    return queue.sort_values(["reviewed", "status", "evidence_score"], ascending=[True, True, True])


def _review_reason(row: pd.Series) -> str:
    if row.status == "ambiguous":
        return "Top candidates are close in score."
    if row.status == "unresolved":
        return str(row.reason)
    return "Accepted link has a lower-than-0.85 evidence score; verify the signals."


def compare_employees(current: pd.DataFrame, previous: pd.DataFrame, current_predictions: pd.DataFrame, previous_predictions: pd.DataFrame) -> pd.DataFrame:
    columns = ["employee_id", "Employee", "Change", "Previous", "Current"]
    old = previous.set_index("employee_id", drop=False)
    new = current.set_index("employee_id", drop=False)
    rows = []
    for employee_id in sorted(set(old.index) | set(new.index)):
        if employee_id not in old.index:
            rows.append({"employee_id": employee_id, "Employee": new.loc[employee_id].full_name, "Change": "Joined", "Previous": "", "Current": "Present in current dataset"})
            continue
        if employee_id not in new.index:
            rows.append({"employee_id": employee_id, "Employee": old.loc[employee_id].full_name, "Change": "Departed", "Previous": "Present in previous dataset", "Current": ""})
            continue
        for field, label in [("job_title", "Title changed"), ("department", "Department changed"), ("seniority_level", "Designation changed")]:
            before, after = old.loc[employee_id].get(field), new.loc[employee_id].get(field)
            before, after = _clean(before), _clean(after)
            if before != after:
                rows.append({"employee_id": employee_id, "Employee": new.loc[employee_id].full_name, "Change": label, "Previous": before, "Current": after})
    old_managers = previous_predictions.set_index("employee_id").manager_employee_id.to_dict() if not previous_predictions.empty else {}
    new_managers = current_predictions.set_index("employee_id").manager_employee_id.to_dict() if not current_predictions.empty else {}
    for employee_id in sorted(set(old_managers) & set(new_managers)):
        before, after = _clean(old_managers[employee_id]), _clean(new_managers[employee_id])
        if before != after:
            name = new.loc[employee_id].full_name if employee_id in new.index else employee_id
            rows.append({"employee_id": employee_id, "Employee": name, "Change": "Inferred manager changed", "Previous": before or "Unresolved", "Current": after or "Unresolved"})
    return pd.DataFrame(rows, columns=columns)


def _clean(value) -> str:
    return "" if pd.isna(value) else str(value)


def _missing(value) -> bool:
    return value is None or pd.isna(value) or not str(value).strip()


def snapshot_directories(data_dir: Path) -> list[Path]:
    root = data_dir / "snapshots"
    return sorted((path for path in root.iterdir() if path.is_dir() and (path / "employees.csv").exists()), reverse=True) if root.exists() else []

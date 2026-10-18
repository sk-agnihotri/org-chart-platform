from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from orgchart.normalization import build_title_alias_lookup, normalize_title
from orgchart.validation import validate_edges

ALGORITHM_VERSION = "baseline-0.1"


@dataclass(frozen=True)
class InferenceConfig:
    acceptance_threshold: float = 0.72
    ambiguity_margin: float = 0.12
    max_seniority_gap: int = 5


def score_candidate(employee: dict[str, Any], manager: dict[str, Any]) -> dict[str, Any]:
    employee_title, manager_title = employee["normalized"], manager["normalized"]
    gap = (manager_title["seniority_rank"] or 0) - (employee_title["seniority_rank"] or 0)
    score, feature_values = _score_candidate_components(employee, manager, gap)
    feature_names = ("seniority_compatibility", "functional_alignment", "department_alignment", "organizational_plausibility", "attribute_completeness")
    return {"score": score, "features": {key: round(value, 3) for key, value in zip(feature_names, feature_values)}, "seniority_gap": gap}


def _score_candidate_components(employee: dict[str, Any], manager: dict[str, Any], gap: int) -> tuple[float, tuple[float, ...]]:
    employee_title, manager_title = employee["normalized"], manager["normalized"]
    employee_has_department = employee.get("_has_department", bool(employee.get("department")))
    manager_has_department = manager.get("_has_department", bool(manager.get("department")))
    employee_department = employee.get("_department_key", str(employee.get("department", "")).casefold())
    manager_department = manager.get("_department_key", str(manager.get("department", "")).casefold())
    same_department = bool(employee_has_department and manager_has_department and employee_department == manager_department)
    same_function = bool(employee_title["function"] and manager_title["function"] and employee_title["function"] == manager_title["function"])
    features = (
        1.0 if 1 <= gap <= 3 else 0.65 if gap > 3 else 0.0,
        1.0 if same_function else 0.45 if same_department else 0.15,
        1.0 if same_department else 0.25 if not employee_has_department or not manager_has_department else 0.0,
        1.0 if manager_title["is_management"] else 0.2,
        sum((employee.get("_has_job_title", bool(employee.get("job_title"))), employee_has_department, manager.get("_has_job_title", bool(manager.get("job_title"))), manager_has_department)) / 4,
    )
    score = round(features[0] * 0.35 + features[1] * 0.25 + features[2] * 0.18 + features[3] * 0.17 + features[4] * 0.05, 4)
    return score, features


def _score_candidate_matrices(employees: list[dict], managers: list[dict], config: InferenceConfig):
    employee_titles = [person["normalized"] for person in employees]
    manager_titles = [person["normalized"] for person in managers]
    employee_ranks = np.array([title["seniority_rank"] or 0 for title in employee_titles])
    manager_ranks = np.array([title["seniority_rank"] or 0 for title in manager_titles])
    gaps = manager_ranks[None, :] - employee_ranks[:, None]
    employee_ids = np.asarray([person["employee_id"] for person in employees], dtype=object)
    manager_ids = np.asarray([person["employee_id"] for person in managers], dtype=object)
    eligible = (gaps >= 1) & (gaps <= config.max_seniority_gap) & (employee_ids[:, None] != manager_ids[None, :])

    employee_departments = np.asarray([person["_department_key"] for person in employees], dtype=object)
    manager_departments = np.asarray([person["_department_key"] for person in managers], dtype=object)
    employee_has_department = np.asarray([person["_has_department"] for person in employees], dtype=bool)
    manager_has_department = np.asarray([person["_has_department"] for person in managers], dtype=bool)
    same_department = (employee_departments[:, None] == manager_departments[None, :]) & employee_has_department[:, None] & manager_has_department[None, :]

    employee_functions = np.asarray([title["function"] or "" for title in employee_titles], dtype=object)
    manager_functions = np.asarray([title["function"] or "" for title in manager_titles], dtype=object)
    same_function = (employee_functions[:, None] == manager_functions[None, :]) & (employee_functions[:, None] != "") & (manager_functions[None, :] != "")

    seniority = np.where((gaps >= 1) & (gaps <= 3), 1.0, np.where(gaps > 3, 0.65, 0.0))
    functional = np.where(same_function, 1.0, np.where(same_department, 0.45, 0.15))
    department = np.where(same_department, 1.0, np.where(~employee_has_department[:, None] | ~manager_has_department[None, :], 0.25, 0.0))
    plausibility = np.broadcast_to(np.asarray([title["is_management"] for title in manager_titles], dtype=float), gaps.shape)
    employee_complete = np.asarray([person["_has_job_title"] for person in employees], dtype=float) + employee_has_department
    manager_complete = np.asarray([person["_has_job_title"] for person in managers], dtype=float) + manager_has_department
    completeness = (employee_complete[:, None] + manager_complete[None, :]) / 4
    scores = np.round(seniority * 0.35 + functional * 0.25 + department * 0.18 + plausibility * 0.17 + completeness * 0.05, 4)
    scores[~eligible] = -np.inf
    return scores, gaps, (seniority, functional, department, plausibility, completeness)


def infer_company(employees: pd.DataFrame, config: InferenceConfig = InferenceConfig(), taxonomy: pd.DataFrame | None = None) -> pd.DataFrame:
    columns = ["company_id", "employee_id", "manager_employee_id", "status", "evidence_score", "runner_up_score", "score_margin", "seniority_gap", "evidence", "candidate_employee_id", "runner_up_employee_id", "reason", "algorithm_version"]
    if employees.empty:
        return pd.DataFrame(columns=columns)
    if not {"company_id", "employee_id"}.issubset(employees.columns):
        raise ValueError("employees requires company_id and employee_id")
    if employees.employee_id.duplicated().any():
        raise ValueError("employee_id values must be unique")
    title_aliases = build_title_alias_lookup(taxonomy)
    by_company: dict[Any, list[dict]] = {}
    for record in employees.to_dict("records"):
        record["normalized"] = normalize_title(record.get("job_title"), title_aliases=title_aliases)
        department = record.get("department")
        record["_has_department"] = bool(department)
        record["_department_key"] = str(department).casefold() if record["_has_department"] else ""
        record["_has_job_title"] = bool(record.get("job_title"))
        by_company.setdefault(record["company_id"], []).append(record)
    outcomes = []
    for company_id, coworkers in by_company.items():
        managers = sorted((person for person in coworkers if person["normalized"]["is_management"]), key=lambda person: str(person["employee_id"]))
        batch_size = max(1, min(512, 2_000_000 // max(1, len(managers))))
        for batch_start in range(0, len(coworkers), batch_size):
            employee_batch = coworkers[batch_start:batch_start + batch_size]
            if managers:
                score_matrix, gap_matrix, feature_matrices = _score_candidate_matrices(employee_batch, managers, config)
                candidate_order = np.argsort(-score_matrix, axis=1, kind="stable")
            else:
                score_matrix = gap_matrix = candidate_order = None
                feature_matrices = ()
            for batch_index, employee in enumerate(employee_batch):
                best = None
                runner = None
                if managers:
                    top_index = int(candidate_order[batch_index, 0])
                    if np.isfinite(score_matrix[batch_index, top_index]):
                        best = (
                            managers[top_index],
                            float(score_matrix[batch_index, top_index]),
                            int(gap_matrix[batch_index, top_index]),
                            tuple(float(features[batch_index, top_index]) for features in feature_matrices),
                        )
                        if len(managers) > 1:
                            runner_index = int(candidate_order[batch_index, 1])
                            if np.isfinite(score_matrix[batch_index, runner_index]):
                                runner = (
                                    managers[runner_index],
                                    float(score_matrix[batch_index, runner_index]),
                                    int(gap_matrix[batch_index, runner_index]),
                                    (),
                                )
                best_score = best[1] if best else None
                runner_score = runner[1] if runner else None
                margin = round(best_score - runner_score, 4) if best and runner else best_score
                status = "unresolved" if not best or best_score < config.acceptance_threshold else "ambiguous" if runner and margin < config.ambiguity_margin else "accepted"
                reason = "No eligible higher-seniority manager candidate." if not best else "Top candidates are too close to distinguish." if status == "ambiguous" else "Best candidate did not meet the evidence threshold." if status == "unresolved" else "Highest-scoring candidate meets threshold and margin."
                outcomes.append({"company_id": company_id, "employee_id": employee["employee_id"], "manager_employee_id": best[0]["employee_id"] if status == "accepted" else None, "status": status, "evidence_score": best_score, "runner_up_score": runner_score, "score_margin": margin, "seniority_gap": best[2] if best else None, "evidence": {key: round(value, 3) for key, value in zip(("seniority_compatibility", "functional_alignment", "department_alignment", "organizational_plausibility", "attribute_completeness"), best[3])} if best else {}, "candidate_employee_id": best[0]["employee_id"] if best else None, "runner_up_employee_id": runner[0]["employee_id"] if runner else None, "reason": reason, "algorithm_version": ALGORITHM_VERSION})
    result = pd.DataFrame(outcomes, columns=columns)
    accepted = result[result.status == "accepted"]
    violations = validate_edges(employees, accepted[["company_id", "employee_id", "manager_employee_id"]])
    if violations:
        invalid = {item["employee_id"] for item in violations}
        mask = result.employee_id.isin(invalid)
        result.loc[mask, "manager_employee_id"] = None
        result.loc[mask, "status"] = "unresolved"
        result.loc[mask, "reason"] = "Rejected by graph validation."
    return result

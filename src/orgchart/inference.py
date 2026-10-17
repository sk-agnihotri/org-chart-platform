from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from orgchart.normalization import normalize_title
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
    same_department = bool(employee.get("department") and manager.get("department") and str(employee["department"]).casefold() == str(manager["department"]).casefold())
    same_function = bool(employee_title["function"] and manager_title["function"] and employee_title["function"] == manager_title["function"])
    features = {
        "seniority_compatibility": 1.0 if 1 <= gap <= 3 else 0.65 if gap > 3 else 0.0,
        "functional_alignment": 1.0 if same_function else 0.45 if same_department else 0.15,
        "department_alignment": 1.0 if same_department else 0.25 if not employee.get("department") or not manager.get("department") else 0.0,
        "organizational_plausibility": 1.0 if manager_title["is_management"] else 0.2,
        "attribute_completeness": sum(bool(value) for value in (employee.get("job_title"), employee.get("department"), manager.get("job_title"), manager.get("department"))) / 4,
    }
    weights = {"seniority_compatibility": 0.35, "functional_alignment": 0.25, "department_alignment": 0.18, "organizational_plausibility": 0.17, "attribute_completeness": 0.05}
    return {"score": round(sum(features[key] * weights[key] for key in features), 4), "features": {key: round(value, 3) for key, value in features.items()}, "seniority_gap": gap}


def infer_company(employees: pd.DataFrame, config: InferenceConfig = InferenceConfig(), taxonomy: pd.DataFrame | None = None) -> pd.DataFrame:
    columns = ["company_id", "employee_id", "manager_employee_id", "status", "evidence_score", "runner_up_score", "score_margin", "evidence", "candidate_employee_id", "reason", "algorithm_version"]
    if employees.empty:
        return pd.DataFrame(columns=columns)
    if not {"company_id", "employee_id"}.issubset(employees.columns):
        raise ValueError("employees requires company_id and employee_id")
    if employees.employee_id.duplicated().any():
        raise ValueError("employee_id values must be unique")
    by_company: dict[Any, list[dict]] = {}
    for record in employees.to_dict("records"):
        record["normalized"] = normalize_title(record.get("job_title"), taxonomy)
        by_company.setdefault(record["company_id"], []).append(record)
    outcomes = []
    for company_id, coworkers in by_company.items():
        manager_pool = [person for person in coworkers if person["normalized"]["is_management"]]
        for employee in coworkers:
            candidates = []
            for manager in manager_pool:
                if manager["employee_id"] == employee["employee_id"]:
                    continue
                score = score_candidate(employee, manager)
                gap = score["seniority_gap"]
                if 1 <= gap <= config.max_seniority_gap:
                    candidates.append((manager, score))
            candidates.sort(key=lambda pair: (-pair[1]["score"], str(pair[0]["employee_id"])))
            best = candidates[0] if candidates else None
            runner = candidates[1] if len(candidates) > 1 else None
            best_score = best[1]["score"] if best else None
            runner_score = runner[1]["score"] if runner else None
            margin = round(best_score - runner_score, 4) if best and runner else best_score
            status = "unresolved" if not best or best_score < config.acceptance_threshold else "ambiguous" if runner and margin < config.ambiguity_margin else "accepted"
            reason = "No eligible higher-seniority manager candidate." if not best else "Top candidates are too close to distinguish." if status == "ambiguous" else "Best candidate did not meet the evidence threshold." if status == "unresolved" else "Highest-scoring candidate meets threshold and margin."
            outcomes.append({"company_id": company_id, "employee_id": employee["employee_id"], "manager_employee_id": best[0]["employee_id"] if status == "accepted" else None, "status": status, "evidence_score": best_score, "runner_up_score": runner_score, "score_margin": margin, "evidence": best[1]["features"] if best else {}, "candidate_employee_id": best[0]["employee_id"] if best else None, "reason": reason, "algorithm_version": ALGORITHM_VERSION})
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

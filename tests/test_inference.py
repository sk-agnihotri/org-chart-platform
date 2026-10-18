import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from orgchart.inference import InferenceConfig, infer_company
from orgchart.normalization import build_title_alias_lookup, normalize_title


def test_title_aliases_and_features():
    title = normalize_title("SWE")
    assert title["canonical_title"] == "Software Engineer"
    assert title["function"] == "engineering"
    assert normalize_title("Chief Technology Officer")["is_executive"]


def test_compiled_taxonomy_alias_lookup_matches_direct_normalization():
    taxonomy = pd.DataFrame([
        {"canonical_title": "Engineering Manager", "aliases": "Eng Manager|Engineering Lead"},
    ])
    lookup = build_title_alias_lookup(taxonomy)
    for title in ["Engineering Manager", "Eng Manager", "Engineering Lead"]:
        assert normalize_title(title, taxonomy) == normalize_title(title, title_aliases=lookup)


def test_inference_accepts_plausible_same_department_manager():
    employees = pd.DataFrame([
        {"company_id": "A", "employee_id": "e1", "job_title": "Software Engineer", "department": "Engineering"},
        {"company_id": "A", "employee_id": "e2", "job_title": "Engineering Manager", "department": "Engineering"},
        {"company_id": "B", "employee_id": "e3", "job_title": "Engineering Manager", "department": "Engineering"},
    ])
    result = infer_company(employees)
    employee = result[result.employee_id == "e1"].iloc[0]
    assert employee.status == "accepted"
    assert employee.manager_employee_id == "e2"
    assert employee.evidence["department_alignment"] == 1


def test_weak_or_tied_evidence_abstains():
    employees = pd.DataFrame([
        {"company_id": "A", "employee_id": "e1", "job_title": None, "department": None},
        {"company_id": "A", "employee_id": "m1", "job_title": "Director of Engineering", "department": None},
        {"company_id": "A", "employee_id": "m2", "job_title": "Director of Engineering", "department": None},
    ])
    result = infer_company(employees, InferenceConfig(acceptance_threshold=0.1, ambiguity_margin=0.1))
    assert result.loc[result.employee_id == "e1", "status"].item() == "ambiguous"


def test_equal_scores_keep_employee_id_order_for_top_two_candidates():
    employees = pd.DataFrame([
        {"company_id": "A", "employee_id": "e1", "job_title": "Software Engineer", "department": "Engineering"},
        {"company_id": "A", "employee_id": "m3", "job_title": "Engineering Manager", "department": "Engineering"},
        {"company_id": "A", "employee_id": "m1", "job_title": "Engineering Manager", "department": "Engineering"},
        {"company_id": "A", "employee_id": "m2", "job_title": "Engineering Manager", "department": "Engineering"},
    ])
    result = infer_company(employees, InferenceConfig(acceptance_threshold=0.1, ambiguity_margin=0.1))
    employee = result[result.employee_id == "e1"].iloc[0]
    assert employee.candidate_employee_id == "m1"
    assert employee.runner_up_employee_id == "m2"


def test_empty_company_result():
    assert infer_company(pd.DataFrame()).empty

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from orgchart.inference import infer_company
from orgchart.review_features import (
    compare_employees,
    health_findings,
    make_review_queue,
    relationship_evidence,
    snapshot_directories,
    structural_summary,
)


def sample_people():
    return pd.DataFrame([
        {"company_id": "C1", "employee_id": "e1", "full_name": "Asha Rao", "job_title": "Software Engineer", "department": "Engineering", "seniority_level": "individual_contributor"},
        {"company_id": "C1", "employee_id": "e2", "full_name": "Dev Shah", "job_title": "Engineering Manager", "department": "Engineering", "seniority_level": "manager"},
        {"company_id": "C1", "employee_id": "e3", "full_name": "Mira Iyer", "job_title": "Director of Engineering", "department": "Engineering", "seniority_level": "director"},
        {"company_id": "C1", "employee_id": "e4", "full_name": "Ravi Das", "job_title": None, "department": None, "seniority_level": "individual_contributor"},
    ])


def test_relationship_evidence_explains_candidate_and_signals():
    people = sample_people()
    predictions = infer_company(people)
    prediction = predictions[predictions.employee_id == "e1"].iloc[0]
    table, candidate = relationship_evidence(people[people.employee_id == "e1"].iloc[0], prediction, people)
    assert candidate.name == prediction.candidate_employee_id
    assert "Functional alignment" in set(table.Signal)
    assert "Score margin" in set(table.Signal)


def test_review_queue_contains_unresolved_and_low_score_accepted_items():
    people = sample_people()
    predictions = infer_company(people)
    queue = make_review_queue(people, predictions, {"e4"})
    assert set(queue.status).issubset({"accepted", "ambiguous", "unresolved"})
    assert queue.reviewed.any()
    assert (queue.status != "accepted").any() or (queue.evidence_score.fillna(0) < 0.85).any()


def test_health_findings_and_structure_summary_are_explainable():
    people = sample_people()
    predictions = infer_company(people)
    findings = health_findings(people, predictions)
    assert {"Missing title", "Missing department"}.issubset(set(findings.Finding))
    summary = structural_summary(people, predictions)
    assert summary["reporting_layers"] >= 1
    assert summary["without_accepted_manager"] >= 1


def test_comparison_reports_profile_and_membership_changes():
    old = sample_people().iloc[:3].copy()
    current = sample_people().iloc[:3].copy()
    current.loc[current.employee_id == "e1", "job_title"] = "Senior Software Engineer"
    current = pd.concat([current, sample_people().iloc[[3]]], ignore_index=True)
    changes = compare_employees(current, old, infer_company(current), infer_company(old))
    assert {"Title changed", "Joined"}.issubset(set(changes.Change))


def test_snapshot_discovery_ignores_incomplete_directories(tmp_path):
    data = tmp_path / "data"
    (data / "snapshots" / "v1").mkdir(parents=True)
    (data / "snapshots" / "v1" / "employees.csv").write_text("employee_id\ne1\n", encoding="utf-8")
    (data / "snapshots" / "incomplete").mkdir()
    assert [path.name for path in snapshot_directories(data)] == ["v1"]

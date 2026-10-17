import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from orgchart.auth import hash_password, verify_password
from orgchart.evaluation import evaluate_predictions
from orgchart.validation import validate_edges


def test_validation_rejects_self_cross_company_and_cycles():
    employees = pd.DataFrame([
        {"company_id": "A", "employee_id": "a"},
        {"company_id": "A", "employee_id": "b"},
        {"company_id": "B", "employee_id": "c"},
    ])
    edges = pd.DataFrame([
        {"company_id": "A", "employee_id": "a", "manager_employee_id": "a"},
        {"company_id": "A", "employee_id": "b", "manager_employee_id": "c"},
        {"company_id": "A", "employee_id": "a", "manager_employee_id": "b"},
        {"company_id": "A", "employee_id": "b", "manager_employee_id": "a"},
    ])
    reasons = {issue["reason"] for issue in validate_edges(employees, edges)}
    assert {"self_reporting", "cross_company", "multiple_managers", "cycle"} <= reasons


def test_metrics_zero_denominators_and_correct_edges():
    predictions = pd.DataFrame([
        {"employee_id": "e1", "manager_employee_id": "m1", "status": "accepted"},
        {"employee_id": "e2", "manager_employee_id": None, "status": "unresolved"},
    ])
    truth = pd.DataFrame([{ "employee_id": "e1", "manager_employee_id": "m1" }])
    report = evaluate_predictions(predictions, truth)
    assert report["edge_precision"] == 1
    assert report["edge_recall"] == 1
    assert report["employee_coverage"] == 0.5
    assert evaluate_predictions(predictions.iloc[0:0], truth.iloc[0:0])["f1"] == 0


def test_password_hash_verification():
    configured = hash_password("a-long-demo-password")
    assert verify_password("a-long-demo-password", configured)
    assert not verify_password("incorrect-password", configured)
    assert not verify_password("password", "sha256:" + "0" * 64)

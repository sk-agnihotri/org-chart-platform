import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate_dataset import FIRST_NAMES, LAST_NAMES, generate_dataset


def test_counts_ids_and_manager_isolation():
    data = generate_dataset(seed=11, company_count=500)
    companies, employees = data["companies"], data["employees"]
    assert len(companies) == 500
    assert companies.company_id.is_unique
    assert employees.employee_id.is_unique
    assert employees.groupby("company_id").size().between(100, 250).all()
    assert "manager_employee_id" not in employees.columns
    assert data["ground_truth"].employee_id.is_unique
    assert data["ground_truth"].manager_employee_id.notna().any()
    assert employees.full_name.map(lambda name: name.split()[0] in FIRST_NAMES and name.split()[-1] in LAST_NAMES).all()


def test_seed_reproduces_frames():
    first = generate_dataset(seed=23, company_count=500)
    second = generate_dataset(seed=23, company_count=500)
    for sheet in first:
        pd.testing.assert_frame_equal(first[sheet], second[sheet])


def test_management_layers_have_four_to_eight_reports():
    data = generate_dataset(seed=17, company_count=500)
    employees = data["employees"]
    truth = data["ground_truth"]
    for company_id, company_people in employees.groupby("company_id"):
        company_truth = truth[truth.company_id == company_id]
        functional_executive_id = f"{company_id}-E002"
        director_ids = company_people.loc[company_people.seniority_level == "director", "employee_id"].tolist()
        exec_reports = company_truth.loc[(company_truth.manager_employee_id == functional_executive_id) & company_truth.employee_id.isin(director_ids)]
        assert 6 <= len(exec_reports) <= 8
        assert set(exec_reports.employee_id) == set(director_ids)
        for director_id in director_ids:
            manager_reports = company_truth.loc[company_truth.manager_employee_id == director_id]
            assert 4 <= len(manager_reports) <= 8
            assert employees.loc[employees.employee_id.isin(manager_reports.employee_id), "seniority_level"].eq("manager").all()


def test_generator_requires_assessment_minimum():
    try:
        generate_dataset(seed=1, company_count=499)
    except ValueError as exc:
        assert "at least 500" in str(exc)
    else:
        raise AssertionError("expected company-count validation")

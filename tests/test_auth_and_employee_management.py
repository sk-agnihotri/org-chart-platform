import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from orgchart.auth import User, authenticate, can_manage_employees, hash_password, parse_users
from orgchart.data_mutations import add_employee, remove_employee


def test_username_password_and_roles():
    encoded = hash_password("long-enough-demo-password")
    users = parse_users('[{"username":"manager1","role":"manager","password_hash":"' + encoded + '","company_ids":["A"]}]')
    user = authenticate("MANAGER1", "long-enough-demo-password", users)
    assert user and user.role == "manager"
    assert can_manage_employees(user, "A")
    assert not can_manage_employees(user, "B")
    assert authenticate("manager1", "wrong-password", users) is None
    assert can_manage_employees(User("root", "admin"), "any-company")
    assert not can_manage_employees(User("viewer", "readonly"), "A")


def test_user_configuration_validation():
    with pytest.raises(ValueError):
        parse_users('[{"username":"bad","role":"root","password_hash":"x"}]')


def test_add_remove_employee_updates_dataset_and_invalidates_labels(tmp_path):
    employees = pd.DataFrame([
        {"company_id": "A", "employee_id": "A-E001", "full_name": "Alex Example", "job_title": "Director of Engineering", "department": "Engineering", "seniority_level": "director", "location": "Remote", "employment_type": "full_time", "tenure_years": 1.0},
    ])
    employees.to_csv(tmp_path / "employees.csv", index=False)
    pd.DataFrame([{"company_id": "A", "company_name": "Alpha", "employee_count": 1, "size_band": "100-149"}]).to_csv(tmp_path / "companies.csv", index=False)
    pd.DataFrame([{"company_id": "A", "employee_id": "A-E001", "manager_employee_id": None}]).to_csv(tmp_path / "ground_truth.csv", index=False)
    pd.DataFrame([{"company_id": "A", "employee_id": "A-E001", "title_missing": False, "department_missing": False, "title_abbreviated": False, "title_case_corrupted": False, "attributes_corrupted": False}]).to_csv(tmp_path / "data_quality.csv", index=False)
    pd.DataFrame([{"key": "seed", "value": 42}]).to_csv(tmp_path / "dataset_metadata.csv", index=False)

    new_id = add_employee(tmp_path, {"company_id": "A", "full_name": "Jamie New", "job_title": "Software Engineer", "department": "Engineering", "seniority_level": "individual_contributor", "location": "Remote", "employment_type": "full_time", "tenure_years": 0})
    assert new_id == "A-E002"
    assert len(pd.read_csv(tmp_path / "employees.csv")) == 2
    assert pd.read_csv(tmp_path / "companies.csv").employee_count.item() == 2
    metadata = pd.read_csv(tmp_path / "dataset_metadata.csv").set_index("key").value.to_dict()
    assert metadata["user_modified"] == "true"
    assert metadata["evaluation_ground_truth_valid"] == "false"

    truth = pd.read_csv(tmp_path / "ground_truth.csv", dtype={"manager_employee_id": "string"})
    truth.loc[truth.employee_id == "A-E001", "manager_employee_id"] = new_id
    truth.to_csv(tmp_path / "ground_truth.csv", index=False)
    remove_employee(tmp_path, new_id, "A")
    assert len(pd.read_csv(tmp_path / "employees.csv")) == 1
    assert pd.isna(pd.read_csv(tmp_path / "ground_truth.csv").loc[0, "manager_employee_id"])
    next_id = add_employee(tmp_path, {"company_id": "A", "full_name": "Taylor Next", "job_title": "Software Engineer"})
    assert next_id == "A-E003"

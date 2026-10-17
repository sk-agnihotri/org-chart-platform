from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f"{path.stem}-", suffix=".csv.tmp", dir=path.parent)
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        frame.to_csv(temporary_path, index=False)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def add_employee(data_dir: Path, record: dict[str, Any]) -> str:
    employees_path = data_dir / "employees.csv"
    employees = pd.read_csv(employees_path)
    company_id = str(record["company_id"])
    if company_id not in set(employees.company_id):
        raise ValueError("Unknown company ID.")
    if not str(record.get("full_name", "")).strip() or not str(record.get("job_title", "")).strip():
        raise ValueError("Name and job title are required.")
    counter_path = data_dir / "employee_id_counters.csv"
    if counter_path.exists():
        counters = pd.read_csv(counter_path, dtype={"company_id": str}).set_index("company_id")["next_number"].to_dict()
    else:
        counters = {}
        for current_company, group in employees.groupby("company_id"):
            numbers = [int(value.rsplit("E", 1)[-1]) for value in group.employee_id.astype(str) if value.rsplit("E", 1)[-1].isdigit()]
            counters[current_company] = max(numbers, default=0) + 1
    next_number = int(counters.get(company_id, 1))
    employee_id = f"{company_id}-E{next_number:03d}"
    counters[company_id] = next_number + 1
    _atomic_csv(pd.DataFrame([{"company_id": key, "next_number": value} for key, value in counters.items()]), counter_path)
    row = {"company_id": company_id, "employee_id": employee_id, "full_name": str(record["full_name"]).strip(), "job_title": str(record["job_title"]).strip(), "department": record.get("department"), "seniority_level": record.get("seniority_level", "individual_contributor"), "location": record.get("location") or "Not specified", "employment_type": record.get("employment_type", "full_time"), "tenure_years": record.get("tenure_years", 0.0)}
    updated = employees.copy()
    updated.loc[len(updated)] = row

    quality_path = data_dir / "data_quality.csv"
    quality = pd.read_csv(quality_path)
    quality_row = {column: False if column not in {"company_id", "employee_id"} else company_id if column == "company_id" else employee_id for column in quality.columns}
    if "title_missing" in quality_row:
        quality_row["title_missing"] = not bool(row["job_title"])
    if "department_missing" in quality_row:
        quality_row["department_missing"] = not bool(row["department"])
    if "attributes_corrupted" in quality_row:
        quality_row["attributes_corrupted"] = bool(quality_row.get("title_missing") or quality_row.get("department_missing"))
    quality = pd.concat([quality, pd.DataFrame([quality_row], columns=quality.columns)], ignore_index=True)

    truth_path = data_dir / "ground_truth.csv"
    truth = pd.read_csv(truth_path)
    truth_row = {column: company_id if column == "company_id" else employee_id if column == "employee_id" else None for column in truth.columns}
    truth = pd.concat([truth, pd.DataFrame([truth_row], columns=truth.columns)], ignore_index=True)

    _atomic_csv(updated, employees_path)
    _atomic_csv(quality, quality_path)
    _atomic_csv(truth, truth_path)
    _update_company_counts(data_dir, updated)
    _mark_evaluation_invalid(data_dir)
    return employee_id


def remove_employee(data_dir: Path, employee_id: str, company_id: str) -> None:
    employees_path = data_dir / "employees.csv"
    employees = pd.read_csv(employees_path)
    match = (employees.employee_id == employee_id) & (employees.company_id == company_id)
    if not match.any():
        raise ValueError("Employee does not exist in the selected company.")
    _atomic_csv(employees.loc[~match].copy(), employees_path)
    for filename in ("data_quality.csv", "ground_truth.csv"):
        path = data_dir / filename
        if path.exists():
            frame = pd.read_csv(path)
            if filename == "ground_truth.csv" and "manager_employee_id" in frame:
                frame.loc[frame.manager_employee_id == employee_id, "manager_employee_id"] = None
            frame = frame.loc[~((frame.employee_id == employee_id) & (frame.company_id == company_id))].copy()
            _atomic_csv(frame, path)
    _update_company_counts(data_dir, employees.loc[~match].copy())
    _mark_evaluation_invalid(data_dir)


def _update_company_counts(data_dir: Path, employees: pd.DataFrame) -> None:
    path = data_dir / "companies.csv"
    companies = pd.read_csv(path)
    counts = employees.groupby("company_id").size().to_dict()
    companies["employee_count"] = companies.company_id.map(counts).fillna(0).astype(int)
    companies["size_band"] = companies.employee_count.map(lambda count: "100-149" if count < 150 else "150-199" if count < 200 else "200-250" if count <= 250 else "250+")
    _atomic_csv(companies, path)


def _mark_evaluation_invalid(data_dir: Path) -> None:
    path = data_dir / "dataset_metadata.csv"
    metadata = pd.read_csv(path)
    for key, value in (("user_modified", "true"), ("evaluation_ground_truth_valid", "false")):
        metadata = metadata.loc[metadata.key != key]
        metadata = pd.concat([metadata, pd.DataFrame([{"key": key, "value": value}])], ignore_index=True)
    _atomic_csv(metadata, path)

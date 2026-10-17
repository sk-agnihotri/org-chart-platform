from pathlib import Path

import pandas as pd


def load_observable_data(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    companies = pd.read_csv(data_dir / "companies.csv")
    employees = pd.read_csv(data_dir / "employees.csv")
    taxonomy = pd.read_csv(data_dir / "title_taxonomy.csv")
    if "manager_employee_id" in employees.columns:
        raise ValueError("observable employee data must not contain manager labels")
    return companies, employees, taxonomy

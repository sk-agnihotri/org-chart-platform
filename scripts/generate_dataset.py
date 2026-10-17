from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

INDUSTRIES = ["Technology", "Healthcare", "Financial Services", "Retail", "Manufacturing", "Education"]
STAGES = ["Seed", "Series A", "Series B", "Growth", "Established"]
DEPARTMENTS = ["Engineering", "Sales", "Marketing", "People", "Finance", "Operations", "Product", "Customer Success"]
FIRST_NAMES = ["Aarav", "Aditi", "Advait", "Ananya", "Arjun", "Diya", "Ishaan", "Kavya", "Meera", "Neha", "Priya", "Rahul", "Rohan", "Saanvi", "Sanjay", "Vihaan", "Yash", "Zoya", "Ira", "Kabir", "Nisha", "Dev", "Mira", "Kiran", "Anika", "Parth", "Tara", "Aditya", "Ishita", "Vikram", "Sneha", "Om", "Riya", "Krish", "Pooja", "Manav"]
LAST_NAMES = ["Agarwal", "Bansal", "Chatterjee", "Desai", "Gupta", "Iyer", "Joshi", "Kapoor", "Kulkarni", "Malhotra", "Mehta", "Menon", "Mishra", "Mukherjee", "Nair", "Patel", "Rao", "Reddy", "Saxena", "Shah", "Sharma", "Shetty", "Singh", "Srinivasan", "Verma", "Pillai", "Banerjee", "Das", "Khan", "Kumar", "Jain", "Ghosh", "Sengupta", "Thakur", "Naidu", "Bhatt"]

ROLE_TEMPLATES = {
    "Engineering": ["Software Engineer", "Senior Software Engineer", "Engineering Manager", "Director of Engineering"],
    "Sales": ["Account Executive", "Senior Account Executive", "Sales Manager", "Director of Sales"],
    "Marketing": ["Marketing Specialist", "Senior Marketing Manager", "Marketing Manager", "Director of Marketing"],
    "People": ["People Operations Specialist", "HR Business Partner", "People Manager", "Director of People"],
    "Finance": ["Financial Analyst", "Senior Accountant", "Finance Manager", "Director of Finance"],
    "Operations": ["Operations Associate", "Senior Operations Analyst", "Operations Manager", "Director of Operations"],
    "Product": ["Product Analyst", "Senior Product Manager", "Product Manager", "Director of Product"],
    "Customer Success": ["Customer Success Associate", "Senior Customer Success Manager", "Customer Success Manager", "Director of Customer Success"],
}
ABBREVIATIONS = {"Software Engineer": "SWE", "Engineering Manager": "Eng Manager", "Director of Engineering": "Eng Director", "Account Executive": "AE", "Human Resources": "HR"}
EXECUTIVE_ROLES = ["Chief Executive Officer", "Chief Operating Officer", "Chief Technology Officer", "Chief Financial Officer"]
COMPANY_NAMES = ["Aarohan", "Aarunya", "Aashray", "Aavishkar", "Akshara", "Amara", "Ananta", "Arohan", "Astitva", "Bharat", "Chaitanya", "Daksha", "Dharohar", "Ekatva", "Gati", "Indus", "Iraaya", "Jeevika", "Kaveri", "Navika", "Nirmaan", "Pragati", "Sampada", "Sankalp", "Srishti", "Sudarshan", "Tarang", "Udaan", "Vistaar", "Yukti"]


def _make_company(rng: random.Random, index: int) -> tuple[dict, list[dict], list[dict], list[dict]]:
    company_id = f"COMP-{index:04d}"
    employee_count = rng.randint(100, 250)
    department_count = rng.choice([6, 7, 8])
    departments = rng.sample(DEPARTMENTS, department_count)
    stage = rng.choice(STAGES)
    structure = rng.choices(["functional", "flat_startup", "matrix_like", "executive_led"], [48, 12, 15, 25])[0]
    company = {
        "company_id": company_id,
        "company_name": f"{rng.choice(COMPANY_NAMES)} {rng.choice(['Labs', 'Group', 'Works', 'Systems', 'Co'])} {index:03d}",
        "industry": rng.choice(INDUSTRIES),
        "stage": stage,
        "size_band": "100-149" if employee_count < 150 else "150-199" if employee_count < 200 else "200-250",
        "employee_count": employee_count,
        "structure_type": structure,
        "founded_year": rng.randint(1998, 2024),
    }
    people: list[dict] = []
    truth: list[dict] = []
    quality: list[dict] = []

    def add_employee(department: str | None, title: str, level: int, manager: str | None) -> str:
        emp_num = len(people) + 1
        employee_id = f"{company_id}-E{emp_num:03d}"
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        raw_title = title
        if rng.random() < 0.09:
            raw_title = ABBREVIATIONS.get(title, title)
        if rng.random() < 0.06:
            raw_title = raw_title.lower()
        raw_department = department
        if rng.random() < 0.035:
            raw_department = None
        if rng.random() < 0.018:
            raw_title = None
        people.append({
            "company_id": company_id,
            "employee_id": employee_id,
            "full_name": name,
            "job_title": raw_title,
            "department": raw_department,
            "seniority_level": ["executive", "director", "manager", "individual_contributor"][min(level, 3)],
            "location": rng.choice(["New York", "London", "Toronto", "Bengaluru", "Remote", "Singapore"]),
            "employment_type": rng.choice(["full_time", "full_time", "full_time", "contract"]),
            "tenure_years": round(rng.uniform(0.1, 15), 1),
        })
        truth.append({"company_id": company_id, "employee_id": employee_id, "manager_employee_id": manager})
        quality.append({
            "company_id": company_id,
            "employee_id": employee_id,
            "title_missing": raw_title is None,
            "department_missing": raw_department is None,
            "title_abbreviated": raw_title in ABBREVIATIONS.values(),
            "title_case_corrupted": bool(raw_title and raw_title.islower()),
            "attributes_corrupted": bool(raw_title is None or raw_department is None or raw_title in ABBREVIATIONS.values()),
        })
        return employee_id

    ceo_id = add_employee(None, "Chief Executive Officer", 0, None)
    functional_exec_id = add_employee(None, rng.choice(EXECUTIVE_ROLES[1:]), 0, ceo_id)
    dept_managers: dict[str, list[str]] = {}
    for department in departments:
        director = add_employee(department, ROLE_TEMPLATES[department][3], 1, functional_exec_id)
        manager_count = rng.randint(4, 8)
        dept_managers[department] = [
            add_employee(department, ROLE_TEMPLATES[department][2], 2, director)
            for _ in range(manager_count)
        ]

    while len(people) < employee_count:
        department = rng.choice(departments)
        manager = rng.choice(dept_managers[department])
        title = rng.choice(ROLE_TEMPLATES[department][:2])
        # Flat startups and selected teams allow skipped layers or direct executive reports.
        if structure == "flat_startup" and rng.random() < 0.2:
            manager = functional_exec_id
        if rng.random() < 0.045:
            manager = None
        add_employee(department, title, 3, manager)

    return company, people, truth, quality


def generate_dataset(seed: int = 42, company_count: int = 500) -> dict[str, pd.DataFrame]:
    if company_count < 500:
        raise ValueError("company_count must be at least 500")
    rng = random.Random(seed)
    companies, employees, ground_truth, quality = [], [], [], []
    for index in range(1, company_count + 1):
        company, people, truth, issues = _make_company(rng, index)
        companies.append(company)
        employees.extend(people)
        ground_truth.extend(truth)
        quality.extend(issues)

    taxonomy_rows = []
    for department, titles in ROLE_TEMPLATES.items():
        for title in titles:
            taxonomy_rows.append({"canonical_title": title, "department": department, "seniority_level": "director" if title.startswith("Director") else "manager" if "Manager" in title else "individual_contributor", "is_management": "Manager" in title or title.startswith("Director"), "is_executive": False, "aliases": ""})
    taxonomy_rows.extend([
        {"canonical_title": title, "department": "Executive", "seniority_level": "executive", "is_management": True, "is_executive": True, "aliases": ""}
        for title in EXECUTIVE_ROLES
    ])
    metadata = [{"key": "seed", "value": seed}, {"key": "company_count", "value": company_count}, {"key": "generator_version", "value": "0.2.0"}, {"key": "management_span", "value": "4-8 reports per executive/director layer"}, {"key": "ground_truth_note", "value": "Synthetic hierarchy; not evidence of real-world accuracy."}]
    return {
        "companies": pd.DataFrame(companies),
        "employees": pd.DataFrame(employees),
        "ground_truth": pd.DataFrame(ground_truth),
        "title_taxonomy": pd.DataFrame(taxonomy_rows),
        "data_quality": pd.DataFrame(quality),
        "dataset_metadata": pd.DataFrame(metadata),
    }


def write_dataset(seed: int, company_count: int, output_dir: Path) -> dict:
    sheets = generate_dataset(seed, company_count)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "employee_id_counters.csv").unlink(missing_ok=True)
    for name, frame in sheets.items():
        frame.to_csv(output_dir / f"{name}.csv", index=False)
    checksums = {
        f"{name}.csv": hashlib.sha256((output_dir / f"{name}.csv").read_bytes()).hexdigest()
        for name in sheets
    }
    manifest = {
        "seed": seed,
        "company_count": len(sheets["companies"]),
        "employee_count": len(sheets["employees"]),
        "files": {f"{name}.csv": {"rows": len(frame), "columns": list(frame.columns)} for name, frame in sheets.items()},
        "sha256": checksums,
        "ground_truth_is_evaluation_only": True,
    }
    (output_dir / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the deterministic synthetic org-chart workbook.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--companies", type=int, default=500)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    print(json.dumps(write_dataset(args.seed, args.companies, args.output_dir), indent=2))


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from orgchart.evaluation import evaluate_predictions
from orgchart.inference import InferenceConfig, infer_company


def main() -> None:
    data = ROOT / "data"
    companies = pd.read_csv(data / "companies.csv")
    employees = pd.read_csv(data / "employees.csv")
    taxonomy = pd.read_csv(data / "title_taxonomy.csv")
    truth = pd.read_csv(data / "ground_truth.csv")
    metadata = pd.read_csv(data / "dataset_metadata.csv")
    if ((metadata.key == "user_modified") & (metadata.value.astype(str).str.lower() == "true")).any():
        raise SystemExit("Evaluation stopped: employee records were edited after synthetic ground truth generation. Regenerate the dataset for a clean evaluation run.")
    company_ids = companies.sample(frac=1, random_state=42).company_id.tolist()
    split = {"development": company_ids[:300], "validation": company_ids[300:400], "test": company_ids[400:]}
    test_ids = set(split["test"])
    predictions = infer_company(employees[employees.company_id.isin(test_ids)], InferenceConfig(), taxonomy)
    report = {"split_seed": 42, "split_company_counts": {key: len(value) for key, value in split.items()}, "threshold_source": "predeclared baseline; no held-out test tuning", **evaluate_predictions(predictions, truth[truth.company_id.isin(test_ids)])}
    output = ROOT / "reports"
    output.mkdir(exist_ok=True)
    (output / "evaluation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

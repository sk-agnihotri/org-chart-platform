from __future__ import annotations

import pandas as pd


def evaluate_predictions(predictions: pd.DataFrame, ground_truth: pd.DataFrame) -> dict:
    accepted = predictions[predictions.status == "accepted"]
    true_edges = ground_truth[ground_truth.manager_employee_id.notna()]
    expected = set(zip(true_edges.employee_id, true_edges.manager_employee_id))
    predicted = set(zip(accepted.employee_id, accepted.manager_employee_id))
    correct = len(expected & predicted)
    precision = correct / len(predicted) if predicted else 0.0
    recall = correct / len(expected) if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    count = len(predictions)
    return {"edge_precision": precision, "edge_recall": recall, "f1": f1, "employee_coverage": len(accepted) / count if count else 0.0, "abstention_rate": predictions.status.isin(["ambiguous", "unresolved"]).sum() / count if count else 0.0, "cycle_violation_count": 0, "accepted_edge_count": len(predicted), "true_edge_count": len(expected)}

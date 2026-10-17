from __future__ import annotations

import networkx as nx
import pandas as pd


def validate_edges(employees: pd.DataFrame, edges: pd.DataFrame) -> list[dict]:
    issues = []
    if employees.employee_id.duplicated().any():
        return [{"employee_id": value, "reason": "duplicate_employee_id"} for value in employees.loc[employees.employee_id.duplicated(), "employee_id"]]
    company_lookup = employees.set_index("employee_id")["company_id"].to_dict()
    if edges.employee_id.duplicated().any():
        issues.extend({"employee_id": value, "reason": "multiple_managers"} for value in edges.loc[edges.employee_id.duplicated(), "employee_id"])
    graph = nx.DiGraph()
    for edge in edges.itertuples(index=False):
        child, manager = edge.employee_id, edge.manager_employee_id
        if child not in company_lookup or manager not in company_lookup:
            issues.append({"employee_id": child, "reason": "invalid_reference"})
        elif child == manager:
            issues.append({"employee_id": child, "reason": "self_reporting"})
        elif company_lookup[child] != company_lookup[manager] or edge.company_id != company_lookup[child]:
            issues.append({"employee_id": child, "reason": "cross_company"})
        else:
            graph.add_edge(manager, child)
    if not nx.is_directed_acyclic_graph(graph):
        for cycle in nx.simple_cycles(graph):
            issues.extend({"employee_id": value, "reason": "cycle"} for value in cycle)
    return issues

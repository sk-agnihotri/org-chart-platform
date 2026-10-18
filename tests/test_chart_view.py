import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from orgchart.chart_view import CARD_HEIGHT, CARD_WIDTH, render_org_chart_svg


def test_org_chart_cards_keep_fixed_dimensions_and_reflow_without_horizontal_scroll():
    employees = pd.DataFrame([
        {"employee_id": "e1", "full_name": "Ananya Sharma with a Very Long Name", "department": "Research & Development Department", "seniority_level": "individual_contributor", "job_title": "Principal Research Software Engineer"},
        {"employee_id": "e2", "full_name": "Aarav Rao", "department": "Research", "seniority_level": "director", "job_title": "Director of Research"},
    ])
    predictions = pd.DataFrame([{"employee_id": "e1", "manager_employee_id": "e2", "status": "accepted"}])

    rendered = render_org_chart_svg(employees, predictions)

    assert f"const cardWidth = {CARD_WIDTH}" in rendered
    assert f"const cardHeight = {CARD_HEIGHT}" in rendered
    assert "overflow:hidden" in rendered
    assert 'id="chart-zoom-in"' in rendered
    assert 'id="chart-zoom-out"' in rendered
    assert 'id="chart-fit"' in rendered
    assert "function zoomAt" in rendered
    assert "pointerdown" in rendered
    assert "const collapsedNodes = new Set()" in rendered
    assert 'symbol.textContent = collapsedNodes.has(node.id) ? "+" : "−"' in rendered
    assert "collapsedNodes.delete(node.id)" in rendered
    assert 'toggle.addEventListener("pointerdown", event => event.stopPropagation())' in rendered
    assert "event.target.closest('[role=\"button\"]')" in rendered
    assert "const columns = Math.max(1" in rendered
    assert "text: clipped(node.name" in rendered
    assert "Ananya Sharma with a Very Long Name" in rendered
    assert "Research \\u0026 Development Department" in rendered
    assert "overflow-x:auto" not in rendered


def test_org_chart_renders_fallback_cards_when_no_relationships():
    employees = pd.DataFrame([
        {"employee_id": "e1", "full_name": "Asha Rao", "department": None, "seniority_level": None, "job_title": None},
    ])
    predictions = pd.DataFrame(columns=["employee_id", "manager_employee_id", "status"])

    rendered = render_org_chart_svg(employees, predictions)

    assert '"department": "Department not set"' in rendered
    assert '"designation": "Designation Not Set"' in rendered
    assert '"title": "Title unavailable"' in rendered

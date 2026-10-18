from __future__ import annotations

import json

import networkx as nx
import pandas as pd


CARD_WIDTH = 280
CARD_HEIGHT = 124
HORIZONTAL_GAP = 18
VERTICAL_GAP = 54


def _value(value, fallback: str) -> str:
    return fallback if pd.isna(value) or not str(value).strip() else str(value)


def render_org_chart_svg(employees: pd.DataFrame, predictions: pd.DataFrame) -> str:
    graph = nx.DiGraph()
    graph.add_nodes_from(employees.employee_id)
    if not predictions.empty:
        accepted = predictions[predictions.status == "accepted"]
        graph.add_edges_from((row.manager_employee_id, row.employee_id) for row in accepted.itertuples())

    people = employees.set_index("employee_id")
    depth_by_node = {}
    for node in nx.topological_sort(graph):
        depth_by_node[node] = max((depth_by_node[parent] + 1 for parent in graph.predecessors(node)), default=0)
    nodes = []
    for node, depth in depth_by_node.items():
        person = people.loc[node]
        nodes.append({
            "id": str(node),
            "parent": str(next(iter(graph.predecessors(node)), "")),
            "depth": depth,
            "name": _value(person.get("full_name"), "Name unavailable"),
            "department": _value(person.get("department"), "Department not set"),
            "designation": _value(person.get("seniority_level"), "Designation not set").replace("_", " ").title(),
            "role": _value(person.get("seniority_level"), "").casefold().replace("_", " "),
            "title": _value(person.get("job_title"), "Title unavailable"),
        })
    nodes_json = json.dumps(nodes, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return f'''<div id="org-chart-wrap" style="width:100%;height:800px;display:flex;flex-direction:column;overflow:hidden;border:1px solid #e2e8f0;border-radius:10px;background:#fff">
<div style="min-height:42px;display:flex;align-items:center;justify-content:space-between;gap:8px;padding:6px 10px;border-bottom:1px solid #e2e8f0;background:#fff;font-family:Arial,sans-serif;flex-wrap:wrap">
<div aria-label="Designation legend" style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:12px;color:#415674">
<span><i style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#e65365;margin-right:4px"></i>Executive</span><span><i style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#f28c45;margin-right:4px"></i>Director</span><span><i style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#3979d6;margin-right:4px"></i>Manager</span><span><i style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#32b878;margin-right:4px"></i>Senior</span><span><i style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#9a7ac7;margin-right:4px"></i>IC</span>
</div><div style="display:flex;align-items:center;justify-content:flex-end;gap:6px">
<button id="chart-zoom-out" type="button" aria-label="Zoom out" style="height:30px;padding:0 12px;border:1px solid #cbd8e8;border-radius:6px;background:#fff;color:#172b4d;font-size:16px;cursor:pointer">−</button>
<button id="chart-fit" type="button" style="height:30px;padding:0 12px;border:1px solid #cbd8e8;border-radius:6px;background:#fff;color:#172b4d;font-size:12px;cursor:pointer">Fit</button>
<button id="chart-zoom-in" type="button" aria-label="Zoom in" style="height:30px;padding:0 12px;border:1px solid #cbd8e8;border-radius:6px;background:#fff;color:#172b4d;font-size:16px;cursor:pointer">+</button>
</div></div>
<svg id="org-chart" role="img" aria-label="Inferred organizational chart" style="display:block;width:100%;height:auto;min-height:0;flex:1;background:#fff;touch-action:none;cursor:grab"></svg>
<script>
const chartNodes = {nodes_json};
const chartSvg = document.getElementById("org-chart");
const chartWrap = document.getElementById("org-chart-wrap");
const ns = "http://www.w3.org/2000/svg";
const cardWidth = {CARD_WIDTH};
const cardHeight = {CARD_HEIGHT};
const rowGap = {HORIZONTAL_GAP};
const levelGap = {VERTICAL_GAP};
const roleColors = {{"executive": "#e65365", "director": "#f28c45", "manager": "#3979d6", "senior": "#32b878", "individual contributor": "#9a7ac7", "ic": "#9a7ac7"}};
let zoom = 1;
let panX = 0;
let panY = 0;
let fitMode = true;
let contentWidth = 0;
let contentHeight = 0;
let viewportWidth = 0;
let viewportHeight = 0;
let dragState = null;
const collapsedNodes = new Set();
const nodesById = new Map(chartNodes.map(node => [node.id, node]));
function isVisible(node) {{
  let parentId = node.parent;
  const seen = new Set();
  while (parentId && !seen.has(parentId)) {{
    if (collapsedNodes.has(parentId)) return false;
    seen.add(parentId);
    parentId = nodesById.get(parentId)?.parent || "";
  }}
  return true;
}}
function addSvg(tag, attrs, parent) {{
  const element = document.createElementNS(ns, tag);
  for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, value);
  parent.appendChild(element);
  return element;
}}
function drawChart() {{
  const width = Math.max(cardWidth, Math.floor(chartSvg.clientWidth));
  const height = Math.max(cardHeight, Math.floor(chartSvg.clientHeight));
  const padding = 12;
  const columns = Math.max(1, Math.floor((width - 2 * padding + rowGap) / (cardWidth + rowGap)));
  const gridWidth = columns * cardWidth + (columns - 1) * rowGap;
  const offsetX = Math.max(padding, (width - gridWidth) / 2);
  const visibleNodes = chartNodes.filter(isVisible);
  const nodesByDepth = new Map();
  const childCounts = new Map();
  for (const node of visibleNodes) {{
    if (!nodesByDepth.has(node.depth)) nodesByDepth.set(node.depth, []);
    nodesByDepth.get(node.depth).push(node);
  }}
  for (const node of chartNodes) {{
    if (node.parent) childCounts.set(node.parent, (childCounts.get(node.parent) || 0) + 1);
  }}
  const depths = [...nodesByDepth.keys()].sort((a, b) => a - b);
  const positions = new Map();
  let currentY = 24;
  for (const depth of depths) {{
    const levelNodes = nodesByDepth.get(depth).sort((a, b) => a.name.localeCompare(b.name));
    const rows = Math.ceil(levelNodes.length / columns);
    levelNodes.forEach((node, index) => {{
      const row = Math.floor(index / columns);
      const column = index % columns;
      positions.set(node.id, {{x: offsetX + cardWidth / 2 + column * (cardWidth + rowGap), y: currentY + cardHeight / 2 + row * (cardHeight + rowGap)}});
    }});
    currentY += rows * (cardHeight + rowGap) + levelGap;
  }}
  viewportWidth = width;
  viewportHeight = height;
  contentWidth = Math.max(width, gridWidth + 2 * padding);
  contentHeight = currentY;
  chartSvg.setAttribute("viewBox", `0 0 ${{width}} ${{height}}`);
  chartSvg.replaceChildren();
  const layer = addSvg("g", {{}}, chartSvg);
  for (const node of visibleNodes) {{
    if (!node.parent || !positions.has(node.parent)) continue;
    const parent = positions.get(node.parent);
    const child = positions.get(node.id);
    const startY = parent.y + cardHeight / 2;
    const endY = child.y - cardHeight / 2;
    const bend = Math.max(24, (endY - startY) * 0.5);
    addSvg("path", {{d: `M ${{parent.x}} ${{startY}} C ${{parent.x}} ${{startY + bend}}, ${{child.x}} ${{endY - bend}}, ${{child.x}} ${{endY}}`, fill: "none", stroke: "#aab4c0", "stroke-width": 2}}, layer);
  }}
  const measure = document.createElement("canvas").getContext("2d");
  function clipped(value, maxWidth, font) {{
    measure.font = font;
    if (measure.measureText(value).width <= maxWidth) return value;
    let text = value;
    while (text.length && measure.measureText(text + "…").width > maxWidth) text = text.slice(0, -1);
    return text.trimEnd() + "…";
  }}
  for (const node of visibleNodes) {{
    const point = positions.get(node.id);
    const left = point.x - cardWidth / 2;
    const top = point.y - cardHeight / 2;
    const group = addSvg("g", {{}}, layer);
    const roleColor = roleColors[node.role] || "#64748b";
    const tooltip = addSvg("title", {{}}, group);
    tooltip.textContent = `${{node.name}} | ${{node.department}} | ${{node.designation}} | ${{node.title}}`;
    addSvg("rect", {{x: left, y: top, width: cardWidth, height: cardHeight, rx: 10, fill: `${{roleColor}}12`, stroke: `${{roleColor}}80`, "stroke-width": 1.5}}, group);
    addSvg("rect", {{x: left, y: top + 10, width: 5, height: cardHeight - 20, rx: 2, fill: roleColor}}, group);
    const lines = [
      {{text: clipped(node.name, cardWidth - 40, "700 16px Arial"), y: top + 34, font: "Arial, sans-serif", size: 16, weight: 700, color: "#172b4d"}},
      {{text: `Department: ${{clipped(node.department, cardWidth - 44, "13px Arial")}}`, y: top + 62, font: "Arial, sans-serif", size: 13, color: "#415674"}},
      {{text: `Designation: ${{clipped(node.designation, cardWidth - 48, "13px Arial")}}`, y: top + 84, font: "Arial, sans-serif", size: 13, color: "#415674"}},
      {{text: clipped(node.title, cardWidth - 40, "12px Arial"), y: top + 106, font: "Arial, sans-serif", size: 12, color: "#65758b"}}
    ];
    for (const line of lines) {{
      const text = addSvg("text", {{x: left + 20, y: line.y, fill: line.color, "font-family": line.font, "font-size": line.size, "font-weight": line.weight || 400}}, group);
      text.textContent = line.text;
    }}
    if (childCounts.has(node.id)) {{
      const toggle = addSvg("g", {{role: "button", tabindex: 0, "aria-label": `${{collapsedNodes.has(node.id) ? "Expand" : "Collapse"}} reports for ${{node.name}}`, style: "cursor:pointer"}}, group);
      addSvg("circle", {{cx: left + cardWidth - 18, cy: top + 18, r: 11, fill: "#326cf4", stroke: "#fff", "stroke-width": 2}}, toggle);
      const symbol = addSvg("text", {{x: left + cardWidth - 18, y: top + 23, fill: "#fff", "font-family": "Arial, sans-serif", "font-size": 16, "font-weight": 700, "text-anchor": "middle", "pointer-events": "none"}}, toggle);
      symbol.textContent = collapsedNodes.has(node.id) ? "+" : "−";
      const toggleNode = event => {{
        event.stopPropagation();
        if (collapsedNodes.has(node.id)) collapsedNodes.delete(node.id);
        else collapsedNodes.add(node.id);
        drawChart();
      }};
      toggle.addEventListener("pointerdown", event => event.stopPropagation());
      toggle.addEventListener("click", toggleNode);
      toggle.addEventListener("keydown", event => {{
        if (event.key === "Enter" || event.key === " ") toggleNode(event);
      }});
    }}
  }}
  if (fitMode) fitChart();
  else applyTransform();
}}
function applyTransform() {{
  const layer = chartSvg.firstElementChild;
  if (layer) layer.setAttribute("transform", `translate(${{panX}} ${{panY}}) scale(${{zoom}})`);
}}
function fitChart() {{
  zoom = Math.min(1, viewportWidth / contentWidth, viewportHeight / contentHeight);
  panX = (viewportWidth - contentWidth * zoom) / 2;
  panY = (viewportHeight - contentHeight * zoom) / 2;
  fitMode = true;
  applyTransform();
}}
function zoomAt(nextZoom, x = viewportWidth / 2, y = viewportHeight / 2) {{
  const worldX = (x - panX) / zoom;
  const worldY = (y - panY) / zoom;
  zoom = Math.max(0.25, Math.min(3, nextZoom));
  panX = x - worldX * zoom;
  panY = y - worldY * zoom;
  fitMode = false;
  applyTransform();
}}
document.getElementById("chart-zoom-in").addEventListener("click", () => zoomAt(zoom * 1.2));
document.getElementById("chart-zoom-out").addEventListener("click", () => zoomAt(zoom / 1.2));
document.getElementById("chart-fit").addEventListener("click", fitChart);
chartSvg.addEventListener("pointerdown", event => {{
  if (event.target.closest('[role="button"]')) return;
  dragState = {{x: event.clientX, y: event.clientY, panX, panY}};
  chartSvg.setPointerCapture(event.pointerId);
  chartSvg.style.cursor = "grabbing";
}});
chartSvg.addEventListener("pointermove", event => {{
  if (!dragState) return;
  panX = dragState.panX + event.clientX - dragState.x;
  panY = dragState.panY + event.clientY - dragState.y;
  fitMode = false;
  applyTransform();
}});
chartSvg.addEventListener("pointerup", () => {{ dragState = null; chartSvg.style.cursor = "grab"; }});
chartSvg.addEventListener("pointercancel", () => {{ dragState = null; chartSvg.style.cursor = "grab"; }});
new ResizeObserver(drawChart).observe(chartWrap);
drawChart();
</script></div>'''

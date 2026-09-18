# -*- coding: utf-8 -*-
"""Graph Explorer: xuất 1 trang HTML độc lập (mở trực tiếp bằng browser).

Node bấm được -> hiện definition + aliases + MỌI nguồn kèm quote (explainability).
Edge bấm được -> hiện evidence quote + nguồn.
Không cần server, không cần internet (Cytoscape.js nhúng local qua CDN-free
fallback: dùng pure canvas? — dùng CDN đơn giản nhất cho hackathon demo).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<title>Knowledge Graph Explorer — Track C1</title>
<script src="https://unpkg.com/cytoscape@3.30.2/dist/cytoscape.min.js"></script>
<style>
  body { font-family: system-ui, sans-serif; margin: 0; display: flex; height: 100vh; }
  #graph { flex: 1; background: #fafbfc; }
  #panel { width: 380px; border-left: 1px solid #ddd; padding: 16px; overflow-y: auto; }
  h2 { font-size: 16px; margin: 4px 0; }
  .tag { display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 10px;
         background: #eef; margin: 2px 2px; }
  .src { font-size: 12px; background: #f4f6f8; border-left: 3px solid #48f;
         padding: 6px 8px; margin: 6px 0; }
  .src b { color: #236; }
  .quote { font-style: italic; color: #456; }
  #hint { color: #889; font-size: 13px; }
</style>
</head>
<body>
<div id="graph"></div>
<div id="panel">
  <h2>Knowledge Graph — Lesson Studio C1</h2>
  <p id="hint">Bấm vào một node (concept) hoặc một cạnh để xem nguồn truy vết.</p>
  <div id="detail"></div>
</div>
<script>
const GRAPH_DATA = __GRAPH_JSON__;

const cy = cytoscape({
  container: document.getElementById('graph'),
  elements: [
    ...GRAPH_DATA.nodes.map(n => ({
      data: { id: n.id, label: n.name, kind: n.type, weight: n.sources.length }
    })),
    ...GRAPH_DATA.edges.map((e, i) => ({
      data: { id: 'e' + i, source: e.source, target: e.target, kind: e.type, eidx: i }
    })),
  ],
  style: [
    { selector: 'node', style: {
        label: 'data(label)', 'text-wrap': 'wrap', 'font-size': 10,
        'background-color': 'data(color)',
        color: '#fff', 'text-valign': 'center', width: 'mapData(weight, 1, 8, 25, 55)',
        height: 'mapData(weight, 1, 8, 25, 55)' } },
    { selector: 'edge', style: {
        'line-color': 'data(color)',
        'target-arrow-shape': 'triangle', 'arrow-scale': 0.7,
        label: 'data(kind)', 'font-size': 7, color: '#99a', 'text-rotation': 'autorotate',
        'curve-style': 'bezier', width: 1.5 } },
  ],
  layout: { name: 'cose', animate: true, nodeRepulsion: 8000, idealEdgeLength: 90 },
});

const detail = document.getElementById('detail');
window.cy = cy;  // expose để kiểm thử/tự động hóa bấm node
const nodeById = Object.fromEntries(GRAPH_DATA.nodes.map(n => [n.id, n]));
const fmtSrc = s => s.page !== undefined ? `${s.file} · trang ${s.page}` : `${s.file} · lượt ${s.turn}`;

cy.on('tap', 'node', evt => {
  const n = nodeById[evt.target.id()];
  detail.innerHTML = `
    <h2>${n.name}</h2>
    ${n.aliases.length ? '<div>' + n.aliases.map(a => `<span class="tag">${a}</span>`).join('') + '</div>' : ''}
    <div><span class="tag">${n.type}</span><span class="tag">confidence ${n.confidence}</span>
         <span class="tag">${n.sources.length} nguồn</span></div>
    <p>${n.definition}</p>
    <h2>Nguồn (provenance)</h2>
    ${n.sources.map(s => `<div class="src"><b>${fmtSrc(s)}</b><br>${(s.section ? 'mục: ' + s.section + '<br>' : '')}</div>`).join('')}
    ${n.quotes.filter(Boolean).map(q => `<div class="src quote">“${q}”</div>`).join('')}`;
});

cy.on('tap', 'edge', evt => {
  const e = GRAPH_DATA.edges[evt.target.data('eidx')];
  const s = nodeById[e.source], t = nodeById[e.target];
  detail.innerHTML = `
    <h2>${s.name} → ${t.name}</h2>
    <div><span class="tag">${e.type}</span><span class="tag">confidence ${e.confidence}</span></div>
    <div class="src"><b>${fmtSrc(e.provenance)}</b></div>
    ${e.evidence_quote ? `<div class="src quote">“${e.evidence_quote}”</div>` : ''}`;
});
</script>
</body>
</html>
"""


def main():
    graph = json.loads((ROOT / "extraction" / "graph.json").read_text(encoding="utf-8"))
    # Cytoscape style không chạy biểu thức JS — gắn màu sẵn theo loại node/cạnh
    NODE_COLORS = {"concept": "#3498db", "example": "#f39c12", "misconception": "#e74c3c"}
    EDGE_COLORS = {"prerequisite": "#8e44ad", "contradicts": "#e74c3c", "broader": "#16a085",
                   "example-of": "#f39c12", "related": "#bdc3c7"}
    for n in graph["nodes"]:
        n["color"] = NODE_COLORS.get(n["type"], "#3498db")
    for e in graph["edges"]:
        e["color"] = EDGE_COLORS.get(e["type"], "#bdc3c7")
    html = HTML_TEMPLATE.replace(
        "__GRAPH_JSON__",
        json.dumps({"nodes": graph["nodes"], "edges": graph["edges"]}, ensure_ascii=False),
    )
    out = ROOT / "graph_explorer.html"
    out.write_text(html, encoding="utf-8")
    print(f"Nodes: {len(graph['nodes'])}, Edges: {len(graph['edges'])}")
    print(f"-> {out} (mở trực tiếp bằng browser)")


if __name__ == "__main__":
    main()

"""
Structured Hierarchical Graph Visualization Module (Track 2 -> Track 5)
Restructured for maximum readability:
- Top-to-Bottom Flow (Root prerequisites at top -> Advanced concepts at bottom)
- Rigid topological tiers (every node sits strictly on its pedagogical level)
- Uniform, consistent edges with clean vertical routing
- Elegant cards with badges for level, status, and verified course links
"""

import json
from typing import Optional
import networkx as nx
from dag_engine import RoadmapResult, get_dag_engine


def generate_interactive_html(
    roadmap: RoadmapResult,
    output_path: str = "roadmap_graph.html",
    title: Optional[str] = None,
) -> str:
    """
    Renders an ultra-structured, vertical hierarchical graph (Top-to-Bottom).
    Tier 1 (Foundations) sits at the very top, progressing cleanly downward.
    """
    page_title = title or f"مسیر یادگیری گام‌به‌گام: {roadmap.role_title_fa} ({roadmap.target_level})"

    engine = get_dag_engine()
    all_nodes_set = set(roadmap.known_concepts).union(set(roadmap.to_learn_concepts))
    subgraph = engine.graph.subgraph(all_nodes_set)

    # 1. Calculate strict topological depth from roots (Longest path to place nodes on correct vertical tier)
    node_depth = {}
    for node in nx.topological_sort(subgraph):
        preds = list(subgraph.predecessors(node))
        if not preds:
            node_depth[node] = 1
        else:
            node_depth[node] = max(node_depth[p] for p in preds) + 1

    max_depth = max(node_depth.values()) if node_depth else 1

    # Map concept_id to step info
    step_info = {s.concept_id: s for s in roadmap.steps}
    known_set = set(roadmap.known_concepts)

    vis_nodes = []
    for cid in all_nodes_set:
        cdata = engine.concepts[cid]
        is_known = cid in known_set
        tier = node_depth.get(cid, 1)
        level_str = cdata.get("level", "junior")
        s_data = step_info.get(cid)

        # Distinct card styling
        if is_known:
            bg_color = "#F1F5F9"
            border_color = "#94A3B8"
            font_color = "#475569"
            badge = "✓ از قبل می‌دانید"
        else:
            if level_str == "junior":
                bg_color = "#ECFDF5"
                border_color = "#10B981"
                font_color = "#065F46"
                badge = "سطح مقدماتی"
            elif level_str == "mid":
                bg_color = "#EFF6FF"
                border_color = "#3B82F6"
                font_color = "#1E40AF"
                badge = "سطح متوسط"
            else:
                bg_color = "#FAF5FF"
                border_color = "#8B5CF6"
                font_color = "#5B21B6"
                badge = "سطح پیشرفته"

        # Verified educational resources
        res_items = []
        if s_data and s_data.resources:
            for r in s_data.resources:
                free_lbl = " [رایگان]" if r.get("is_free") else ""
                res_items.append(
                    f"<li><a href='{r['url']}' target='_blank' style='color:#2563EB;'>{r['title']}</a>{free_lbl} ({r.get('provider','')})</li>"
                )
        res_html = ""
        if res_items:
            res_html = f"<div style='margin-top:6px;'><b>دوره‌های معتبر:</b><ul style='margin:4px 0; padding-right:16px;'>{''.join(res_items)}</ul></div>"

        tooltip = (
            f"<div dir='rtl' style='text-align:right; font-family:tahoma,sans-serif; max-width:280px; padding:6px;'>"
            f"<div style='font-size:14px; font-weight:bold;'>{cdata['title_fa']}</div>"
            f"<div style='font-size:11px; color:#64748B;'>{cdata['title_en']} | لایه {tier}</div>"
            f"<div style='font-size:12px; margin-top:4px;'><b>وضعیت:</b> {badge}</div>"
            f"{res_html}"
            f"</div>"
        )

        vis_nodes.append({
            "id": cid,
            "label": f"{cdata['title_fa']}\n({cdata['title_en']})",
            "title": tooltip,
            "level": tier,  # Strict vertical tier (1 = top, 2 = under, etc.)
            "color": {
                "background": bg_color,
                "border": border_color,
                "highlight": {"background": "#FEF3C7", "border": "#D97706"},
            },
            "font": {
                "color": font_color,
                "face": "Vazirmatn, Tahoma, sans-serif",
                "size": 13,
            },
            "shape": "box",
            "margin": {"top": 10, "bottom": 10, "left": 14, "right": 14},
            "borderWidth": 2,
            "shadow": {"enabled": True, "color": "rgba(0,0,0,0.06)", "size": 6, "x": 0, "y": 3},
        })

    # Uniform, structured vertical edges
    vis_edges = []
    for u, v in subgraph.edges():
        vis_edges.append({
            "from": u,
            "to": v,
            "arrows": {"to": {"enabled": True, "scaleFactor": 0.8}},
            "color": {"color": "#94A3B8", "highlight": "#F59E0B"},
            "width": 2,
            "smooth": {
                "type": "cubicBezier",
                "forceDirection": "vertical",
                "roundness": 0.4,
            },
        })

    html_content = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="UTF-8">
  <title>{page_title}</title>
  <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
  <link href="https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css" rel="stylesheet" type="text/css" />
  <style>
    * {{
      box-sizing: border-box;
      font-family: 'Vazirmatn', Tahoma, sans-serif;
    }}
    body, html {{
      margin: 0;
      padding: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
      background: #F8FAFC;
    }}
    #header {{
      height: 60px;
      background: #FFFFFF;
      border-bottom: 1px solid #E2E8F0;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 24px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }}
    #header h1 {{
      margin: 0;
      font-size: 17px;
      font-weight: 700;
      color: #0F172A;
    }}
    .legend {{
      display: flex;
      gap: 16px;
      font-size: 12px;
      align-items: center;
    }}
    .legend-item {{
      display: flex;
      align-items: center;
      gap: 6px;
      color: #334155;
    }}
    .pill {{
      width: 12px;
      height: 12px;
      border-radius: 3px;
    }}
    #network-container {{
      width: 100%;
      height: calc(100% - 60px);
    }}
    #stats-card {{
      position: absolute;
      bottom: 16px;
      right: 20px;
      background: rgba(255, 255, 255, 0.95);
      backdrop-filter: blur(8px);
      padding: 10px 18px;
      border-radius: 8px;
      border: 1px solid #E2E8F0;
      font-size: 13px;
      color: #1E293B;
      box-shadow: 0 4px 12px rgba(0,0,0,0.08);
      z-index: 10;
    }}
  </style>
</head>
<body>
  <div id="header">
    <h1>{page_title}</h1>
    <div class="legend">
      <div class="legend-item"><span class="pill" style="background:#F1F5F9; border:1px solid #94A3B8;"></span> تسلط دارید (تکمیل شده)</div>
      <div class="legend-item"><span class="pill" style="background:#ECFDF5; border:1px solid #10B981;"></span> پیش‌نیاز پایه (Junior)</div>
      <div class="legend-item"><span class="pill" style="background:#EFF6FF; border:1px solid #3B82F6;"></span> ابزار اصلی (Mid)</div>
      <div class="legend-item"><span class="pill" style="background:#FAF5FF; border:1px solid #8B5CF6;"></span> تخصص و معماری (Senior)</div>
    </div>
  </div>

  <div id="network-container"></div>

  <div id="stats-card">
    ⬇️ <b>ساختار مرحله‌ای بالا به پایین:</b> مفاهیم ریشه در بالاترین ردیف قرار دارند و پیش‌نیازها به سمت پایین جریان دارند.
    <br>
    ⚡ <b>زمان محاسبه:</b> {roadmap.computation_time_ms:.2f} میلی‌ثانیه | <b>کل مراحل:</b> {max_depth} لایه آموزشی | <b>نیاز به یادگیری:</b> {roadmap.to_learn_count} مهارت
  </div>

  <script type="text/javascript">
    const nodes = new vis.DataSet({json.dumps(vis_nodes, ensure_ascii=False)});
    const edges = new vis.DataSet({json.dumps(vis_edges, ensure_ascii=False)});

    const container = document.getElementById('network-container');
    const data = {{ nodes: nodes, edges: edges }};
    const options = {{
      layout: {{
        hierarchical: {{
          enabled: true,
          direction: 'UD',       // Strict Top-to-Bottom (Up to Down)
          sortMethod: 'directed',
          levelSeparation: 130,   // Clean vertical spacing between tiers
          nodeSpacing: 200,       // Generous horizontal spacing so nodes never overlap
          treeSpacing: 180,
          blockShifting: true,
          edgeMinimization: true,
          parentCentralization: true
        }}
      }},
      physics: {{
        enabled: false          // Fixed, clean deterministic layout
      }},
      interaction: {{
        hover: true,
        tooltipDelay: 80,
        zoomView: true,
        dragView: true
      }}
    }};

    const network = new vis.Network(container, data, options);
  </script>
</body>
</html>
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return output_path


if __name__ == "__main__":
    engine = get_dag_engine()
    
    # 1. Generate Structured Top-to-Bottom roadmap for Data Analyst Mid
    da_roadmap = engine.compute_roadmap(
        role_id="data_analyst",
        target_level="mid",
        known_concepts=["excel_basics", "sql_basics"],
    )
    generate_interactive_html(da_roadmap, "data_analyst_roadmap.html")
    print("Regenerated structured vertical tree for Data Analyst: data_analyst_roadmap.html")

    # 2. Generate Structured Top-to-Bottom roadmap for Backend Developer Mid
    be_roadmap = engine.compute_roadmap(
        role_id="backend_developer",
        target_level="mid",
        known_concepts=["python_basics", "git"],
    )
    generate_interactive_html(be_roadmap, "backend_roadmap.html")
    print("Regenerated structured vertical tree for Backend Developer: backend_roadmap.html")

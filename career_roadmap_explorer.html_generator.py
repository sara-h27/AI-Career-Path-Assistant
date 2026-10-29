"""
Unified Career Roadmap Explorer & Interactive Visualizer
Allows selecting ANY of the 25 roles at ANY level (Junior, Mid, Senior, Full Journey),
rendering a tight, compact, top-to-bottom DAG with exact level colors:
- Junior = Emerald Green (#10B981)
- Mid = Royal Blue (#3B82F6)
- Senior = Purple (#8B5CF6)
- Known = Slate Gray (#94A3B8)
"""

import json
from dag_engine import get_dag_engine


def generate_unified_explorer_html(output_path: str = "career_roadmap_explorer.html") -> str:
    engine = get_dag_engine()
    taxonomy = engine.taxonomy
    roles = engine.roles
    concepts = engine.concepts

    # Prepare complete serializable metadata for browser engine
    roles_meta = {}
    for rid, rdata in sorted(roles.items(), key=lambda x: x[1]["title_fa"]):
        roles_meta[rid] = {
            "role_id": rid,
            "title_fa": rdata["title_fa"],
            "title_en": rdata["title_en"],
            "domain_id": rdata["domain_id"],
            "domain_title_fa": rdata["domain_title_fa"],
            "levels": rdata["levels"]  # {"junior": [...], "mid": [...], "senior": [...]}
        }

    concepts_meta = {}
    for cid, cdata in concepts.items():
        resources = engine.get_resources_for_concept(cid, limit=2)
        concepts_meta[cid] = {
            "concept_id": cid,
            "title_fa": cdata["title_fa"],
            "title_en": cdata["title_en"],
            "level": cdata.get("level", "junior"),
            "prerequisites": cdata.get("prerequisites", []),
            "resources": resources
        }

    html_template = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="UTF-8">
  <title>دستیار مسیر شغلی - کاوشگر گراف یادگیری (Career Roadmap Explorer)</title>
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
      color: #0F172A;
    }}
    #header {{
      height: 64px;
      background: #FFFFFF;
      border-bottom: 1px solid #E2E8F0;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 20px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.04);
      z-index: 20;
    }}
    .title-area {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .title-area h1 {{
      margin: 0;
      font-size: 17px;
      font-weight: 700;
      color: #0F172A;
    }}
    .controls {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    select, button {{
      background: #FFFFFF;
      color: #0F172A;
      border: 1px solid #CBD5E1;
      border-radius: 6px;
      padding: 6px 12px;
      font-size: 13px;
      outline: none;
      cursor: pointer;
    }}
    select:focus {{
      border-color: #3B82F6;
    }}
    .level-btn-group {{
      display: flex;
      border: 1px solid #CBD5E1;
      border-radius: 6px;
      overflow: hidden;
    }}
    .level-btn {{
      border: none;
      border-radius: 0;
      padding: 6px 12px;
      background: #F8FAFC;
      color: #475569;
      font-size: 12px;
      transition: all 0.15s;
    }}
    .level-btn.active {{
      background: #3B82F6;
      color: #FFFFFF;
      font-weight: 600;
    }}
    .legend {{
      display: flex;
      gap: 14px;
      font-size: 12px;
      align-items: center;
    }}
    .legend-item {{
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .pill {{
      width: 14px;
      height: 14px;
      border-radius: 3px;
    }}
    #main-container {{
      width: 100%;
      height: calc(100% - 64px);
      position: relative;
    }}
    #network-container {{
      width: 100%;
      height: 100%;
    }}
    #stats-panel {{
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
    #skill-sidebar {{
      position: absolute;
      top: 16px;
      left: 16px;
      width: 280px;
      max-height: calc(100% - 32px);
      background: rgba(255, 255, 255, 0.95);
      backdrop-filter: blur(8px);
      border: 1px solid #E2E8F0;
      border-radius: 8px;
      padding: 14px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.08);
      z-index: 10;
      overflow-y: auto;
    }}
    #skill-sidebar h3 {{
      margin: 0 0 8px 0;
      font-size: 14px;
      color: #0F172A;
      border-bottom: 1px solid #E2E8F0;
      padding-bottom: 6px;
    }}
    .checkbox-item {{
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 6px;
      font-size: 12px;
      cursor: pointer;
    }}
  </style>
</head>
<body>
  <div id="header">
    <div class="title-area">
      <h1>کاوشگر مسیر شغلی (Career Roadmap Explorer)</h1>
      <div class="legend">
        <div class="legend-item"><span class="pill" style="background:#ECFDF5; border:1px solid #10B981;"></span> پایه (Junior)</div>
        <div class="legend-item"><span class="pill" style="background:#EFF6FF; border:1px solid #3B82F6;"></span> متوسط (Mid)</div>
        <div class="legend-item"><span class="pill" style="background:#FAF5FF; border:1px solid #8B5CF6;"></span> پیشرفته (Senior)</div>
        <div class="legend-item"><span class="pill" style="background:#F1F5F9; border:1px solid #94A3B8;"></span> تسلط دارید</div>
      </div>
    </div>

    <div class="controls">
      <label style="font-size:13px; font-weight:600;">انتخاب شغل:</label>
      <select id="role-select" onchange="onRoleOrLevelChange()">
        {"".join([f'<option value="{r["role_id"]}">{r["title_fa"]} ({r["title_en"]})</option>' for r in sorted(roles.values(), key=lambda x: x["title_fa"])])}
      </select>

      <div class="level-btn-group">
        <button class="level-btn" onclick="setLevel('junior', this)">مقدماتی (Junior)</button>
        <button class="level-btn active" onclick="setLevel('mid', this)">متوسط (Mid)</button>
        <button class="level-btn" onclick="setLevel('senior', this)">پیشرفته (Senior)</button>
        <button class="level-btn" onclick="setLevel('all', this)">کل مسیر (All)</button>
      </div>

      <button onclick="resetKnown()" style="background:#F1F5F9;">پاکسازی تسلط‌ها</button>
    </div>
  </div>

  <div id="main-container">
    <div id="network-container"></div>

    <div id="skill-sidebar">
      <h3>مهارت‌هایی که بلد هستید:</h3>
      <div style="font-size:11px; color:#64748B; margin-bottom:8px;">تیک بزنید تا مهارت از پیش‌نیازها حذف شود:</div>
      <div id="checkboxes-list"></div>
    </div>

    <div id="stats-panel">
      ⬇️ <b>ساختار مرحله‌ای بالا به پایین:</b> مفاهیم ریشه در بالاترین ردیف قرار دارند.
      <br>
      📊 <b>کل مهارت‌های مسیر:</b> <span id="stat-total">0</span> | <b>نیاز به یادگیری:</b> <span id="stat-gaps" style="color:#2563EB; font-weight:bold;">0</span>
    </div>
  </div>

  <script type="text/javascript">
    const ROLES = {json.dumps(roles_meta, ensure_ascii=False)};
    const CONCEPTS = {json.dumps(concepts_meta, ensure_ascii=False)};

    let currentRole = "backend_developer";
    let currentLevel = "mid";
    let userKnownSkills = new Set();
    let network = null;

    // Set default selection
    document.getElementById("role-select").value = currentRole;

    function setLevel(lvl, btn) {{
      currentLevel = lvl;
      document.querySelectorAll(".level-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      renderCurrentRoadmap();
    }}

    function onRoleOrLevelChange() {{
      currentRole = document.getElementById("role-select").value;
      renderCurrentRoadmap();
    }}

    function toggleKnown(cid) {{
      if (userKnownSkills.has(cid)) {{
        userKnownSkills.delete(cid);
      }} else {{
        userKnownSkills.add(cid);
      }}
      renderCurrentRoadmap();
    }}

    function resetKnown() {{
      userKnownSkills.clear();
      renderCurrentRoadmap();
    }}

    // Compute Transitive Closure for selected role and level
    function computeTargetClosure(roleId, targetLevel) {{
      const r = ROLES[roleId];
      if (!r) return new Set();

      const targets = new Set();
      if (targetLevel === "junior") {{
        (r.levels.junior || []).forEach(c => targets.add(c));
      }} else if (targetLevel === "mid") {{
        (r.levels.junior || []).forEach(c => targets.add(c));
        (r.levels.mid || []).forEach(c => targets.add(c));
      }} else if (targetLevel === "senior" || targetLevel === "all") {{
        (r.levels.junior || []).forEach(c => targets.add(c));
        (r.levels.mid || []).forEach(c => targets.add(c));
        (r.levels.senior || []).forEach(c => targets.add(c));
      }}

      // Transitive closure (ancestor prerequisites)
      const closure = new Set(targets);
      let added = true;
      while (added) {{
        added = false;
        closure.forEach(cid => {{
          const cdata = CONCEPTS[cid];
          if (cdata && cdata.prerequisites) {{
            cdata.prerequisites.forEach(p => {{
              if (!closure.has(p)) {{
                closure.add(p);
                added = true;
              }}
            }});
          }}
        }});
      }}
      return closure;
    }}

    // Calculate hierarchical depth from roots (in-degree 0)
    function calculateDepths(subgraphNodes) {{
      const depths = {{}};
      const inNodes = new Set(subgraphNodes);

      // Recursive depth calculator
      function getDepth(cid, visited = new Set()) {{
        if (visited.has(cid)) return 1;
        if (depths[cid]) return depths[cid];

        visited.add(cid);
        const cdata = CONCEPTS[cid];
        const validPrereqs = (cdata.prerequisites || []).filter(p => inNodes.has(p));

        if (validPrereqs.length === 0) {{
          depths[cid] = 1;
        }} else {{
          let maxP = 0;
          validPrereqs.forEach(p => {{
            maxP = Math.max(maxP, getDepth(p, new Set(visited)));
          }});
          depths[cid] = maxP + 1;
        }}
        return depths[cid];
      }}

      inNodes.forEach(cid => getDepth(cid));
      return depths;
    }}

    function renderCurrentRoadmap() {{
      const closure = computeTargetClosure(currentRole, currentLevel);
      const depths = calculateDepths(Array.from(closure));
      const roleData = ROLES[currentRole];

      // Update Sidebar checkboxes
      const cbContainer = document.getElementById("checkboxes-list");
      cbContainer.innerHTML = "";
      Array.from(closure).sort((a,b) => (depths[a]||1) - (depths[b]||1)).forEach(cid => {{
        const cdata = CONCEPTS[cid];
        const isChecked = userKnownSkills.has(cid);
        const div = document.createElement("div");
        div.className = "checkbox-item";
        div.innerHTML = `
          <input type="checkbox" id="cb_${{cid}}" ${{isChecked ? "checked" : ""}} onchange="toggleKnown('${{cid}}')">
          <label for="cb_${{cid}}">${{cdata.title_fa}}</label>
        `;
        cbContainer.appendChild(div);
      }});

      // Stats
      const totalCount = closure.size;
      const knownCount = Array.from(closure).filter(c => userKnownSkills.has(c)).length;
      const gapCount = totalCount - knownCount;
      document.getElementById("stat-total").innerText = totalCount;
      document.getElementById("stat-gaps").innerText = gapCount;

      // Build Vis Nodes
      const visNodes = [];
      closure.forEach(cid => {{
        const cdata = CONCEPTS[cid];
        const isKnown = userKnownSkills.has(cid);
        const tier = depths[cid] || 1;

        // Level determination for this specific role
        let conceptLevel = cdata.level || "junior";
        if (roleData.levels.junior && roleData.levels.junior.includes(cid)) conceptLevel = "junior";
        else if (roleData.levels.mid && roleData.levels.mid.includes(cid)) conceptLevel = "mid";
        else if (roleData.levels.senior && roleData.levels.senior.includes(cid)) conceptLevel = "senior";

        // Styling based strictly on level
        let bgColor, borderColor, fontColor, badgeText;
        if (isKnown) {{
          bgColor = "#F1F5F9";
          borderColor = "#94A3B8";
          fontColor = "#64748B";
          badgeText = "✓ از قبل بلدید";
        }} else if (conceptLevel === "junior") {{
          bgColor = "#ECFDF5";
          borderColor = "#10B981";
          fontColor = "#065F46";
          badgeText = "سطح مقدماتی (Junior)";
        }} else if (conceptLevel === "mid") {{
          bgColor = "#EFF6FF";
          borderColor = "#3B82F6";
          fontColor = "#1E40AF";
          badgeText = "سطح متوسط (Mid)";
        }} else {{
          bgColor = "#FAF5FF";
          borderColor = "#8B5CF6";
          fontColor = "#5B21B6";
          badgeText = "سطح پیشرفته (Senior)";
        }}

        // Tooltip with verified courses
        let resHtml = "";
        if (cdata.resources && cdata.resources.length > 0) {{
          const links = cdata.resources.map(r => `<li><a href="${{r.url}}" target="_blank" style="color:#2563EB;">${{r.title}}</a> (${{r.provider}})</li>`).join("");
          resHtml = `<div style="margin-top:6px;"><b>دوره‌های معتبر:</b><ul style="margin:4px 0; padding-right:16px;">${{links}}</ul></div>`;
        }}

        const tooltip = `
          <div dir="rtl" style="text-align:right; font-family:tahoma,sans-serif; max-width:280px; padding:6px;">
            <div style="font-size:14px; font-weight:bold;">${{cdata.title_fa}}</div>
            <div style="font-size:11px; color:#64748B;">${{cdata.title_en}} | لایه ${{tier}}</div>
            <div style="font-size:12px; margin-top:4px;"><b>سطح:</b> ${{badgeText}}</div>
            ${{resHtml}}
          </div>
        `;

        visNodes.push({{
          id: cid,
          label: `${{cdata.title_fa}}\\n(${{cdata.title_en}})`,
          title: tooltip,
          level: tier, // Top-to-bottom tier (1 = top)
          color: {{
            background: bgColor,
            border: borderColor,
            highlight: {{ background: "#FEF3C7", border: "#D97706" }}
          }},
          font: {{
            color: fontColor,
            face: "Vazirmatn, Tahoma, sans-serif",
            size: 13,
            bold: !isKnown
          }},
          shape: "box",
          margin: {{ top: 10, bottom: 10, left: 14, right: 14 }},
          borderWidth: 2,
          shadow: {{ enabled: true, color: "rgba(0,0,0,0.06)", size: 6, x: 0, y: 3 }}
        }});
      }});

      // Build Vis Edges (uniform vertical lines)
      const visEdges = [];
      closure.forEach(cid => {{
        const cdata = CONCEPTS[cid];
        (cdata.prerequisites || []).forEach(p => {{
          if (closure.has(p)) {{
            visEdges.push({{
              from: p,
              to: cid,
              arrows: {{ to: {{ enabled: true, scaleFactor: 0.8 }} }},
              color: {{ color: "#94A3B8", highlight: "#F59E0B" }},
              width: 2,
              smooth: {{
                type: "cubicBezier",
                forceDirection: "vertical",
                roundness: 0.4
              }}
            }});
          }}
        }});
      }});

      // Render Vis Network
      const container = document.getElementById("network-container");
      const data = {{
        nodes: new vis.DataSet(visNodes),
        edges: new vis.DataSet(visEdges)
      }};

      // Tight, compact layout settings
      const options = {{
        layout: {{
          hierarchical: {{
            enabled: true,
            direction: "UD",       // Strict Top-to-Bottom
            sortMethod: "directed",
            levelSeparation: 110,   // Compact vertical distance
            nodeSpacing: 180,       // Neat horizontal distance
            treeSpacing: 150,
            blockShifting: true,
            edgeMinimization: true,
            parentCentralization: true
          }}
        }},
        physics: {{ enabled: false }},
        interaction: {{
          hover: true,
          tooltipDelay: 80,
          zoomView: true,
          dragView: true
        }}
      }};

      if (network) network.destroy();
      network = new vis.Network(container, data, options);
    }}

    // Initial render
    renderCurrentRoadmap();
  </script>
</body>
</html>
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_template)

    return output_path


if __name__ == "__main__":
    out = generate_unified_explorer_html("career_roadmap_explorer.html")
    print(f"Unified Career Roadmap Explorer created: {out}")

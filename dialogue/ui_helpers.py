import json

def graphviz_dot(graph):
    lines=['digraph Roadmap {','graph [rankdir=TB, bgcolor="transparent", nodesep=0.35, ranksep=0.62, pad=0.2];',
           'node [shape=box, style="rounded,filled", fillcolor="#F7F8FC", color="#6D5BD0", penwidth=1.4, fontcolor="#202235", fontname="sans-serif", margin="0.20,0.13"];',
           'edge [color="#8C86B8", penwidth=1.2, arrowsize=0.7];']
    labels={n.id:n.label for n in graph.nodes}
    for i,cid in enumerate(graph.study_order,1):
        lines.append(f'{json.dumps(cid)} [label={json.dumps(str(i)+". "+labels[cid],ensure_ascii=False)}];')
    for edge in graph.edges:
        lines.append(f'{json.dumps(edge.source)} -> {json.dumps(edge.target)};')
    return '\n'.join(lines+['}'])

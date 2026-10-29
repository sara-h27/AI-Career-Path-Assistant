import json

def graphviz_dot(graph):
    lines=['digraph Roadmap {','graph [rankdir=TB, bgcolor="transparent", nodesep=0.35, ranksep=0.55];',
           'node [shape=box, style="rounded,filled", fillcolor="#123446", color="#2dd4bf", fontcolor="#e6f4f1", fontname="sans-serif", margin="0.16,0.10"];',
           'edge [color="#66b5bc", arrowsize=0.65];']
    labels={n.id:n.label for n in graph.nodes}
    for i,cid in enumerate(graph.study_order,1):
        lines.append(f'{json.dumps(cid)} [label={json.dumps(str(i)+". "+labels[cid],ensure_ascii=False)}];')
    for edge in graph.edges:
        lines.append(f'{json.dumps(edge.source)} -> {json.dumps(edge.target)};')
    return '\n'.join(lines+['}'])

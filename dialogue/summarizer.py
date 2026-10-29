"""A-09: deterministic Persian text over the validated, displayed graph only."""
from .graph import validate_roadmap

class RoadmapSummarizer:
    def __init__(self, taxonomy): self.taxonomy = taxonomy

    def summarize(self, graph, profile, revision):
        graph = validate_roadmap(graph,profile,revision,self.taxonomy)
        if not graph.nodes:
            return 'در گراف فعلی، مفهومی برای یادگیری باقی نمانده است.'
        labels = {n.id:n.label for n in graph.nodes}
        lines = [f'گراف فعلی شامل {len(graph.nodes)} مفهوم برای یادگیری است. ترتیب پیشنهادی:']
        lines += [f'{i}. {labels[cid]}' for i,cid in enumerate(graph.study_order,1)]
        if graph.edges:
            lines += ['پیش‌نیازهای نمایش‌داده‌شده در گراف:']
            lines += [f'• {labels[e.source]} پیش‌نیازِ {labels[e.target]} است.' for e in graph.edges]
        return '\n'.join(lines)

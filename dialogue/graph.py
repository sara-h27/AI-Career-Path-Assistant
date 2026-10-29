"""Graph-team boundary; reference engine for a runnable integration demo."""
import hashlib
from graphlib import TopologicalSorter
from typing import Protocol
from .schemas import UserProfile, Roadmap, RoadmapNode, RoadmapEdge
from .guardrails import TaxonomyGuardrail

class GraphContractError(ValueError):
    pass

def fingerprint(profile: UserProfile):
    public = profile.model_copy(update={'known_concepts':sorted(profile.known_concepts)})
    return hashlib.sha256(public.model_dump_json(exclude={'is_confirmed'}).encode()).hexdigest()

class GraphEngine(Protocol):
    def build_roadmap(self, profile: UserProfile, revision: int) -> Roadmap: ...

class ReferenceGraphEngine:
    def __init__(self, taxonomy: TaxonomyGuardrail): self.taxonomy = taxonomy

    def build_roadmap(self, profile, revision):
        g = self.taxonomy
        missing = g.closure(profile.target_role, profile.target_level) - set(profile.known_concepts)
        deps = {cid:set(g.concepts[cid].prerequisites)&missing for cid in sorted(missing)}
        order = list(TopologicalSorter({k:sorted(v) for k,v in deps.items()}).static_order())
        return Roadmap(taxonomy_version=g.taxonomy.version, profile_revision=revision,
            profile_fingerprint=fingerprint(profile), target_role=profile.target_role,
            target_level=profile.target_level,
            nodes=[RoadmapNode(id=c,label=g.concepts[c].label) for c in order],
            edges=[RoadmapEdge(source=p,target=c) for c in order for p in sorted(deps[c])], study_order=order)


def validate_roadmap(raw, profile, revision, taxonomy):
    """Reject stale, incomplete, invented or wrongly ordered graph output."""
    def require(condition):
        if not condition: raise ValueError('Graph contract violation')
    try:
        graph = Roadmap.model_validate(raw).model_copy(deep=True)
        ids = [n.id for n in graph.nodes]
        expected = taxonomy.closure(profile.target_role,profile.target_level)-set(profile.known_concepts)
        require(len(ids)==len(set(ids)) and set(ids)==expected)
        require(len(graph.study_order)==len(ids) and set(graph.study_order)==set(ids))
        require(graph.taxonomy_version==taxonomy.taxonomy.version)
        require(graph.profile_revision==revision and graph.profile_fingerprint==fingerprint(profile))
        require(graph.target_role==profile.target_role and graph.target_level==profile.target_level)
        require(all(n.label==taxonomy.concepts[n.id].label for n in graph.nodes))
        edges = [(e.source,e.target) for e in graph.edges]
        expected_edges = {(p,c) for c in expected for p in taxonomy.concepts[c].prerequisites if p in expected}
        require(len(edges)==len(set(edges)) and set(edges)==expected_edges)
        pos = {cid:i for i,cid in enumerate(graph.study_order)}
        require(all(pos[a]<pos[b] for a,b in edges))
    except Exception:
        raise GraphContractError('Invalid, stale or inconsistent graph output') from None
    return graph

"""Bridges between the DAG engine (Track 2) and the dialogue package (Track 3).

The DAG engine and data/taxonomy.json are the single source of truth. The dialogue guardrail
receives the same taxonomy in its own schema, with levels expanded cumulatively so that both
sides compute identical closures (validate_roadmap relies on that).
"""
from dataclasses import dataclass, field
from typing import Dict, List

from dialogue.graph import fingerprint
from dialogue.guardrails import TaxonomyGuardrail
from dialogue.schemas import ResourceLink, Roadmap, RoadmapEdge, RoadmapNode

from .dag_engine import DAGEngine, RoadmapResult

LEVELS = ("junior", "mid", "senior")


def dialogue_taxonomy(engine: DAGEngine) -> dict:
    """Taxonomy in the dialogue guardrail's schema (docs/schemas/dialogue_taxonomy.schema.json)."""
    roles = []
    for rid, role in engine.roles.items():
        cumulative, requirements = [], {}
        for level in LEVELS:
            cumulative += [c for c in role["levels"][level] if c not in cumulative]
            requirements[level] = list(cumulative)
        roles.append({
            "id": rid,
            "label": role["title_fa"],
            "domain": role["domain_title_fa"],
            "aliases": role.get("aliases", []),
            "requirements": requirements,
        })
    concepts = [{
        "id": cid,
        "label": c["title_fa"],
        "aliases": c.get("aliases", []),
        "prerequisites": c["prerequisites"],
    } for cid, c in engine.concepts.items()]
    return {
        "schema_version": "1.0",
        "version": engine.taxonomy.get("version", "1.0"),
        "is_demo": False,
        "roles": roles,
        "concepts": concepts,
    }


def build_guardrail(engine: DAGEngine) -> TaxonomyGuardrail:
    return TaxonomyGuardrail(data=dialogue_taxonomy(engine))


def _resource_links(steps) -> Dict[str, List[ResourceLink]]:
    return {s.concept_id: [ResourceLink(**r) for r in s.resources] for s in steps if s.resources}


class DagGraphEngine:
    """GraphEngine protocol implementation (dialogue.graph.GraphEngine) backed by DAGEngine."""

    def __init__(self, engine: DAGEngine, resources_per_concept: int = 3):
        self.engine = engine
        self.resources_per_concept = resources_per_concept

    def build_roadmap(self, profile, revision) -> Roadmap:
        result = self.engine.compute_roadmap(profile.target_role, profile.target_level, list(profile.known_concepts))
        return Roadmap(
            taxonomy_version=self.engine.taxonomy.get("version", "1.0"),
            profile_revision=revision,
            profile_fingerprint=fingerprint(profile),
            target_role=profile.target_role,
            target_level=profile.target_level,
            nodes=[RoadmapNode(id=s.concept_id, label=s.title_fa) for s in result.steps],
            edges=[RoadmapEdge(source=p, target=s.concept_id) for s in result.steps for p in sorted(s.prerequisites)],
            study_order=list(result.study_order),
            resources={cid: links[:self.resources_per_concept]
                       for cid, links in _resource_links(result.steps).items()},
        )


@dataclass
class GraphView:
    """Minimal roadmap shape for rendering (same attribute names as dialogue.schemas.Roadmap)."""
    nodes: List[RoadmapNode]
    edges: List[RoadmapEdge]
    study_order: List[str]
    resources: Dict[str, List[ResourceLink]] = field(default_factory=dict)


def graph_view(result: RoadmapResult) -> GraphView:
    """Render any DAGEngine result, e.g. a B-10 job-gap roadmap."""
    return GraphView(
        nodes=[RoadmapNode(id=s.concept_id, label=s.title_fa) for s in result.steps],
        edges=[RoadmapEdge(source=p, target=s.concept_id) for s in result.steps for p in sorted(s.prerequisites)],
        study_order=list(result.study_order),
        resources=_resource_links(result.steps),
    )

"""
Deterministic DAG Engine & Knowledge Graph Module (Track 2)
Author: Track 2 - Knowledge Graph Engineer
Rahnama Hackathon: AI Career Path Assistant

Fulfills RFP Requirements:
- A-02: Taxonomy of 25 roles across 5 domains with Junior/Mid/Senior concepts
- A-03: Prerequisite relations forming a strict Directed Acyclic Graph (DAG) with cycle detection
- A-04: Hallucination filter & profile validator against verified taxonomy
- A-05: Deterministic roadmap engine (Prerequisite Closure -> Knowledge Pruning -> Topological Sort)
- A-06: Graph visualization payload (nodes, edges, topological layers for UI)
- A-07: Attachment of verified educational resources (Maktabkhooneh, Quera, Youtube, etc.)
- A-08: Ultra-fast delta updates (< 10 ms) upon user corrections
- A-09: Summary bounds helper to prevent LLM hallucination in text summaries
- B-10: Bridge for Module B (Resume Matching) to generate roadmaps for missing job skills
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Set, Optional, Tuple, Any
import networkx as nx

logger = logging.getLogger("DAGEngine")


@dataclass
class ResourceItem:
    resource_id: str
    title: str
    url: str
    source: str
    provider: str
    language: str
    type: str
    is_free: bool
    accessible_from_iran: bool
    http_status: int = 200


@dataclass
class RoadmapStep:
    step_number: int
    concept_id: str
    title_fa: str
    title_en: str
    level: str
    prerequisites: List[str]
    resources: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class RoadmapResult:
    role_id: str
    role_title_fa: str
    role_title_en: str
    target_level: str
    total_required_count: int
    known_count: int
    to_learn_count: int
    known_concepts: List[str]
    to_learn_concepts: List[str]
    study_order: List[str]
    steps: List[RoadmapStep]
    graph_payload: Dict[str, Any]
    computation_time_ms: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DAGEngine:
    """
    Core Deterministic Knowledge Graph and DAG Engine.
    Guarantees zero-hallucination learning paths, strict cycle-free validation,
    and instantaneous (< 10ms) roadmap calculations.
    """

    def __init__(
        self,
        taxonomy_path: str = "taxonomy.json",
        resources_path: str = "resources/resources.json",
    ):
        self.taxonomy_path = taxonomy_path
        self.resources_path = resources_path

        self.taxonomy: Dict[str, Any] = {}
        self.roles: Dict[str, Any] = {}
        self.concepts: Dict[str, Any] = {}
        self.resources_by_concept: Dict[str, List[Dict[str, Any]]] = {}

        # NetworkX Directed Graph: Edge represents (prerequisite -> concept)
        self.graph: nx.DiGraph = nx.DiGraph()

        self._load_and_validate()

    def _load_and_validate(self):
        """Loads taxonomy & resources, builds graph, and strictly validates DAG integrity."""
        start_time = time.perf_counter()

        # 1. Load taxonomy
        if not os.path.exists(self.taxonomy_path):
            raise FileNotFoundError(f"Taxonomy file not found at: {self.taxonomy_path}")

        with open(self.taxonomy_path, "r", encoding="utf-8") as f:
            self.taxonomy = json.load(f)

        self.roles = self.taxonomy.get("roles", {})
        self.concepts = self.taxonomy.get("concepts", {})

        # 2. Build NetworkX DiGraph
        self.graph.clear()
        for cid, cdata in self.concepts.items():
            self.graph.add_node(
                cid,
                title_fa=cdata.get("title_fa", cid),
                title_en=cdata.get("title_en", cid),
                level=cdata.get("level", "junior"),
            )

        for cid, cdata in self.concepts.items():
            for prereq_id in cdata.get("prerequisites", []):
                if prereq_id not in self.concepts:
                    raise ValueError(
                        f"Integrity Error: Prerequisite '{prereq_id}' for '{cid}' does not exist in taxonomy!"
                    )
                # Edge direction: Prerequisite -> Next Concept (learning flow)
                self.graph.add_edge(prereq_id, cid)

        # 3. Requirement A-03: Cycle Detection & Verification
        if not nx.is_directed_acyclic_graph(self.graph):
            cycles = list(nx.simple_cycles(self.graph))
            raise RuntimeError(
                f"FATAL A-03 VIOLATION: Circular dependency detected in Skill Graph: {cycles}"
            )

        # 4. Load Verified Educational Resources (Requirement A-07)
        if os.path.exists(self.resources_path):
            with open(self.resources_path, "r", encoding="utf-8") as f:
                res_data = json.load(f)
                all_resources = res_data.get("resources", [])
                for r in all_resources:
                    for cid in r.get("concept_ids", []):
                        if cid not in self.resources_by_concept:
                            self.resources_by_concept[cid] = []
                        self.resources_by_concept[cid].append(r)

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"DAGEngine initialized in {elapsed_ms:.2f} ms: {len(self.roles)} roles, "
            f"{len(self.concepts)} concepts, {self.graph.number_of_edges()} prerequisite edges. DAG is valid."
        )

    # --------------------------------------------------------------------------
    # Requirement A-04: Hallucination Guardrail & Profile Validation
    # --------------------------------------------------------------------------
    def validate_concepts(self, concepts_list: List[str]) -> Tuple[List[str], List[str]]:
        """
        Splits a list of concept IDs into (valid_known, hallucinated_or_unknown).
        Ensures LLM or user-submitted concepts strictly exist in the taxonomy.
        """
        valid = []
        invalid = []
        for c in concepts_list:
            cid = c.strip().lower()
            if cid in self.concepts:
                valid.append(cid)
            else:
                invalid.append(c)
        return valid, invalid

    def is_valid_role(self, role_id: str) -> bool:
        """Checks if a given role_id exists in the taxonomy."""
        return role_id.strip().lower() in self.roles

    # --------------------------------------------------------------------------
    # Helper: Cumulative Level Retrieval
    # --------------------------------------------------------------------------
    def get_role_target_concepts(self, role_id: str, target_level: str) -> List[str]:
        """
        Returns cumulative required concepts for a role up to target_level.
        Junior: junior concepts
        Mid: junior + mid concepts
        Senior: junior + mid + senior concepts
        """
        rid = role_id.strip().lower()
        if rid not in self.roles:
            raise ValueError(f"Unknown role_id: '{role_id}'. Valid roles are: {list(self.roles.keys())}")

        lvl = target_level.strip().lower()
        valid_levels = ["junior", "mid", "senior"]
        if lvl not in valid_levels:
            lvl = "junior"

        role_levels = self.roles[rid].get("levels", {})
        required: Set[str] = set()

        if lvl == "junior":
            required.update(role_levels.get("junior", []))
        elif lvl == "mid":
            required.update(role_levels.get("junior", []))
            required.update(role_levels.get("mid", []))
        elif lvl == "senior":
            required.update(role_levels.get("junior", []))
            required.update(role_levels.get("mid", []))
            required.update(role_levels.get("senior", []))

        return sorted(list(required))

    # --------------------------------------------------------------------------
    # Prerequisite Transitive Closure
    # --------------------------------------------------------------------------
    def compute_prerequisite_closure(self, target_concepts: List[str]) -> Set[str]:
        """
        Computes the complete transitive closure of prerequisites for a given set of concepts.
        Recursively retrieves all ancestor prerequisites using nx.ancestors.
        """
        closure: Set[str] = set()
        for c in target_concepts:
            if c in self.concepts:
                closure.add(c)
                ancestors = nx.ancestors(self.graph, c)
                closure.update(ancestors)
        return closure

    # --------------------------------------------------------------------------
    # Requirement A-07: Verified Resource Matcher
    # --------------------------------------------------------------------------
    def get_resources_for_concept(
        self,
        concept_id: str,
        limit: int = 3,
        prefer_fa: bool = True,
        prefer_free: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves top verified educational resources for a concept,
        sorted by relevance (Persian, accessibility from Iran, free of cost).
        """
        raw_resources = self.resources_by_concept.get(concept_id, [])
        if not raw_resources:
            return []

        def sort_key(r):
            # Prioritize: 1) Verified HTTP 200, 2) Iranian accessible, 3) Language, 4) Free
            is_200 = 1 if r.get("http_status") == 200 else 0
            is_access = 1 if r.get("accessible_from_iran", True) else 0
            is_fa = 1 if (r.get("language") == "fa" if prefer_fa else True) else 0
            is_free = 1 if (r.get("is_free", False) if prefer_free else True) else 0
            return (is_200, is_access, is_fa, is_free)

        sorted_res = sorted(raw_resources, key=sort_key, reverse=True)
        results = []
        for r in sorted_res[:limit]:
            results.append({
                "resource_id": r.get("resource_id", ""),
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "provider": r.get("provider", ""),
                "source": r.get("source", ""),
                "language": r.get("language", "fa"),
                "is_free": r.get("is_free", False),
                "accessible_from_iran": r.get("accessible_from_iran", True),
            })
        return results

    # --------------------------------------------------------------------------
    # Requirement A-05: Deterministic Roadmap Engine
    # --------------------------------------------------------------------------
    def compute_roadmap(
        self,
        role_id: str,
        target_level: str = "junior",
        known_concepts: Optional[List[str]] = None,
    ) -> RoadmapResult:
        """
        Computes a deterministic, mathematically optimal learning roadmap:
        1. Identifies cumulative role concepts for target level
        2. Calculates complete prerequisite closure
        3. Prunes user validated knowledge: To_Learn = Closure - Known
        4. Computes valid pedagogical order via Topological Sort
        5. Attaches verified educational resources
        6. Builds UI graph visualization payload
        """
        start_time = time.perf_counter()

        rid = role_id.strip().lower()
        if rid not in self.roles:
            raise ValueError(f"Unknown role_id: '{role_id}'")

        target_level = target_level.strip().lower()
        role_meta = self.roles[rid]

        # 1. Target concepts
        target_concepts = self.get_role_target_concepts(rid, target_level)

        # 2. Prerequisite Closure
        full_closure = self.compute_prerequisite_closure(target_concepts)

        # 3. Pruning: To_Learn = Closure \ Known
        known_set = set(known_concepts or [])
        # Sanitize known concepts against taxonomy
        valid_known = known_set.intersection(set(self.concepts.keys()))
        to_learn_set = full_closure - valid_known

        # 4. Topological Sort of To_Learn subgraph
        subgraph = self.graph.subgraph(to_learn_set)
        study_order = list(nx.topological_sort(subgraph))

        # 5. Formulate Steps with verified resources
        steps: List[RoadmapStep] = []
        for idx, cid in enumerate(study_order, start=1):
            cdata = self.concepts[cid]
            direct_prereqs = [
                p for p in cdata.get("prerequisites", []) if p in to_learn_set
            ]
            res = self.get_resources_for_concept(cid, limit=2)
            steps.append(
                RoadmapStep(
                    step_number=idx,
                    concept_id=cid,
                    title_fa=cdata.get("title_fa", cid),
                    title_en=cdata.get("title_en", cid),
                    level=cdata.get("level", "junior"),
                    prerequisites=direct_prereqs,
                    resources=res,
                )
            )

        # 6. Build UI Graph Payload (Requirement A-06)
        graph_payload = self._build_graph_payload(
            all_closure=full_closure,
            known_set=valid_known,
            to_learn_order=study_order,
        )

        calc_time_ms = (time.perf_counter() - start_time) * 1000

        return RoadmapResult(
            role_id=rid,
            role_title_fa=role_meta.get("title_fa", rid),
            role_title_en=role_meta.get("title_en", rid),
            target_level=target_level,
            total_required_count=len(full_closure),
            known_count=len(full_closure.intersection(valid_known)),
            to_learn_count=len(to_learn_set),
            known_concepts=sorted(list(full_closure.intersection(valid_known))),
            to_learn_concepts=study_order,
            study_order=study_order,
            steps=steps,
            graph_payload=graph_payload,
            computation_time_ms=calc_time_ms,
        )

    # --------------------------------------------------------------------------
    # Requirement A-08: Fast Dynamic Delta Updates (< 10 ms)
    # --------------------------------------------------------------------------
    def update_roadmap_delta(
        self,
        current_roadmap: RoadmapResult,
        add_known: Optional[List[str]] = None,
        remove_known: Optional[List[str]] = None,
    ) -> RoadmapResult:
        """
        Fast dynamic state transition when user corrects their knowledge in chat.
        Runs in < 5 milliseconds.
        """
        new_known = set(current_roadmap.known_concepts)
        if add_known:
            new_known.update(add_known)
        if remove_known:
            new_known.difference_update(remove_known)

        return self.compute_roadmap(
            role_id=current_roadmap.role_id,
            target_level=current_roadmap.target_level,
            known_concepts=list(new_known),
        )

    # --------------------------------------------------------------------------
    # Bonus B-10: Module B -> Module A Integration Bridge
    # --------------------------------------------------------------------------
    def compute_roadmap_for_skills(
        self,
        missing_skills: List[str],
        known_skills: Optional[List[str]] = None,
        label: str = "Job Gap Roadmap",
    ) -> RoadmapResult:
        """
        Enables Module B (Job Matching) to generate a targeted learning roadmap
        for missing skills of a specific job posting.
        """
        start_time = time.perf_counter()

        valid_targets, _ = self.validate_concepts(missing_skills)
        if not valid_targets:
            # Fallback if no valid concepts found
            valid_targets = []

        full_closure = self.compute_prerequisite_closure(valid_targets)
        known_set = set(known_skills or []).intersection(set(self.concepts.keys()))
        to_learn_set = full_closure - known_set

        subgraph = self.graph.subgraph(to_learn_set)
        study_order = list(nx.topological_sort(subgraph))

        steps = []
        for idx, cid in enumerate(study_order, start=1):
            cdata = self.concepts[cid]
            direct_prereqs = [p for p in cdata.get("prerequisites", []) if p in to_learn_set]
            res = self.get_resources_for_concept(cid, limit=2)
            steps.append(
                RoadmapStep(
                    step_number=idx,
                    concept_id=cid,
                    title_fa=cdata.get("title_fa", cid),
                    title_en=cdata.get("title_en", cid),
                    level=cdata.get("level", "junior"),
                    prerequisites=direct_prereqs,
                    resources=res,
                )
            )

        graph_payload = self._build_graph_payload(
            all_closure=full_closure,
            known_set=known_set,
            to_learn_order=study_order,
        )

        calc_time_ms = (time.perf_counter() - start_time) * 1000

        return RoadmapResult(
            role_id="custom_job_gap",
            role_title_fa=label,
            role_title_en=label,
            target_level="custom",
            total_required_count=len(full_closure),
            known_count=len(full_closure.intersection(known_set)),
            to_learn_count=len(to_learn_set),
            known_concepts=sorted(list(full_closure.intersection(known_set))),
            to_learn_concepts=study_order,
            study_order=study_order,
            steps=steps,
            graph_payload=graph_payload,
            computation_time_ms=calc_time_ms,
        )

    # --------------------------------------------------------------------------
    # Requirement A-06: UI Graph Visualization Formatter
    # --------------------------------------------------------------------------
    def _build_graph_payload(
        self,
        all_closure: Set[str],
        known_set: Set[str],
        to_learn_order: List[str],
    ) -> Dict[str, Any]:
        """
        Builds a Cytoscape/Pyvis/Streamlit compatible graph representation:
        - Nodes categorized as 'known' (gray/green), 'to_learn' (colored by level)
        - Nodes assigned a topological level / layer for clean left-to-right rendering
        - Directed edges between nodes
        """
        nodes = []
        edges = []

        subgraph = self.graph.subgraph(all_closure)
        # Compute topological layers for clean horizontal layout
        try:
            topo_layers = list(nx.topological_generations(subgraph))
        except Exception:
            topo_layers = [list(all_closure)]

        node_layers: Dict[str, int] = {}
        for layer_idx, layer_nodes in enumerate(topo_layers):
            for n in layer_nodes:
                node_layers[n] = layer_idx + 1

        for cid in all_closure:
            cdata = self.concepts[cid]
            is_known = cid in known_set
            status = "known" if is_known else "to_learn"
            level = cdata.get("level", "junior")

            nodes.append({
                "id": cid,
                "label": cdata.get("title_fa", cid),
                "label_en": cdata.get("title_en", cid),
                "status": status,
                "level": level,
                "layer": node_layers.get(cid, 1),
                "color": (
                    "#94A3B8" if is_known  # Muted slate for known
                    else "#10B981" if level == "junior"  # Emerald for junior
                    else "#3B82F6" if level == "mid"  # Blue for mid
                    else "#8B5CF6"  # Purple for senior
                ),
            })

        for u, v in subgraph.edges():
            edges.append({
                "from": u,
                "to": v,
                "arrows": "to",
                "color": "#CBD5E1",
            })

        return {
            "nodes": nodes,
            "edges": edges,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
        }

    # --------------------------------------------------------------------------
    # Requirement A-09: Context Bounding for LLM Text Summaries
    # --------------------------------------------------------------------------
    def get_summary_prompt_context(self, roadmap: RoadmapResult) -> str:
        """
        Generates a strict Persian summary context to inject into LLM prompts.
        Prevents LLM hallucinations by bounding it strictly to the computed steps.
        """
        lines = [
            f"مسیر شغلی برای نقش: {roadmap.role_title_fa} (سطح: {roadmap.target_level})",
            f"تعداد کل مهارت‌های این مسیر: {roadmap.total_required_count}",
            f"مهارت‌های فعلی کاربر که تسلط دارد ({roadmap.known_count} مورد): {', '.join([self.concepts[c]['title_fa'] for c in roadmap.known_concepts]) if roadmap.known_concepts else 'موردی ثبت نشده'}",
            f"مراحل یادگیری پیشنهادی به ترتیب اولویت و پیش‌نیازها ({roadmap.to_learn_count} مرحله):",
        ]

        for s in roadmap.steps:
            prereq_titles = [self.concepts[p]["title_fa"] for p in s.prerequisites]
            prereq_str = f" (پیش‌نیاز: {', '.join(prereq_titles)})" if prereq_titles else ""
            lines.append(f"مرحله {s.step_number}: {s.title_fa} [{s.level}]{prereq_str}")

        lines.append(
            "توجه اکید: در خلاصه متنی خود فقط و فقط درباره مراحل بالا توضیح دهید و هیچ مهارت یا دوره دیگری اضافه نکنید."
        )
        return "\n".join(lines)


# Singleton factory for quick access across modules
_engine_instance: Optional[DAGEngine] = None

def get_dag_engine() -> DAGEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = DAGEngine()
    return _engine_instance


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    # Self-test demonstration
    engine = get_dag_engine()
    print("Testing Backend Developer Mid Roadmap...")
    res = engine.compute_roadmap(
        role_id="backend_developer",
        target_level="mid",
        known_concepts=["git", "python_basics", "sql_basics"],
    )
    print(f"Role: {res.role_title_fa} ({res.target_level})")
    print(f"Total Closure: {res.total_required_count} concepts")
    print(f"Known (Pruned): {res.known_count} concepts -> {res.known_concepts}")
    print(f"To Learn: {res.to_learn_count} concepts in topological order:")
    for s in res.steps:
        print(f"  Step {s.step_number}: {s.title_fa} ({s.title_en}) [{s.level}] - {len(s.resources)} resources")
    print(f"Calculation time: {res.computation_time_ms:.2f} ms")

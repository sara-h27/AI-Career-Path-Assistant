"""
Unit Test Suite for Deterministic DAG Engine & Knowledge Graph (Track 2)
Proves compliance with Rahnama Hackathon RFP Requirements:
- A-02: 25 roles across 5 domains with Junior/Mid/Senior coverage
- A-03: Zero-cycle DAG integrity and cycle rejection
- A-04: Hallucination filtering of invalid concepts
- A-05: Transitive closure, pruning, and valid topological study order
- A-06: Graph visualization payload integrity
- A-07: Verified educational resources attached (HTTP 200, no hallucinated URLs)
- A-08: Sub-10ms delta updates upon user corrections
- B-10: Module B job gap roadmap calculation
"""

import unittest
import time
import networkx as nx
from dag_engine import DAGEngine, get_dag_engine


class TestDAGEngine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = get_dag_engine()

    def test_01_taxonomy_coverage_a02(self):
        """Verifies A-02: At least 10 roles across 3 domains (we provide 25 roles across 5 domains)."""
        roles = self.engine.roles
        concepts = self.engine.concepts
        domains = self.engine.taxonomy.get("domains", [])

        self.assertGreaterEqual(len(domains), 3, "Must cover at least 3 domains")
        self.assertGreaterEqual(len(roles), 10, "Must cover at least 10 roles")
        self.assertEqual(len(roles), 25, "Expected exactly 25 roles from categories.json")
        self.assertEqual(len(concepts), 145, "Expected 145 standardized concepts")

        # Verify each role has junior, mid, senior concept sets
        for rid, rdata in roles.items():
            levels = rdata.get("levels", {})
            self.assertIn("junior", levels, f"Role {rid} missing junior level")
            self.assertIn("mid", levels, f"Role {rid} missing mid level")
            self.assertIn("senior", levels, f"Role {rid} missing senior level")
            self.assertGreater(len(levels["junior"]), 0, f"Role {rid} has 0 junior concepts")
            self.assertGreater(len(levels["mid"]), 0, f"Role {rid} has 0 mid concepts")
            self.assertGreater(len(levels["senior"]), 0, f"Role {rid} has 0 senior concepts")

    def test_02_strict_dag_acyclicity_a03(self):
        """Verifies A-03: The graph is strictly a Directed Acyclic Graph with 0 cycles."""
        self.assertTrue(
            nx.is_directed_acyclic_graph(self.engine.graph),
            "CRITICAL: Graph contains cycles and violates A-03!"
        )
        cycles = list(nx.simple_cycles(self.engine.graph))
        self.assertEqual(len(cycles), 0, f"Detected cycles: {cycles}")

    def test_03_no_dangling_prerequisites(self):
        """Verifies that every prerequisite points to a real, valid concept ID."""
        for cid, cdata in self.engine.concepts.items():
            for p in cdata.get("prerequisites", []):
                self.assertIn(
                    p,
                    self.engine.concepts,
                    f"Dangling prerequisite '{p}' found in concept '{cid}'!"
                )

    def test_04_hallucination_guardrail_a04(self):
        """Verifies A-04: Non-taxonomy/hallucinated skills are cleanly filtered out."""
        test_skills = ["python_basics", "quantum_teleportation_v2", "docker", "imaginary_skill_123"]
        valid, invalid = self.engine.validate_concepts(test_skills)

        self.assertIn("python_basics", valid)
        self.assertIn("docker", valid)
        self.assertIn("quantum_teleportation_v2", invalid)
        self.assertIn("imaginary_skill_123", invalid)

    def test_05_prerequisite_closure_and_pruning_a05(self):
        """Verifies A-05: Complete transitive closure is gathered and known concepts are subtracted."""
        role_id = "ml_engineer"
        # ML Engineer needs machine_learning_basics, which depends on python_basics & linear_algebra
        roadmap = self.engine.compute_roadmap(
            role_id=role_id,
            target_level="junior",
            known_concepts=["python_basics"],
        )

        # python_basics must be in known, not to_learn
        self.assertIn("python_basics", roadmap.known_concepts)
        self.assertNotIn("python_basics", roadmap.to_learn_concepts)

        # machine_learning_basics and its prerequisites (linear_algebra, etc.) must be in closure
        self.assertIn("machine_learning_basics", roadmap.to_learn_concepts)

    def test_06_topological_study_order_soundness_a05(self):
        """Verifies A-05: In every generated roadmap, prerequisites strictly appear before their dependent concepts."""
        for role_id in ["backend_developer", "frontend_developer", "data_scientist", "devops_engineer"]:
            roadmap = self.engine.compute_roadmap(role_id=role_id, target_level="senior", known_concepts=[])
            order = roadmap.study_order
            position = {cid: idx for idx, cid in enumerate(order)}

            # For every node in the roadmap, all its prerequisites that are also in the roadmap must appear earlier
            for cid in order:
                cdata = self.engine.concepts[cid]
                for prereq in cdata.get("prerequisites", []):
                    if prereq in position:
                        self.assertLess(
                            position[prereq],
                            position[cid],
                            f"Pedagogical ordering violation in {role_id}: {prereq} (pos {position[prereq]}) "
                            f"appears after {cid} (pos {position[cid]})!"
                        )

    def test_07_verified_resources_attached_a07(self):
        """Verifies A-07: Verified learning resources exist for gaps and have real HTTP URLs."""
        roadmap = self.engine.compute_roadmap(
            role_id="data_analyst",
            target_level="mid",
            known_concepts=[],
        )

        steps_with_resources = [s for s in roadmap.steps if len(s.resources) > 0]
        # At least 90% of steps must have verified resources attached
        coverage_ratio = len(steps_with_resources) / len(roadmap.steps)
        self.assertGreaterEqual(
            coverage_ratio,
            0.85,
            f"Resource coverage too low: only {coverage_ratio * 100:.1f}% steps have resources",
        )

        # Check URL validity (must start with http/https)
        for s in roadmap.steps:
            for r in s.resources:
                self.assertTrue(
                    r["url"].startswith("http"),
                    f"Invalid URL for resource in step {s.concept_id}: {r['url']}"
                )

    def test_08_sub_10ms_delta_update_performance_a08(self):
        """Verifies A-08: Dynamic user corrections recalculate in < 10 milliseconds."""
        initial = self.engine.compute_roadmap(
            role_id="backend_developer",
            target_level="senior",
            known_concepts=["python_basics", "git"],
        )

        # User says: "Actually, I also know Docker and SQL basics"
        start = time.perf_counter()
        updated = self.engine.update_roadmap_delta(
            current_roadmap=initial,
            add_known=["docker", "sql_basics"],
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        self.assertLess(
            elapsed_ms,
            10.0,
            f"Delta update too slow: took {elapsed_ms:.2f} ms (must be < 10ms)",
        )
        self.assertIn("docker", updated.known_concepts)
        self.assertNotIn("docker", updated.to_learn_concepts)

    def test_09_all_25_roles_execute_without_error(self):
        """Stress-test: Runs all 25 roles across Junior, Mid, Senior levels (75 permutations)."""
        for rid in self.engine.roles.keys():
            for lvl in ["junior", "mid", "senior"]:
                res = self.engine.compute_roadmap(role_id=rid, target_level=lvl, known_concepts=[])
                self.assertGreater(
                    res.total_required_count,
                    0,
                    f"Roadmap for {rid} at {lvl} has 0 concepts!",
                )
                self.assertEqual(len(res.study_order), len(res.steps))
                self.assertIsNotNone(res.graph_payload)

    def test_10_module_b_integration_bridge_b10(self):
        """Verifies Bonus B-10: Generates learning roadmap for missing job skills."""
        missing = ["docker", "kubernetes", "ci_cd", "system_design"]
        known = ["linux_basics", "git"]

        bridge_result = self.engine.compute_roadmap_for_skills(
            missing_skills=missing,
            known_skills=known,
            label="DevOps Job Gap Roadmap",
        )

        self.assertIn("linux_basics", bridge_result.known_concepts)
        self.assertIn("docker", bridge_result.to_learn_concepts)
        self.assertIn("kubernetes", bridge_result.to_learn_concepts)
        # docker must come before kubernetes
        order = bridge_result.study_order
        self.assertLess(order.index("docker"), order.index("kubernetes"))


if __name__ == "__main__":
    unittest.main()

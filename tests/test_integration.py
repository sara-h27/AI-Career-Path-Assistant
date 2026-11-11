"""End-to-end checks across modules, using the real team taxonomy (RFP Appendix B scenarios)."""
import io
import unittest
from pathlib import Path

from dialogue import ConversationManager, MockLLMClient
from engine import DAGEngine
from engine.adapters import DagGraphEngine, build_guardrail, graph_view
from matching.profile import extract_profile_offline
from matching.ranker import Filters, JobRanker, load_jobs
from matching.resume_parser import parse_resume

ROOT = Path(__file__).resolve().parents[1]
RESUMES = ROOT / "data" / "eval" / "resumes"


class Shared:
    engine = DAGEngine()
    guardrail = build_guardrail(engine)
    ranker = JobRanker(engine, guardrail, load_jobs(guardrail))


def chat(messages):
    m = ConversationManager(MockLLMClient(), Shared.guardrail, DagGraphEngine(Shared.engine))
    m.start_session("s")
    r = None
    for text in messages:
        r = m.handle_user_turn("s", text)
    return m, r


class ModuleATests(unittest.TestCase):
    def test_beginner_data_analyst_hearsay_not_known(self):
        _, r = chat(["می‌خوام تحلیلگر داده بشم", "جونیور", "دانشجوی مهندسی صنایع هستم",
                     "0 سال سابقه دارم و مبتدی هستم", "فقط اسم اکسل و SQL را شنیده‌ام", "تایید می‌کنم"])
        self.assertTrue(r.is_complete)
        self.assertEqual(r.profile_json["known_concepts"], [])
        order = r.roadmap.study_order
        for cid in ("excel_basics", "sql_basics", "statistics_basics", "power_bi"):
            self.assertIn(cid, order)
        self.assertLess(order.index("excel_basics"), order.index("power_bi"))
        self.assertTrue(r.roadmap.resources, "A-07 resources attached")
        self.assertIn(r.summary.splitlines()[1].split(". ", 1)[1], [n.label for n in r.roadmap.nodes])

    def test_junior_backend_to_senior_focuses_on_advanced(self):
        _, r = chat(["بک‌اند", "سنیور", "لیسانس کامپیوتر", "2 سال سابقه دارم و سطح فعلی جونیور",
                     "با پایتون و جنگو و sql و گیت و لینوکس کار کرده‌ام", "تایید می‌کنم"])
        self.assertTrue(r.is_complete)
        order = r.roadmap.study_order
        for known in ("python_basics", "django", "sql_basics", "git"):
            self.assertNotIn(known, order)
        for target in ("caching_redis", "message_queues", "system_design", "distributed_systems"):
            self.assertIn(target, order)

    def test_correction_regenerates_roadmap(self):
        m, r = chat(["تحلیلگر داده", "جونیور", "دانشجو هستم", "0 سال سابقه دارم و مبتدی هستم",
                     "با اکسل کار کرده‌ام", "تایید می‌کنم"])
        self.assertNotIn("excel_basics", r.roadmap.study_order)
        r = m.handle_user_turn("s", "من اکسل بلد نیستم")
        self.assertNotIn("excel_basics", r.profile_json["known_concepts"])
        r = m.confirm_profile("s")
        self.assertIn("excel_basics", r.roadmap.study_order)

    def test_resource_links_come_from_catalogue(self):
        _, r = chat(["تحلیلگر داده", "جونیور", "دانشجو هستم", "0 سال سابقه دارم و مبتدی هستم",
                     "هیچ مهارتی ندارم", "تایید می‌کنم"])
        catalogue = {res["url"] for items in Shared.engine.resources_by_concept.values() for res in items}
        for links in r.roadmap.resources.values():
            for link in links:
                self.assertIn(link.url, catalogue)


class ModuleBTests(unittest.TestCase):
    def profile(self, name):
        text = (RESUMES / name).read_text(encoding="utf-8")
        return text, extract_profile_offline(text, Shared.guardrail, Shared.ranker.cities())

    def test_profile_fields(self):
        _, p = self.profile("r3_accountant.txt")
        self.assertEqual(p.years_of_experience, 3.0)
        self.assertEqual(p.location, "تهران")
        self.assertIn("accountant", p.role_ids)
        self.assertIn("vat", p.concept_ids)
        self.assertTrue(p.education)

    def test_top10_with_scores_links_and_explanations(self):
        text, p = self.profile("r1_data_analyst_junior.txt")
        results = Shared.ranker.rank(p, text)
        self.assertEqual(len(results), 10)
        self.assertEqual([r.score for r in results], sorted((r.score for r in results), reverse=True))
        for r in results:
            self.assertTrue(r.job["url"].startswith("http"))
            self.assertTrue(r.explanation)
            for c in r.matched + r.missing:
                self.assertIn(c, Shared.engine.concepts)
        self.assertIn(results[0].job["role_id"], {"data_analyst", "bi_developer"})

    def test_filters(self):
        text, p = self.profile("r3_accountant.txt")
        for r in Shared.ranker.rank(p, text, Filters(city="تهران", seniority="mid")):
            self.assertEqual(r.job["location"]["city"], "تهران")
            self.assertIn(r.job["seniority"], ("mid", None))

    def test_gap_roadmap_b10(self):
        text, p = self.profile("r2_backend_python.txt")
        top = next(r for r in Shared.ranker.rank(p, text) if r.missing)
        result = Shared.engine.compute_roadmap_for_skills(top.missing, known_skills=list(Shared.ranker.known_closure(p.concept_ids)))
        view = graph_view(result)
        self.assertTrue(set(top.missing) <= set(view.study_order))

    def test_docx_parser_roundtrip(self):
        import docx
        doc = docx.Document()
        doc.add_paragraph("حسابدار با ۳ سال سابقه، مسلط به سپیدار و اکسل")
        buf = io.BytesIO()
        doc.save(buf)
        text = parse_resume(buf.getvalue(), "cv.docx")
        p = extract_profile_offline(text, Shared.guardrail, [])
        self.assertIn("accounting_software", p.concept_ids)
        self.assertEqual(p.years_of_experience, 3.0)


class ApiFlowTests(unittest.TestCase):
    """The HTTP API behind the web UI, in offline mode (no API key)."""

    @classmethod
    def setUpClass(cls):
        import os
        os.environ["OPENAI_API_KEY"] = ""  # force the offline client regardless of .env
        from fastapi.testclient import TestClient
        import server
        server.client = server.MockLLMClient()
        server.manager.llm = server.client
        cls.api = TestClient(server.app)

    def test_quick_replies_to_roadmap(self):
        s = self.api.post("/api/session").json()
        sid = s["session_id"]
        self.assertEqual(s["quick"]["type"], "roles")
        for text in ("تحلیلگر داده", "جونیور", "دانشجوی کارشناسی هستم", "0 سال سابقه دارم و مبتدی هستم"):
            s = self.api.post("/api/chat", json={"session_id": sid, "text": text}).json()
        self.assertEqual(s["quick"]["type"], "skills")
        s = self.api.post("/api/skills", json={"session_id": sid, "skills": ["excel_basics", "sql_basics"]}).json()
        self.assertEqual(s["quick"]["type"], "confirm")
        s = self.api.post("/api/chat", json={"session_id": sid, "text": "بله"}).json()
        self.assertEqual(len(s["roadmap"]["known"]), 2)
        self.assertTrue(all(step["resources"] for step in s["roadmap"]["steps"][:3]))
        restored = self.api.get(f"/api/session/{sid}").json()
        self.assertEqual(len(restored["messages"]), len(s["messages"]), "reload must not add messages")

    def test_resume_prefill_jobs_and_gap(self):
        sid = self.api.post("/api/session").json()["session_id"]
        s = self.api.post("/api/resume", data={"session_id": sid, "sample": "accountant"}).json()
        self.assertEqual(s["profile"]["experience_years"], 3.0)
        self.assertEqual(s["quick"]["suggested"][0]["id"], "accountant")
        self.assertIn("vat", [k["id"] for k in s["profile"]["known"]])
        jobs = self.api.get(f"/api/jobs/{sid}").json()
        self.assertEqual(len(jobs["jobs"]), 10)
        self.assertEqual(jobs["based_on"], "resume")
        job = next(j for j in jobs["jobs"] if j["missing"])
        gap = self.api.get(f"/api/gap/{sid}/{job['id']}").json()
        labels = {step["id"] for step in gap["steps"]}
        self.assertTrue({m["id"] for m in job["missing"]} <= labels)
        self.assertNotIn("html_css", labels, "web skills must not leak into an accounting gap roadmap")

    def test_frontend_served(self):
        page = self.api.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn('dir="rtl"', page.text)
        self.assertEqual(self.api.get("/static/app.js").status_code, 200)


if __name__ == "__main__":
    unittest.main()

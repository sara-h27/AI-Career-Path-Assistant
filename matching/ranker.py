"""B-03..B-09: score every cached posting against a resume profile.

Rankers share one interface so the evaluation (Section 10.2) can compare them:
  - keyword_baseline: token Jaccard between resume text and posting text.
  - hybrid: taxonomy-grounded concept coverage with prerequisite closure, role fit computed from
    the role's required concepts, char n-gram TF-IDF similarity and seniority fit.
  - with a Qdrant index: dense retrieval of the top-K postings (filters applied in Qdrant), then the
    same hybrid re-ranking, with dense similarity averaged into the text feature (dense_in_score,
    on by default; it scored best on the cleaned postings, see eval/results.md).
Matched / missing skills are taxonomy concepts, so a missing set can be sent straight to the
roadmap engine (B-10).
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

import networkx as nx
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from dialogue.mock_client import claims_in_text

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
LEVEL_RANK = {"junior": 0, "mid": 1, "senior": 2}
WEIGHTS = {"coverage": 0.40, "role_fit": 0.25, "text": 0.25, "seniority": 0.10}
# Smoothing so a posting with one tagged concept cannot reach full coverage from a single match.
COVERAGE_PRIOR = 1.5
_TOKEN = re.compile(r"[\w+#.]{2,}")
_STOP = set("""و در به از که با را این برای است یا تا می ها های بر آن یک شود کار شرکت
آشنایی تسلط مسلط آشنا توانایی مهارت سابقه حداقل سال کارشناس استخدام the and of to in for with a an
is on or as be are we you our at by experience knowledge skills years""".split())


def job_text(job: dict) -> str:
    return " ".join([job.get("title") or "", job.get("requirements") or "", job.get("description") or "",
                     " ".join(job.get("skills") or [])])


def load_jobs(guardrail, path: Path = DATA_DIR / "jobs.json") -> List[dict]:
    """Cached postings (B-03) with concepts = taxonomy-alias matches in the text ∪ collector tags that are
    plausible for the posting's role (the collector's tagger is noisy, e.g. web skills on a tax-accounting ad)."""
    jobs = json.loads(path.read_text(encoding="utf-8"))
    role_scope = {rid: guardrail.closure(rid, "senior") for rid in guardrail.roles}
    for job in jobs:
        found = claims_in_text(guardrail, job_text(job))
        scope = role_scope.get(job.get("role_id"), set())
        tagged = [c for c in job.get("concepts", []) if c in guardrail.concepts and (c in found or c in scope)]
        job["concept_ids"] = list(dict.fromkeys(tagged + found))
    return jobs


def candidate_level(years: Optional[float]) -> Optional[str]:
    if years is None:
        return None
    return "junior" if years < 2 else "mid" if years < 5 else "senior"


@dataclass
class RankedJob:
    job: dict
    score: float                      # 0..100
    components: Dict[str, float]
    matched: List[str]                # concept ids the candidate has (directly or via prerequisites)
    missing: List[str]                # concept ids the posting asks for and the candidate lacks
    explanation: str = ""
    method: str = "hybrid"


@dataclass
class Filters:
    city: Optional[str] = None
    seniority: Optional[str] = None   # junior | mid | senior
    remote_only: bool = False

    def accept(self, job: dict) -> bool:
        loc = job.get("location") or {}
        if self.city and loc.get("city") != self.city:
            return False
        if self.seniority and job.get("seniority") not in (self.seniority, None):
            return False
        if self.remote_only and not loc.get("remote"):
            return False
        return True


class JobRanker:
    def __init__(self, engine, guardrail, jobs: List[dict], index=None, retrieve_k: int = 40):
        self.index = index            # matching.retrieval.QdrantJobIndex or None
        self.retrieve_k = retrieve_k
        self.engine = engine
        self.guardrail = guardrail
        self.jobs = jobs
        self._tfidf = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=1)
        self._job_matrix = self._tfidf.fit_transform([self._norm(job_text(j)) for j in jobs])
        self._job_tokens = [self._tokens(job_text(j)) for j in jobs]
        # Concepts each role needs up to mid level, with prerequisites (used for role fit).
        self._role_needs = {
            rid: engine.compute_prerequisite_closure(engine.get_role_target_concepts(rid, "mid"))
            for rid in engine.roles
        }

    # ------------------------------------------------------------------ helpers
    def _norm(self, text: str) -> str:
        return self.guardrail._key(text or "")

    def _tokens(self, text: str) -> Set[str]:
        return {t for t in _TOKEN.findall(self._norm(text)) if t not in _STOP}

    def known_closure(self, concept_ids) -> Set[str]:
        """Knowing a concept implies knowing its prerequisites (Django => Python)."""
        return self.engine.compute_prerequisite_closure(list(concept_ids))

    def role_fit(self, known: Set[str]) -> Dict[str, float]:
        return {rid: len(need & known) / len(need) if need else 0.0 for rid, need in self._role_needs.items()}

    def cities(self) -> List[str]:
        return sorted({(j.get("location") or {}).get("city") for j in self.jobs} - {None})

    def _sort_missing(self, ids) -> List[str]:
        concepts = self.engine.concepts
        return sorted(ids, key=lambda c: (LEVEL_RANK.get(concepts[c].get("level"), 0), c))

    # ------------------------------------------------------------------ rankers
    def keyword_baseline(self, resume_text: str, jobs: Optional[List[dict]] = None, top_k: int = 10) -> List[RankedJob]:
        jobs = self.jobs if jobs is None else jobs
        rt = self._tokens(resume_text)
        out = []
        for job in jobs:
            jt = self._job_tokens[self.jobs.index(job)]
            score = len(rt & jt) / len(rt | jt) if rt | jt else 0.0
            out.append(RankedJob(job=job, score=round(100 * score, 1), components={"jaccard": score},
                                 matched=[], missing=[], method="keyword_baseline"))
        out.sort(key=lambda r: (-r.score, r.job["job_id"]))
        return out[:top_k]

    def rank(self, profile, resume_text: str, filters: Optional[Filters] = None,
             jobs: Optional[List[dict]] = None, top_k: int = 10, use_index: bool = True,
             dense_in_score: bool = True) -> List[RankedJob]:
        subset = jobs is not None
        jobs = self.jobs if jobs is None else jobs
        dense = None
        if self.index is not None and use_index:
            dense = self.index.search(profile, filters, job_ids=[j["job_id"] for j in jobs] if subset else None,
                                      limit=self.retrieve_k if not subset else len(jobs))
            jobs = [j for j in jobs if j["job_id"] in dense]
        elif filters:
            jobs = [j for j in jobs if filters.accept(j)]
        if not jobs:
            return []
        known = self.known_closure(profile.concept_ids)
        fit = self.role_fit(known)
        for rid in profile.role_ids:  # previous titles are strong evidence for the role
            fit[rid] = min(1.0, fit.get(rid, 0.0) + 0.3)
        idx = [self.jobs.index(j) for j in jobs]
        sims = cosine_similarity(self._tfidf.transform([self._norm(resume_text)]), self._job_matrix[idx])[0]
        top_sim = max(float(sims.max()), 1e-9)
        level = candidate_level(profile.years_of_experience)

        out = []
        if dense and dense_in_score:
            # Dense similarity carries meaning; TF-IDF keeps exact stack terms (Python vs .NET). Average both.
            top_dense = max(max(dense.values()), 1e-9)
            sims = [0.5 * max(dense[j["job_id"]], 0.0) / top_dense + 0.5 * float(s) / top_sim for j, s in zip(jobs, sims)]
            top_sim = 1.0
        for job, sim in zip(jobs, sims):
            need = job["concept_ids"]
            matched = [c for c in need if c in known]
            missing = [c for c in need if c not in known]
            coverage = len(matched) / (len(need) + COVERAGE_PRIOR)
            role = fit.get(job.get("role_id"), 0.0)
            seniority = self._seniority_fit(level, job.get("seniority"))
            parts = {"coverage": coverage, "role_fit": role, "text": float(sim) / top_sim, "seniority": seniority}
            score = sum(WEIGHTS[k] * v for k, v in parts.items())
            out.append(RankedJob(job=job, score=round(100 * score, 1), components={k: round(v, 3) for k, v in parts.items()},
                                 matched=matched, missing=self._sort_missing(missing),
                                 method="rag" if dense is not None else "hybrid"))
        out.sort(key=lambda r: (-r.score, r.job["job_id"]))
        top = out[:top_k]
        for r in top:
            r.explanation = self.explain(r)
        return top

    @staticmethod
    def _seniority_fit(candidate: Optional[str], job_level: Optional[str]) -> float:
        if candidate is None or job_level not in LEVEL_RANK:
            return 0.6
        gap = LEVEL_RANK[job_level] - LEVEL_RANK[candidate]
        return 1.0 if gap == 0 else 0.7 if gap == -1 else 0.4 if gap == 1 else 0.0

    def explain(self, r: RankedJob) -> str:
        """Deterministic Persian explanation built only from the computed components (no LLM)."""
        c = self.engine.concepts
        role = self.engine.roles.get(r.job.get("role_id"), {}).get("title_fa", "")
        need = len(r.matched) + len(r.missing)
        parts = []
        if need:
            parts.append(f"{len(r.matched)} مورد از {need} مهارت خواسته‌شده در این آگهی را داری")
        else:
            parts.append("آگهی مهارت مشخصی ذکر نکرده است")
        if role:
            parts.append(f"هم‌خوانی پروفایلت با نقش «{role}» {round(100 * r.components['role_fit'])}٪ است")
        if r.missing:
            parts.append("برای این موقعیت باید " + "، ".join(c[m]["title_fa"] for m in r.missing[:4]) + " را تقویت کنی")
        return "؛ ".join(parts) + "."

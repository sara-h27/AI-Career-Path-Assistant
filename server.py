"""مسیر — HTTP API + static frontend for the AI Career Path Assistant.

Run:  python -m uvicorn server:app --port 8000      (or run.cmd / run.sh / docker compose up)

One workspace session holds the dialogue profile (Module A) and, optionally, a parsed resume
(Module B). A resume pre-fills the dialogue profile; the roadmap and the job list are both computed
from that single profile. Resumes and messages live only in memory and are never logged (NF-03).
"""
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=False)

from dialogue import ConversationManager, LLMClient, LLMSettings, MockLLMClient  # noqa: E402
from dialogue.prompts import LEVEL_LABELS, WARNING_TEXT  # noqa: E402
from dialogue.schemas import DialogueState  # noqa: E402
from engine import DAGEngine  # noqa: E402
from engine.adapters import DagGraphEngine, build_guardrail, graph_view  # noqa: E402
from matching.profile import ResumeProfile, extract_profile_llm, extract_profile_offline  # noqa: E402
from matching.ranker import Filters, JobRanker, load_jobs  # noqa: E402
from matching.resume_parser import parse_resume  # noqa: E402

MAX_UPLOAD = 2_000_000
SAMPLES = {
    "data_analyst": ("تحلیلگر دادهٔ تازه‌کار", "r1_data_analyst_junior.txt"),
    "backend": ("برنامه‌نویس بک‌اند پایتون", "r2_backend_python.txt"),
    "accountant": ("حسابدار با ۳ سال سابقه", "r3_accountant.txt"),
}
DEGREE_FA = {"PhD": "دکتری", "MSc": "کارشناسی ارشد", "BSc": "کارشناسی", "Associate": "کاردانی", "Diploma": "دیپلم"}

# ---------------------------------------------------------------- shared components
engine = DAGEngine()
guardrail = build_guardrail(engine)
jobs = load_jobs(guardrail)
try:
    from matching.retrieval import QdrantJobIndex
    index = QdrantJobIndex(jobs, engine.concepts, engine.roles)
except Exception:  # embeddings/Qdrant unavailable: hybrid ranking over all postings
    index = None
ranker = JobRanker(engine, guardrail, jobs, index=index)


def make_client():
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        return MockLLMClient()
    try:
        def price(name):
            value = os.getenv(name, "").strip()
            return float(value) if value else None
        return LLMClient(LLMSettings(
            api_key=key, base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), protocol=os.getenv("LLM_PROTOCOL", "openai"),
            response_format=os.getenv("LLM_RESPONSE_FORMAT", "json_object"),
            max_session_tokens=int(os.getenv("MAX_SESSION_TOKENS", "60000")), timeout_seconds=15,
            input_usd_per_million=price("INPUT_USD_PER_MILLION"), output_usd_per_million=price("OUTPUT_USD_PER_MILLION")))
    except Exception:
        return MockLLMClient()


client = make_client()
manager = ConversationManager(client, guardrail, DagGraphEngine(engine), max_sessions=500)


class Workspace:
    def __init__(self):
        self.resume_text: Optional[str] = None
        self.resume: Optional[ResumeProfile] = None
        self.touched = time.monotonic()


_workspaces: "OrderedDict[str, Workspace]" = OrderedDict()
_lock = threading.Lock()


def workspace(sid: str, create: bool = False) -> Workspace:
    with _lock:
        now = time.monotonic()
        for key in [k for k, w in _workspaces.items() if now - w.touched > 7200]:
            _workspaces.pop(key, None)
            manager.reset_session(key)
        if sid not in _workspaces:
            if not create:
                raise HTTPException(404, "session expired")
            if len(_workspaces) >= 500:
                old, _ = _workspaces.popitem(last=False)
                manager.reset_session(old)
            _workspaces[sid] = Workspace()
        ws = _workspaces[sid]
        ws.touched = now
        _workspaces.move_to_end(sid)
        return ws


# ---------------------------------------------------------------- view models
def concept_view(cid):
    c = engine.concepts[cid]
    return {"id": cid, "label": c["title_fa"], "level": c.get("level", "junior")}


def role_view(rid):
    r = engine.roles[rid]
    return {"id": rid, "label": r["title_fa"], "domain": r["domain_title_fa"]}


def roadmap_view(graph, known: List[str] = (), total: Optional[int] = None):
    labels = {n.id: n.label for n in graph.nodes}
    after = {}
    for e in graph.edges:
        after.setdefault(e.target, []).append(e.source)
    steps = []
    for cid in graph.study_order:
        steps.append({**concept_view(cid), "after": after.get(cid, []),
                      "resources": [r.model_dump() for r in graph.resources.get(cid, [])[:3]]})
    return {"steps": steps, "edges": [[e.source, e.target] for e in graph.edges],
            "known": [concept_view(c) for c in known], "total": total if total is not None else len(steps),
            "labels": labels}


def suggested_roles(concepts, held_roles=()) -> List[dict]:
    if not concepts:
        return []
    fit = ranker.role_fit(ranker.known_closure(concepts))
    for rid in held_roles:  # a role already held in the resume is strong evidence
        if rid in fit:
            fit[rid] = min(1.0, fit[rid] + 0.3)
    best = sorted(fit.items(), key=lambda kv: -kv[1])[:3]
    return [{**role_view(rid), "fit": round(100 * v)} for rid, v in best if v > 0]


def quick_view(sid, latest, ws):
    session = manager.get_or_create_session(sid)
    p = session.slots
    state = latest.current_state
    if latest.roadmap is not None:
        return None
    if state == DialogueState.ROLE:
        known = p.known_concepts or (ws.resume.concept_ids if ws.resume else [])
        return {"type": "roles", "suggested": suggested_roles(known, ws.resume.role_ids if ws.resume else ()),
                "roles": [role_view(r) for r in engine.roles]}
    if state == DialogueState.TARGET_SENIORITY:
        return {"type": "choices", "options": ["جونیور", "میدلول", "سنیور"]}
    if state == DialogueState.EDUCATION:
        return {"type": "choices", "options": ["دانشجوی کارشناسی هستم", "کارشناسی دارم", "کارشناسی ارشد دارم", "دیپلم دارم"]}
    if state == DialogueState.EXPERIENCE_AND_CURRENT_LEVEL:
        return {"type": "choices", "options": ["0 سال سابقه دارم و مبتدی هستم", "1 سال سابقه دارم و جونیور هستم",
                                               "3 سال سابقه دارم و میدلول هستم", "6 سال سابقه دارم و سنیور هستم"]}
    if state == DialogueState.TOOLS_SKILLS:
        pool = guardrail.closure(p.target_role, "senior") if p.target_role in guardrail.roles else set(engine.concepts)
        return {"type": "skills", "skills": sorted((concept_view(c) for c in pool), key=lambda c: c["label"])}
    if state == DialogueState.CONFIRMATION and not p.is_confirmed:
        return {"type": "confirm"}
    return None


def state_view(sid, latest):
    ws = workspace(sid)
    session = manager.get_or_create_session(sid)
    p = session.slots
    roadmap = None
    if latest.roadmap is not None:
        closure = guardrail.closure(latest.roadmap.target_role, latest.roadmap.target_level)
        known = sorted(set(p.known_concepts) & closure)
        roadmap = {**roadmap_view(latest.roadmap, known, len(closure)),
                   "role": role_view(latest.roadmap.target_role), "level": latest.roadmap.target_level,
                   "summary": latest.summary}
    resume = None
    if ws.resume is not None:
        r = ws.resume
        resume = {"years": r.years_of_experience, "location": r.location, "previous_roles": r.previous_roles,
                  "education": [DEGREE_FA.get(e.degree, e.degree or e.field or "") for e in r.education],
                  "skills": [concept_view(c) for c in r.concept_ids]}
    u = session.usage
    return {
        "session_id": sid,
        "messages": [{"role": m["role"], "text": m["content"]} for m in session.history],
        "status": latest.status,
        "question": min(session.question_count, 6),
        "max_questions": 6,
        "quick": quick_view(sid, latest, ws),
        "warnings": [WARNING_TEXT[c] for c in latest.warnings if c in WARNING_TEXT and c not in ("usage_missing", "confirmation_required")],
        "profile": {
            "target_role": role_view(p.target_role) if p.target_role in engine.roles else None,
            "target_level": p.target_level, "current_level": p.current_level,
            "education": p.education, "experience_years": p.experience_years,
            "known": [concept_view(c) for c in p.known_concepts], "confirmed": p.is_confirmed,
        },
        "roadmap": roadmap,
        "resume": resume,
        "has_jobs": bool(ws.resume or p.known_concepts or p.target_role),
        "usage": {"calls": u.api_calls, "failed": u.failed_calls, "prompt_tokens": u.prompt_tokens,
                  "completion_tokens": u.completion_tokens, "cost_usd": u.estimated_cost_usd,
                  "latency_ms": u.last_latency_ms},
    }


# ---------------------------------------------------------------- API
app = FastAPI(title="Masir — AI Career Path Assistant", docs_url="/api/docs", openapi_url="/api/openapi.json")


class ChatIn(BaseModel):
    session_id: str
    text: str


class SkillsIn(BaseModel):
    session_id: str
    skills: List[str] = []


class ProfileIn(BaseModel):
    session_id: str
    target_role: str
    target_level: str
    current_level: str
    education: str
    experience_years: float
    known_concepts: List[str] = []


@app.get("/api/meta")
def meta():
    return {
        "mode": "api" if isinstance(client, LLMClient) else "offline",
        "model": os.getenv("OPENAI_MODEL", "") if isinstance(client, LLMClient) else None,
        "retrieval": index.backend if index else None,
        "counts": {"roles": len(engine.roles), "concepts": len(engine.concepts), "jobs": len(jobs),
                   "resources": sum(len(v) for v in engine.resources_by_concept.values())},
        "roles": [role_view(r) for r in engine.roles],
        "concepts": sorted((concept_view(c) for c in engine.concepts), key=lambda c: c["label"]),
        "levels": {k: v for k, v in LEVEL_LABELS.items()},
        "cities": ranker.cities(),
        "samples": [{"id": k, "label": v[0]} for k, v in SAMPLES.items()],
    }


@app.post("/api/session")
def new_session():
    sid = str(uuid4())
    workspace(sid, create=True)
    return state_view(sid, manager.start_session(sid))


@app.get("/api/session/{sid}")
def get_session(sid: str):
    """Restore after a page reload without adding messages."""
    workspace(sid)
    session = manager.get_or_create_session(sid)
    if not session.history:
        return state_view(sid, manager.start_session(sid))
    return state_view(sid, manager._response(session, ""))


@app.post("/api/chat")
def chat(body: ChatIn):
    workspace(body.session_id)
    return state_view(body.session_id, manager.handle_user_turn(body.session_id, body.text))


@app.post("/api/skills")
def skills(body: SkillsIn):
    """Skill picker: compose one message the evidence checks can verify (A-04)."""
    workspace(body.session_id)
    names = [guardrail.concepts[c].label.replace("،", " ").replace(",", " ") for c in body.skills if c in guardrail.concepts]
    text = ("با " + " و ".join(names) + " کار کرده‌ام") if names else "هیچ مهارتی ندارم"
    return state_view(body.session_id, manager.handle_user_turn(body.session_id, text))


@app.post("/api/profile")
def profile(body: ProfileIn):
    workspace(body.session_id)
    data = body.model_dump(exclude={"session_id"})
    latest = manager.apply_profile_update(body.session_id, {**data, "skills_assessed": True})
    if latest.status != "error":
        latest = manager.confirm_profile(body.session_id)
    return state_view(body.session_id, latest)


@app.post("/api/reset/{sid}")
def reset(sid: str):
    with _lock:
        _workspaces.pop(sid, None)
    manager.reset_session(sid)
    return new_session()


@app.post("/api/resume")
async def resume(session_id: str = Form(...), file: Optional[UploadFile] = File(None), sample: Optional[str] = Form(None)):
    ws = workspace(session_id)
    if sample:
        if sample not in SAMPLES:
            raise HTTPException(400, "unknown sample")
        text, name = (ROOT / "data" / "eval" / "resumes" / SAMPLES[sample][1]).read_text(encoding="utf-8"), SAMPLES[sample][0]
    elif file is not None:
        data = await file.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "حجم فایل باید کمتر از ۲ مگابایت باشد.")
        try:
            text = parse_resume(data, file.filename or "")
        except Exception:
            raise HTTPException(422, "این فایل خوانده نشد. یک PDF متنی (نه اسکن‌شده) یا فایل Word بفرست.")
        name = file.filename or "resume"
        del data
    else:
        raise HTTPException(400, "file or sample required")
    if not text.strip():
        raise HTTPException(422, "متنی در این فایل پیدا نشد. اگر اسکن است، نسخهٔ متنی آن را بفرست.")
    session = manager.get_or_create_session(session_id)
    if isinstance(client, LLMClient):
        prof, usage, _ = extract_profile_llm(text, guardrail, ranker.cities(), client, session.usage.budget_tokens)
        manager._accumulate(session, usage)
    else:
        prof = extract_profile_offline(text, guardrail, ranker.cities())
    ws.resume_text, ws.resume = text, prof
    session.history.append({"role": "user", "content": f"📎 {name}"})
    parts = []
    if prof.years_of_experience is not None:
        parts.append(f"{prof.years_of_experience:g} سال سابقه")
    if prof.education:
        parts.append(DEGREE_FA.get(prof.education[0].degree, prof.education[0].degree or prof.education[0].field or ""))
    if prof.concept_ids:
        parts.append(f"{len(prof.concept_ids)} مهارت")
    note = ("رزومه‌ات را خواندم: " + "، ".join(p for p in parts if p) + ". این‌ها را به پروفایلت اضافه کردم."
            if parts else "رزومه را خواندم ولی مهارت مشخصی از فهرست مهارت‌ها در آن پیدا نکردم.")
    note = note.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    education = None
    if prof.education:  # the model may return "B.Sc." etc., so fall back to its own wording
        e = prof.education[0]
        education = " ".join(filter(None, [DEGREE_FA.get(e.degree, e.degree), e.field])) or None
    latest = manager.prefill_from_resume(session_id, prof.concept_ids, prof.years_of_experience, education, note)
    return state_view(session_id, latest)


def ranking_profile(sid: str, ws: Workspace):
    """The resume profile if there is one, else a profile built from the conversation."""
    p = manager.get_or_create_session(sid).slots
    if ws.resume is not None:
        prof = ws.resume.model_copy(update={"concept_ids": sorted(set(ws.resume.concept_ids) | set(p.known_concepts))})
        if p.target_role and p.target_role not in prof.role_ids:
            prof.role_ids = [p.target_role] + prof.role_ids
        return prof, ws.resume_text or ""
    prof = ResumeProfile(concept_ids=list(p.known_concepts), years_of_experience=p.experience_years,
                         role_ids=[p.target_role] if p.target_role else [])
    text = " ".join([engine.roles[p.target_role]["title_fa"] if p.target_role else ""]
                    + [guardrail.concepts[c].label for c in p.known_concepts])
    return prof, text


@app.get("/api/jobs/{sid}")
def job_list(sid: str, city: Optional[str] = None, seniority: Optional[str] = None, remote: bool = False):
    ws = workspace(sid)
    prof, text = ranking_profile(sid, ws)
    results = ranker.rank(prof, text, Filters(city=city or None, seniority=seniority or None, remote_only=remote))
    out = []
    for r in results:
        job = r.job
        loc = job.get("location") or {}
        out.append({
            "id": job["job_id"], "title": job["title"], "company": job.get("company"), "city": loc.get("city"),
            "remote": bool(loc.get("remote")), "seniority": job.get("seniority"), "url": job["url"],
            "source": job.get("source"), "score": round(r.score), "explanation": r.explanation,
            "components": r.components,
            "matched": [concept_view(c) for c in r.matched], "missing": [concept_view(c) for c in r.missing],
        })
    return {"jobs": out, "total": len(jobs), "based_on": "resume" if ws.resume else "profile"}


@app.get("/api/gap/{sid}/{job_id:path}")
def gap(sid: str, job_id: str):
    ws = workspace(sid)
    job = next((j for j in jobs if j["job_id"] == job_id), None)
    if job is None:
        raise HTTPException(404, "job not found")
    prof, _ = ranking_profile(sid, ws)
    known = ranker.known_closure(prof.concept_ids)
    missing = [c for c in job["concept_ids"] if c not in known]
    view = graph_view(engine.compute_roadmap_for_skills(missing, known_skills=list(known), label=job["title"]))
    return {"title": job["title"], **roadmap_view(view)}


# ---------------------------------------------------------------- frontend
STATIC = ROOT / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index_page():
    return FileResponse(STATIC / "index.html")

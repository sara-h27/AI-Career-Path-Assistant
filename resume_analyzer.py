"""
Resume Analyzer via Metis API (Gemini 3.1 Flash Lite)
=====================================================

Pipeline:
    1. Read resume.txt (plain text from the parser step)
    2. LLM suggests K job titles + extracts skills present in the resume
    3. Load coverage.json  ->  { concept_id: {total, fa_accessible, free} }
    4. matched_skills  = resume skills that map to an existing concept_id
       missing_skills  = one batched LLM call, restricted to concepts that
                         exist in coverage.json with total > 0
    5. Validate final output with Pydantic, print structured JSON

coverage.json expected shape (list of dicts):
    [
      {"concept_id": "growth_marketing", "total": 3, "fa_accessible": 0, "free": 2},
      ...
    ]
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, List

from google import genai
from google.genai.types import HttpOptions
from pydantic import BaseModel, Field, ValidationError


# =============================================================================
# 0. CONFIG
# =============================================================================

RESOURCES_DIR    = Path("/Users/javad/Downloads/Hackathon/resources")
COVERAGE_PATH    = RESOURCES_DIR / "coverage.json"

METIS_BASE_URL   = "https://api.metisai.ir"
MODEL_NAME       = "gemini-3.1-flash-lite"

K_TITLES         = 5
MAX_RESUME_CHARS = 8000
MAX_MISSING      = 8          # per job title
CALL_TIMEOUT_S   = 60


# =============================================================================
# 1. PYDANTIC MODELS
# =============================================================================

class JobSkillAnalysis(BaseModel):
    job_title:      str       = Field(..., description="Suggested job title (English)")
    matched_skills: List[str] = Field(default_factory=list,
                                      description="Skills present in resume AND backed by coverage")
    missing_skills: List[str] = Field(default_factory=list,
                                      description="Skills to learn (concept_ids that exist in coverage.json)")


class ResumeAnalysisResult(BaseModel):
    suggested_titles:   List[JobSkillAnalysis] = Field(..., description="Up to K titles with skill analysis")
    all_skills_present: List[str]              = Field(default_factory=list,
                                                       description="All skills detected in the resume")


class LLMTitlesAndSkills(BaseModel):
    """What we ask the LLM for in the first call."""
    suggested_titles:   List[str] = Field(..., description="Up to K job titles")
    all_skills_present: List[str] = Field(default_factory=list,
                                          description="All skills detected in the resume")


# =============================================================================
# 2. COVERAGE LOADER
# =============================================================================

def load_coverage(path: Path) -> Dict[str, dict]:
    """
    Load coverage.json -> { "<concept_id lowercased>": {total, fa_accessible, free} }
    Accepts:
      - list of {concept_id, total, fa_accessible, free}
      - {"coverage": [...]}  (wrapped)
    """
    if not path.exists():
        raise FileNotFoundError(f"coverage.json not found at {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(raw, list):
        entries = raw
    elif isinstance(raw, dict) and isinstance(raw.get("coverage"), list):
        entries = raw["coverage"]
    else:
        raise ValueError(
            f"coverage.json must be a list of concept entries (got {type(raw).__name__})."
        )

    coverage: Dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        cid = entry.get("concept_id")
        if not isinstance(cid, str) or not cid.strip():
            continue
        coverage[cid.strip().lower()] = {
            "total":         int(entry.get("total", 0) or 0),
            "fa_accessible": int(entry.get("fa_accessible", 0) or 0),
            "free":          int(entry.get("free", 0) or 0),
        }

    if not coverage:
        raise ValueError("coverage.json contained no valid concept entries.")
    return coverage


# =============================================================================
# 3. CONCEPT / SKILL MATCHING
# =============================================================================

def _norm(s: str) -> str:
    """Normalize free text for matching (lowercase, strip punct, unify separators)."""
    s = s.strip().lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[_\-/]+", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _match_concept(skill: str, coverage: Dict[str, dict]) -> str | None:
    """
    Return the coverage concept key that best matches a free-text skill,
    or None. Uses exact-normalized match first, then substring.
    """
    n = _norm(skill)
    if not n:
        return None
    if n in coverage:
        return n
    for key in coverage:
        if n in key or key in n:
            return key
    return None


# =============================================================================
# 4. METIS / GEMINI CLIENT
# =============================================================================

def _get_client() -> genai.Client:
    api_key = os.environ.get("METIS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "METIS_API_KEY environment variable is not set.\n"
            "Get a key from your Metis dashboard."
        )
    return genai.Client(
        api_key=api_key,
        http_options=HttpOptions(base_url=METIS_BASE_URL),
    )


def _extract_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].lstrip()
        raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise


# =============================================================================
# 5. CALL 1: TITLES + RESUME SKILLS
# =============================================================================

SYSTEM_INSTRUCTION = (
    "You are a career advisor specialized in technical resumes. "
    "You may receive resumes in English or Persian. "
    "You MUST return STRICT JSON only — no prose, no markdown fences."
)

TITLES_PROMPT_TEMPLATE = """Analyze the following resume and return JSON with this EXACT schema:

{{
  "suggested_titles":   [ "<English job title 1>", ... up to {k} ],
  "all_skills_present": [ "<skill present in the resume>", ... ]
}}

Rules:
- The resume may be in Persian. Read it fully, then output titles and skills
  in ENGLISH (Latin script). Technical skill names must stay in their standard
  Latin form (e.g. "Python", "Docker", "Kubernetes", "React", "SQL").
- suggested_titles: at most {k} real industry job titles, best fit first.
  Use standard English market titles ("Data Scientist", "Backend Engineer",
  "MLOps Engineer", "Product Manager", ...). Do NOT translate to Persian.
- all_skills_present: every concrete skill, tool, language, framework, or
  methodology the candidate demonstrably has, deduplicated. Only what is
  actually in the resume. No wishlist items.
- Return ONLY the JSON object. No commentary before or after.

RESUME:
---
{resume_text}
---
"""


def call_titles_and_skills(resume_text: str, k: int = K_TITLES) -> LLMTitlesAndSkills:
    client = _get_client()
    prompt = TITLES_PROMPT_TEMPLATE.format(
        k=k,
        resume_text=resume_text[:MAX_RESUME_CHARS],
    )
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config={
            "system_instruction": SYSTEM_INSTRUCTION,
            "temperature": 0.2,
            "max_output_tokens": 1024,
            "response_mime_type": "application/json",
        },
    )
    raw = (response.text or "").strip()
    return LLMTitlesAndSkills.model_validate(_extract_json(raw))


# =============================================================================
# 6. CALL 2: RELEVANT MISSING CONCEPTS PER TITLE
# =============================================================================

MISSING_PROMPT_TEMPLATE = """You are helping a candidate learn the skills most needed for
each target job title. You may only pick from a FIXED list of concept IDs.

JOB TITLES:
{titles_json}

RESUME SKILLS (things the candidate already has):
{skills_json}

AVAILABLE CONCEPTS (the ONLY valid values you may return):
{concepts_json}

Return JSON in this exact shape:
{{
  "<job title>": ["<concept_id>", "<concept_id>", ...],
  ...
}}

Rules:
- Keys must be exactly the job titles listed above.
- Values must be concept IDs copied verbatim from AVAILABLE CONCEPTS.
  Do NOT invent, translate, or paraphrase concept IDs.
- For each title, return at most {max_missing} concept IDs, best first.
- Skip concepts the resume already covers.
- If no concept fits a title, return an empty list for it.
- Return ONLY the JSON object. No commentary.
"""


def call_missing_concepts(
    titles: List[str],
    resume_skills: List[str],
    candidate_concepts: List[str],
) -> Dict[str, List[str]]:
    client = _get_client()
    prompt = MISSING_PROMPT_TEMPLATE.format(
        titles_json=json.dumps(titles, ensure_ascii=False),
        skills_json=json.dumps(resume_skills, ensure_ascii=False),
        concepts_json=json.dumps(candidate_concepts, ensure_ascii=False),
        max_missing=MAX_MISSING,
    )
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config={
            "system_instruction": SYSTEM_INSTRUCTION,
            "temperature": 0.2,
            "max_output_tokens": 1536,
            "response_mime_type": "application/json",
        },
    )
    raw = (response.text or "").strip()
    data = _extract_json(raw)
    if not isinstance(data, dict):
        return {}

    # Sanitize: only allow keys that are real titles, only concepts that exist.
    valid_concepts = set(candidate_concepts)
    out: Dict[str, List[str]] = {}
    for title in titles:
        picked = data.get(title, [])
        if not isinstance(picked, list):
            picked = []
        cleaned = [c for c in picked if isinstance(c, str) and c in valid_concepts]
        # dedupe, preserve order
        seen = set()
        uniq = []
        for c in cleaned:
            if c not in seen:
                seen.add(c)
                uniq.append(c)
        out[title] = uniq[:MAX_MISSING]
    return out


# =============================================================================
# 7. FULL PIPELINE
# =============================================================================

def load_resume(path: str | Path) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Resume file not found: {p}")
    text = p.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Resume file is empty: {p}")
    return text


def analyze_resume_file(
    resume_path: str | Path,
    k: int = K_TITLES,
    coverage_path: Path = COVERAGE_PATH,
) -> ResumeAnalysisResult:
    # 1. Resume text
    resume_text = load_resume(resume_path)

    # 2. Titles + resume skills (LLM call #1)
    llm = call_titles_and_skills(resume_text, k=k)
    titles = llm.suggested_titles[:k]

    # 3. Coverage
    coverage = load_coverage(coverage_path)

    # 4. matched_skills (deterministic)
    matched_by_title: Dict[str, List[str]] = {}
    for title in titles:
        matched: List[str] = []
        seen = set()
        for skill in llm.all_skills_present:
            key = _match_concept(skill, coverage)
            if key and key not in seen:
                seen.add(key)
                matched.append(key)
        matched_by_title[title] = matched

    # 5. candidate concepts for the "learn next" step
    already_matched = {c for m in matched_by_title.values() for c in m}
    candidate_concepts = sorted(
        cid for cid, meta in coverage.items()
        if meta["total"] > 0 and cid not in already_matched
    )

    # 6. missing_skills (LLM call #2, restricted to candidate_concepts)
    missing_by_title = call_missing_concepts(
        titles=titles,
        resume_skills=llm.all_skills_present,
        candidate_concepts=candidate_concepts,
    )

    # 7. Build final validated output
    analyses: List[JobSkillAnalysis] = []
    for title in titles:
        # missing_skills must be a subset of candidate_concepts (guaranteed by sanitizer)
        analyses.append(JobSkillAnalysis(
            job_title=title,
            matched_skills=matched_by_title.get(title, []),
            missing_skills=missing_by_title.get(title, [])[:MAX_MISSING],
        ))

    return ResumeAnalysisResult(
        suggested_titles=analyses,
        all_skills_present=llm.all_skills_present,
    )


# =============================================================================
# 8. CLI
# =============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python resume_analyzer.py <resume.txt> [k_titles]")
        sys.exit(1)

    resume_path = sys.argv[1]
    k = int(sys.argv[2]) if len(sys.argv) > 2 else K_TITLES

    try:
        result = analyze_resume_file(resume_path, k=k)
    except ValidationError as e:
        print("❌ Pydantic validation failed:")
        print(e)
        sys.exit(2)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(3)

    print(result.model_dump_json(indent=2, ensure_ascii=False))
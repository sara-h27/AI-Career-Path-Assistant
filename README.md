# مسیر: AI Career Path Assistant

Rahnama College ML Bootcamp hackathon (RFP RC-MLB-HACK-2026-01). A Persian, right-to-left assistant with one workspace for both modules:

- **Conversation (Module A):** at most six questions, each with tap-to-answer options, find the target role, target level and current skills. **📎 Attach a resume** in the same chat (Module B): it fills in skills, experience and education, suggests roles that fit, and the assistant asks only what's still missing.
- **Roadmap:** computed from a skill graph (DAG), shown as numbered steps or as a graph. Each step carries checked learning links.
- **Jobs:** postings retrieved from Qdrant and re-ranked against the profile. The top 10 show a match score, matched and missing skills, a score breakdown and a link to the original ad. "Roadmap for this job" builds a roadmap from that ad's missing skills (B-10).

## Run (one command)

```bash
docker compose up --build        # Qdrant (qdrant/qdrant) + app → http://localhost:8000
```

The embedding model (~240 MB) lives in `models/`. It's kept outside git, so share the folder with the team. Docker copies it into the image, because Hugging Face is not reachable from every network. If it's missing, FastEmbed downloads it on first start.

Without Docker: `run.cmd` (Windows) or `./run.sh` → http://localhost:8000. These create `.venv` on first run, install the requirements and start the server. Without a Qdrant server, Qdrant runs in-process. API docs: `/api/docs`.

The app works offline by default (rule-based extraction, no API cost). For the LLM, copy `.env.example` to `.env` and set `OPENAI_API_KEY`, `OPENAI_BASE_URL` and `OPENAI_MODEL` for the event gateway. **Never commit `.env`.**

Tests: `.venv/Scripts/python -m pytest` (72 tests). Evaluation: `python eval/evaluate_ranking.py`.

## Architecture

```
server.py                  FastAPI: session, chat, resume upload, jobs, job-gap roadmap + static UI
static/                    single-page RTL frontend (HTML/CSS/JS, no build step, bundled Vazirmatn font)
dialogue/                  Track 3: 6-question state machine, evidence-checked JSON extraction,
                           guardrail (only taxonomy ids), deterministic summary, shared LLM client
engine/dag_engine.py       Track 2: prerequisite closure, cumulative levels, topological study order,
                           resources per concept, job-gap roadmap (B-10)
engine/adapters.py         taxonomy → dialogue schema; DagGraphEngine (dialogue GraphEngine protocol)
matching/resume_parser.py  Track 4: PDF/DOCX → normalised Persian/English text (in memory)
matching/profile.py        B-02 profile (LLM, re-validated against the taxonomy; offline fallback)
matching/retrieval.py      Qdrant index + multilingual embeddings (retrieval stage)
matching/ranker.py         keyword baseline and hybrid re-ranker, explanations, filters
eval/evaluate_ranking.py   Section 10.2 metrics (writes eval/results.md)
scripts/build_taxonomy.py  builds data/taxonomy.json
scripts/build_presentation.py  builds docs/presentation/index.html from index.src.html
scrapers/resources/        learning-resource collector + link checker
tests/                     taxonomy/DAG, dialogue guardrails, RFP scenarios, ranking, HTTP API
docs/report/               technical report (Masir_Technical_Report.pdf, source report.html)
docs/presentation/         11-slide interactive HTML deck (open index.html; works offline)
docs/schemas/              JSON schemas of the API, extraction and resume-profile contracts
```

Deterministic parts (taxonomy, graph, scoring, summary) are separate from generative parts (dialogue and resume extraction). Every model output is validated in code before use, and unknown roles or concepts are discarded.

## Data

| File | Content |
|---|---|
| `data/categories.json` | 5 domains × 5 roles (shared `role_id`s) |
| `data/taxonomy.json` | 25 roles × junior/mid/senior, 145 concepts, 188 prerequisite edges (DAG-checked), 866 aliases. Built by `scripts/build_taxonomy.py` from `data/resources/concept_seeds.json` and `data/taxonomy_aliases.json`. Levels are incremental; a target level includes the lower ones. |
| `data/jobs.json` | 143 postings from Jobinja, e-estekhdam and Jobvision (Track 1), normalised and de-duplicated |
| `data/resources/resources.json` | 777 learning resources (Maktabkhooneh, Aparat, YouTube, Coursera), every link checked at build time |
| `data/eval/` | 3 synthetic resumes + graded relevance labels |

## Ranking method and evaluation (Section 10.2)

1. **Retrieval:** Qdrant over multilingual MiniLM embeddings of each posting (title, requirement text, concept labels). Filters (city, seniority, remote) are applied inside Qdrant. Top 40.
2. **Re-ranking:**
   - 0.40 × concept coverage of the posting's requirements (resume skills expanded with their prerequisites, smoothed)
   - 0.25 × fit to the posting's role (share of the role's required concepts the candidate has)
   - 0.25 × text similarity (average of Qdrant dense similarity and char n-gram TF-IDF)
   - 0.10 × seniority fit

   Posting skills are taxonomy concepts found in the ad text, plus collector tags that fit the posting's role. Matched and missing skills are therefore taxonomy concepts, so they feed the roadmap engine directly.

Each resume is ranked against its own judged pool of 26 postings. Grades: 2 strong, 1 could apply, 0 not relevant. P@5 counts grade ≥ 1; nDCG@10 uses gain 2^g − 1.

| Method (mean of 3 resumes) | P@5 | nDCG@10 |
|---|---|---|
| Keyword overlap baseline | 0.67 | 0.637 |
| Hybrid re-ranker, no dense similarity | 0.73 | 0.733 |
| **RAG: Qdrant retrieval + hybrid with dense similarity (used)** | **0.73** | **0.774** |

The Qdrant retrieval stage brings back 100%, 100% and 90% of the relevant postings in its top 40 over all 143. Per-resume results: `eval/results.md`.

The labels are a first draft by one person and should be reviewed. With 3 resumes the differences between the two hybrid variants are within noise. Cleaning wrong collector tags (e.g. web skills on a tax-accounting ad) lowered the scores from an earlier run but fixed visible errors in explanations and job roadmaps.

## Responsible AI

- **Privacy (NF-03):** resumes are parsed in memory and never written to disk or logs. The upload is disabled until the user acknowledges the notice. Text is sent only to the configured AI gateway.
- **Secrets (NF-04):** keys stay server-side in `.env`, which `.gitignore` covers along with any `*.env` / `.en*` file.
- **Grounding:** roadmap concepts come only from the taxonomy. Links come only from the checked catalogue, never from the model. The summary and job explanations are generated from computed data.
- **Cost (NF-05):** tokens, calls, latency and estimated cost per session are shown in the Profile tab. Set the gateway prices in `.env`.
- **Scraping (NF-08):** the resource collector is rate-limited and identifies itself. The job collector's code still has to be added to the repo (Track 1).

## Models

- Chat and extraction: any OpenAI-compatible or Gemini-native gateway model (`.env`).
- Embeddings: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` via FastEmbed (local, Apache-2.0), or the gateway's embedding model (`EMBEDDING_PROVIDER=gateway`).

## Team and acknowledgements

- Track 1, jobs: Sara
- Track 2, taxonomy and graph engine: Hemo
- Track 3, dialogue: Amin
- Track 4, resume parser: Javad
- Resources and integration: Mahdi

Open-source libraries: FastAPI, Uvicorn, Pydantic, httpx, NetworkX, scikit-learn, NumPy, pdfplumber, python-docx, python-bidi, qdrant-client, FastEmbed, Qdrant (Docker image); Vazirmatn font (SIL OFL). AI coding assistants (Claude Code) were used for parts of the implementation and integration, as disclosed in the technical report (RFP §6.2).

"""Section 10.2: Precision@5 and nDCG@10 for the hybrid ranker vs the keyword-overlap baseline.

Usage:  python eval/evaluate_ranking.py

Each resume is ranked against its own judged pool (data/eval/labels.json, >= 20 postings),
so every ranked posting has a label. Relevance is graded 0/1/2: P@5 counts grade >= 1 as relevant,
nDCG@10 uses gain 2^grade - 1. Profiles come from the deterministic extractor so results are
reproducible without API calls. Writes eval/results.md and eval/results.json.
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import DAGEngine  # noqa: E402
from engine.adapters import build_guardrail  # noqa: E402
from matching.profile import extract_profile_offline  # noqa: E402
from matching.ranker import JobRanker, load_jobs  # noqa: E402
from matching.retrieval import QdrantJobIndex  # noqa: E402

EVAL_DIR = ROOT / "data" / "eval"


def precision_at(ranked, labels, k=5):
    return sum(labels[j] >= 1 for j in ranked[:k]) / k


def ndcg_at(ranked, labels, k=10):
    def dcg(grades):
        return sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(grades[:k]))
    ideal = dcg(sorted(labels.values(), reverse=True))
    return dcg([labels[j] for j in ranked]) / ideal if ideal else 0.0


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    spec = json.loads((EVAL_DIR / "labels.json").read_text(encoding="utf-8"))["resumes"]
    engine = DAGEngine()
    guardrail = build_guardrail(engine)
    jobs = load_jobs(guardrail)
    by_id = {j["job_id"]: j for j in jobs}
    try:
        index = QdrantJobIndex(jobs, engine.concepts, engine.roles)
        print(f"Qdrant: {index.backend}, embeddings: {index.embedder.name}")
    except Exception as exc:  # embeddings/Qdrant unavailable: evaluate the other methods only
        index = None
        print(f"Qdrant retrieval skipped: {type(exc).__name__}")
    ranker = JobRanker(engine, guardrail, jobs, index=index)

    rows, results, recall = [], {}, {}
    for name, item in spec.items():
        labels = item["labels"]
        pool = [by_id[j] for j in labels]
        text = (EVAL_DIR / item["file"]).read_text(encoding="utf-8")
        profile = extract_profile_offline(text, guardrail, ranker.cities())
        methods = {
            "keyword_baseline": [r.job["job_id"] for r in ranker.keyword_baseline(text, jobs=pool, top_k=len(pool))],
            "hybrid_no_dense": [r.job["job_id"] for r in ranker.rank(profile, text, jobs=pool, top_k=len(pool), use_index=False)],
        }
        if index is not None:
            methods["rag_hybrid (default)"] = [r.job["job_id"] for r in ranker.rank(
                profile, text, jobs=pool, top_k=len(pool), dense_in_score=True)]
            # Retrieval stage over the whole corpus: share of relevant judged postings in Qdrant's top-K.
            hits = index.search(profile, limit=ranker.retrieve_k)
            relevant = [j for j, g in labels.items() if g >= 1]
            recall[name] = sum(j in hits for j in relevant) / len(relevant)
        results[name] = {}
        for method, ranked in methods.items():
            p5, n10 = precision_at(ranked, labels), ndcg_at(ranked, labels)
            results[name][method] = {"P@5": round(p5, 3), "nDCG@10": round(n10, 3), "top5": ranked[:5]}
            rows.append((name, method, p5, n10))

    lines = ["| Resume | Method | P@5 | nDCG@10 |", "|---|---|---|---|"]
    lines += [f"| {n} | {m} | {p:.2f} | {d:.3f} |" for n, m, p, d in rows]
    for method in dict.fromkeys(r[1] for r in rows):
        ps = [r[2] for r in rows if r[1] == method]
        ds = [r[3] for r in rows if r[1] == method]
        lines.append(f"| **mean** | **{method}** | **{sum(ps) / len(ps):.2f}** | **{sum(ds) / len(ds):.3f}** |")
    if recall:
        lines += ["", f"Qdrant retrieval stage, Recall@{ranker.retrieve_k} of relevant postings over all "
                      f"{len(jobs)} postings: " + ", ".join(f"{k} {v:.2f}" for k, v in recall.items())]
    table = "\n".join(lines)
    print(table)
    (ROOT / "eval" / "results.md").write_text(
        "# Ranking evaluation (Section 10.2)\n\n" + table + "\n\nPools and graded labels: `data/eval/labels.json`.\n",
        encoding="utf-8")
    (ROOT / "eval" / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()

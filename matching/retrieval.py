"""Dense retrieval of postings with Qdrant (RAG retrieval stage for Module B).

Stage 1 (this module): embed every posting once into a Qdrant collection; at query time embed the
resume profile and fetch the nearest postings, with B-08 filters applied inside Qdrant.
Stage 2 (ranker.JobRanker): re-rank those candidates with taxonomy-grounded features.

Qdrant: QDRANT_URL (default http://localhost:6333, started by docker compose from the
qdrant/qdrant image). If the server is unreachable we fall back to qdrant-client's in-process
mode, so the app and the evaluation still run without Docker.

Embeddings: EMBEDDING_PROVIDER=fastembed (default, local ONNX multilingual model, no API cost) or
gateway (OpenAI-compatible /embeddings with EMBEDDING_MODEL).
"""
import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Dict, List, Optional

import httpx

FASTEMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


# ------------------------------------------------------------------ embedders
MODEL_DIR = Path(__file__).resolve().parents[1] / "models"


class FastEmbedEmbedder:
    def __init__(self, model_name: str = FASTEMBED_MODEL):
        from fastembed import TextEmbedding  # imported lazily: optional dependency
        self.name = model_name
        # Prefer the copy shipped in models/ (Hugging Face is not reachable from every network,
        # e.g. inside Docker in Iran); download only if it is missing.
        cache = Path(os.getenv("MODEL_CACHE_DIR", MODEL_DIR))
        if any(cache.glob("models--*")):
            self._model = TextEmbedding(model_name, cache_dir=str(cache), local_files_only=True)
        else:
            self._model = TextEmbedding(model_name, cache_dir=str(cache))
        self.dim = len(next(iter(self._model.embed(["probe"]))))

    def embed(self, texts: List[str]) -> List[List[float]]:
        return [v.tolist() for v in self._model.embed(texts)]


class GatewayEmbedder:
    """OpenAI-compatible /embeddings endpoint of the hackathon gateway."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 20.0):
        self.name = model
        self._url = base_url.rstrip("/") + "/embeddings"
        self._headers = {"Authorization": "Bearer " + api_key}
        self._timeout = timeout
        self.dim = len(self.embed(["probe"])[0])

    def embed(self, texts: List[str]) -> List[List[float]]:
        out = []
        with httpx.Client(timeout=self._timeout) as client:
            for i in range(0, len(texts), 64):
                r = client.post(self._url, headers=self._headers, json={"model": self.name, "input": texts[i:i + 64]})
                r.raise_for_status()
                out += [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]
        return out


def make_embedder():
    provider = os.getenv("EMBEDDING_PROVIDER", "fastembed").strip().lower()
    if provider == "gateway":
        return GatewayEmbedder(os.getenv("OPENAI_BASE_URL", ""), os.getenv("OPENAI_API_KEY", ""),
                               os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"))
    return FastEmbedEmbedder(os.getenv("FASTEMBED_MODEL", FASTEMBED_MODEL))


# ------------------------------------------------------------------ texts
def posting_document(job: dict, concepts: Dict[str, dict]) -> str:
    """Title + the posting's own requirement text first (keeps stack words such as Python vs .NET),
    then concept labels. Small models read ~128 tokens, so the most specific text goes first."""
    labels = [concepts[c]["title_en"] for c in job["concept_ids"] if c in concepts]
    requirements = " ".join((job.get("requirements") or job.get("description") or "").split())[:300]
    return " | ".join(filter(None, [job.get("title"), requirements, ", ".join(labels)]))


def profile_query(profile, concepts: Dict[str, dict], roles: Dict[str, dict]) -> str:
    role_names = [f"{roles[r]['title_fa']} {roles[r]['title_en']}" for r in profile.role_ids if r in roles]
    labels = [f"{concepts[c]['title_fa']} {concepts[c]['title_en']}" for c in profile.concept_ids if c in concepts]
    return " | ".join(filter(None, ["، ".join(role_names + profile.previous_roles), "، ".join(labels)]))


# ------------------------------------------------------------------ index
class QdrantJobIndex:
    def __init__(self, jobs: List[dict], concepts: Dict[str, dict], roles: Dict[str, dict], embedder=None,
                 url: Optional[str] = None):
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, PointStruct, VectorParams

        self.concepts, self.roles = concepts, roles
        self.embedder = embedder or make_embedder()
        url = url or os.getenv("QDRANT_URL", "http://localhost:6333")
        # Never send local/compose traffic through a system proxy (e.g. a VPN client on 127.0.0.1).
        bypass = {"localhost", "127.0.0.1", "qdrant", *filter(None, os.getenv("NO_PROXY", "").split(","))}
        os.environ["NO_PROXY"] = ",".join(sorted(bypass))
        try:
            self.client = QdrantClient(url=url, timeout=3)
            self.client.get_collections()
            self.backend = f"qdrant server ({url})"
        except Exception:
            self.client = QdrantClient(":memory:")
            self.backend = "qdrant in-process (server unreachable)"

        docs = [posting_document(j, concepts) for j in jobs]
        digest = hashlib.sha1((self.embedder.name + json.dumps(docs, ensure_ascii=False)).encode()).hexdigest()[:10]
        self.collection = f"jobs_{digest}"
        existing = {c.name for c in self.client.get_collections().collections}
        if self.collection not in existing:
            self.client.create_collection(self.collection,
                                          vectors_config=VectorParams(size=self.embedder.dim, distance=Distance.COSINE))
            vectors = self.embedder.embed(docs)
            self.client.upsert(self.collection, points=[
                PointStruct(id=str(uuid.uuid5(uuid.NAMESPACE_URL, j["job_id"])), vector=v, payload={
                    "job_id": j["job_id"],
                    "role_id": j.get("role_id"),
                    "city": (j.get("location") or {}).get("city"),
                    "remote": bool((j.get("location") or {}).get("remote")),
                    "seniority": j.get("seniority"),
                }) for j, v in zip(jobs, vectors)])

    def search(self, profile, filters=None, job_ids: Optional[List[str]] = None, limit: int = 40) -> Dict[str, float]:
        """job_id -> cosine similarity for the nearest postings that pass the filters."""
        from qdrant_client import models as m

        must = []
        if filters is not None:
            if filters.city:
                must.append(m.FieldCondition(key="city", match=m.MatchValue(value=filters.city)))
            if filters.remote_only:
                must.append(m.FieldCondition(key="remote", match=m.MatchValue(value=True)))
            if filters.seniority:  # unknown seniority stays eligible, as in Filters.accept
                must.append(m.Filter(should=[m.FieldCondition(key="seniority", match=m.MatchValue(value=filters.seniority)),
                                             m.IsNullCondition(is_null=m.PayloadField(key="seniority"))]))
        if job_ids is not None:
            must.append(m.FieldCondition(key="job_id", match=m.MatchAny(any=job_ids)))
        query = profile_query(profile, self.concepts, self.roles) or "resume"
        vector = self.embedder.embed([query])[0]
        hits = self.client.query_points(self.collection, query=vector, limit=limit,
                                        query_filter=m.Filter(must=must) if must else None).points
        return {h.payload["job_id"]: float(h.score) for h in hits}

"""Stage 2: select, verify and publish learning resources per concept.

Usage:  python scrapers/resources/build.py [--no-verify]

Reads data/resources/raw/<source>.json + concept_seeds.json and writes
  data/resources/resources.json  (verified resources, indexed by concept)
  data/resources/coverage.json   (resource counts per concept, gaps listed first)
Every published URL has been fetched successfully at build time (RFP A-07);
re-run before the demo to re-verify.
"""
import argparse
import hashlib
import re
import sys
import threading
from datetime import datetime, timezone

from common import (
    ACCESSIBLE_FROM_IRAN, DATA_DIR, DELAY, RAW_DIR, RateLimiter, get,
    load_json, load_seeds, make_session, matches, save_json,
)

# Max resources kept per concept from each source (Persian, Iran-accessible first).
QUOTA = {"maktabkhooneh": 2, "aparat": 1, "youtube": 2, "coursera": 1}
CONSIDER_TOP = 5          # only look at each source's top-N search results
MIN_VIDEO_SECONDS = 180   # drop shorts / trailers
SOURCE_ORDER = ["maktabkhooneh", "aparat", "youtube", "coursera"]
TYPE = {"maktabkhooneh": "course", "coursera": "course", "aparat": "video", "youtube": "video"}


def video_seconds(c):
    if c["source"] == "aparat":
        return c.get("duration_sec") or 0
    if c["source"] == "youtube":
        parts = [int(p) for p in (c.get("length") or "0").split(":") if p.isdigit()]
        secs = 0
        for p in parts:
            secs = secs * 60 + p
        return secs
    return None


def relevant(c, concept):
    if matches(c["title"], concept.get("exclude", [])):
        return False
    if matches(c["title"], concept["match"]):
        return True
    return c["source"] == "coursera" and any(matches(sk, concept["match"]) for sk in c.get("skills", []))


def clean_description(text):
    text = re.sub(r"https?://\S+", "", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:300] + ("…" if len(text) > 300 else "")


def select(concept, raw):
    picked = []
    for source in SOURCE_ORDER:
        cands = [c for c in raw.get(source, {}).get(concept["concept_id"], [])[:CONSIDER_TOP + 4]
                 if relevant(c, concept)]
        secs_ok = [c for c in cands if video_seconds(c) is None or video_seconds(c) >= MIN_VIDEO_SECONDS]
        cands = secs_ok[:CONSIDER_TOP]
        if source == "youtube":
            # one Persian + one English video when both exist
            fa = [c for c in cands if c["language"] == "fa"]
            en = [c for c in cands if c["language"] == "en"]
            cands = (fa[:1] + en[:1] + fa[1:] + en[1:])
        elif source == "aparat":
            # Aparat's search order is weak; prefer the most-viewed matching video
            cands.sort(key=lambda c: -(c.get("popularity") or 0))
        picked.extend(cands[:QUOTA[source]])
    return picked


def verify_one(s, lim, res):
    src, url = res["source"], res["url"]
    if src == "youtube":
        r = get(s, lim, "https://www.youtube.com/oembed?format=json&url=" + url)
        # 401/403 = embedding disabled but the video exists; deleted/private videos give 404/400
        ok = r is not None and r.status_code in (200, 401, 403)
    elif src == "aparat":
        uid = url.rsplit("/", 1)[-1]
        r = get(s, lim, "https://www.aparat.com/etc/api/video/videohash/" + uid)
        ok = r is not None and r.status_code == 200 and '"uid"' in r.text
    else:
        r = get(s, lim, url)
        ok = r is not None and r.status_code == 200
    res["http_status"] = r.status_code if r is not None else None
    res["verified"] = ok
    res["verified_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def verify_all(resources):
    by_source = {}
    for r in resources:
        by_source.setdefault(r["source"], []).append(r)

    def worker(source, items):
        s, lim = make_session(), RateLimiter(DELAY[source])
        for i, r in enumerate(items, 1):
            verify_one(s, lim, r)
            if i % 25 == 0:
                print("[verify %s] %d/%d" % (source, i, len(items)), flush=True)

    threads = [threading.Thread(target=worker, args=kv) for kv in by_source.items()]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()

    concepts = load_seeds()
    raw = {src: load_json(RAW_DIR / ("%s.json" % src), {}) for src in SOURCE_ORDER}

    by_url = {}
    for concept in concepts:
        for c in select(concept, raw):
            res = by_url.get(c["url"])
            if res is None:
                res = by_url[c["url"]] = {
                    "resource_id": "res_" + hashlib.sha1(c["url"].encode()).hexdigest()[:10],
                    "title": c["title"],
                    "url": c["url"],
                    "source": c["source"],
                    "provider": c.get("provider", ""),
                    "language": c["language"],
                    "type": TYPE[c["source"]],
                    "is_free": c.get("is_free"),
                    "accessible_from_iran": ACCESSIBLE_FROM_IRAN[c["source"]],
                    "level": c.get("difficulty") or concept["level"],
                    "description": clean_description(c.get("description")),
                    "concept_ids": [],
                    "role_ids": [],
                }
            if concept["concept_id"] not in res["concept_ids"]:
                res["concept_ids"].append(concept["concept_id"])
            for role in concept["roles"]:
                if role not in res["role_ids"]:
                    res["role_ids"].append(role)

    resources = list(by_url.values())
    print("selected %d resources" % len(resources))
    if not args.no_verify:
        verify_all(resources)
        failed = [r for r in resources if not r["verified"]]
        for r in failed:
            print("DROP (status %s): %s" % (r["http_status"], r["url"]))
        resources = [r for r in resources if r["verified"]]

    def sort_key(r):  # Persian + reachable from Iran first
        return (r["language"] != "fa", not r["accessible_from_iran"], SOURCE_ORDER.index(r["source"]))

    by_concept = {}
    for c in concepts:
        items = sorted((r for r in resources if c["concept_id"] in r["concept_ids"]), key=sort_key)
        by_concept[c["concept_id"]] = [r["resource_id"] for r in items]

    save_json(DATA_DIR / "resources.json", {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verified": not args.no_verify,
        "resources": sorted(resources, key=lambda r: r["resource_id"]),
        "by_concept": by_concept,
    })

    rid = {r["resource_id"]: r for r in resources}
    coverage = []
    for c in concepts:
        items = [rid[i] for i in by_concept[c["concept_id"]]]
        coverage.append({
            "concept_id": c["concept_id"],
            "total": len(items),
            "fa_accessible": sum(r["language"] == "fa" and r["accessible_from_iran"] for r in items),
            "free": sum(bool(r["is_free"]) for r in items),
        })
    coverage.sort(key=lambda x: (x["fa_accessible"] > 0, x["total"]))
    save_json(DATA_DIR / "coverage.json", coverage)

    gaps = [x["concept_id"] for x in coverage if x["total"] == 0]
    no_fa = [x["concept_id"] for x in coverage if x["total"] and not x["fa_accessible"]]
    print("resources: %d | concepts: %d | with no resource: %d %s | no Persian/Iran-accessible: %d %s"
          % (len(resources), len(concepts), len(gaps), gaps, len(no_fa), no_fa))


if __name__ == "__main__":
    main()

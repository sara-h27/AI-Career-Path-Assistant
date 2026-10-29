"""Stage 1: search each source for every seed concept and cache raw candidates.

Usage:  python scrapers/resources/collect.py [--sources maktabkhooneh,aparat,youtube,coursera]
                                             [--concepts sql_basics,docker] [--refresh]

Writes data/resources/raw/<source>.json  ({concept_id: [candidate, ...]}).
Already-collected concepts are skipped unless --refresh is given.
"""
import argparse
import json
import sys
import threading
from urllib.parse import quote

from common import (
    DELAY, RAW_DIR, RateLimiter, get, language_of, load_json, load_seeds,
    make_session, matches, meta_description, save_json,
)

MAKTAB_LIMIT = 10
YT_EN_LIMIT = 5
YT_FA_LIMIT = 4
COURSERA_LIMIT = 6
APARAT_LIMIT = 6
DESCRIBE_TOP = 3  # fetch page descriptions for the first N title-matching hits


# ---------------------------------------------------------------- maktabkhooneh
def search_maktab(s, lim, c):
    url = ("https://maktabkhooneh.org/api/v1/courses/search/?limit=%d&offset=0&q=%s&sorting=relevance"
           % (MAKTAB_LIMIT, quote(c["q_fa"])))
    r = get(s, lim, url)
    if r is None or r.status_code != 200:
        return None
    out = []
    for x in r.json().get("courses", {}).get("results", []):
        prices = x.get("prices") or {}
        spec = x.get("specifics") or {}
        out.append({
            "source": "maktabkhooneh",
            "title": x["title"],
            "url": "https://maktabkhooneh.org/course/%s-mk%s/" % (x["slug"], x["id"]),
            "provider": (x.get("organization") or {}).get("name", ""),
            "is_free": (prices.get("real") or 0) == 0,
            "hours": x.get("required_hours"),
            "popularity": x.get("no_of_students"),
            "rating": spec.get("avg_rating"),
            "description": "",
        })
    return out


def describe_page(s, lim, cand):
    r = get(s, lim, cand["url"])
    if r is not None and r.status_code == 200:
        cand["description"] = meta_description(r.text)


# ---------------------------------------------------------------- aparat
def search_aparat(s, lim, c):
    url = "https://www.aparat.com/etc/api/videoBySearch/text/%s/perpage/%d" % (quote(c["q_fa"]), APARAT_LIMIT)
    r = get(s, lim, url)
    if r is None or r.status_code != 200:
        return None
    out = []
    for x in r.json().get("videobysearch") or []:
        out.append({
            "source": "aparat",
            "title": x["title"],
            "url": "https://www.aparat.com/v/%s" % x["uid"],
            "provider": x.get("sender_name") or x.get("username", ""),
            "is_free": True,
            "duration_sec": x.get("duration"),
            "popularity": x.get("visit_cnt"),
            "description": "",
        })
    return out


# ---------------------------------------------------------------- youtube
def _walk_videos(o, acc):
    if isinstance(o, dict):
        if "videoRenderer" in o:
            acc.append(o["videoRenderer"])
        for v in o.values():
            _walk_videos(v, acc)
    elif isinstance(o, list):
        for v in o:
            _walk_videos(v, acc)


def _yt_query(s, lim, query, limit):
    r = get(s, lim, "https://www.youtube.com/results?search_query=" + quote(query))
    if r is None or r.status_code != 200:
        return None
    i = r.text.find("var ytInitialData = ")
    if i < 0:
        return None
    data, _ = json.JSONDecoder().raw_decode(r.text[i + len("var ytInitialData = "):])
    vids = []
    _walk_videos(data, vids)
    out = []
    for v in vids[:limit]:
        title = "".join(run["text"] for run in v["title"].get("runs", []))
        snippet = ""
        dms = v.get("detailedMetadataSnippets") or []
        if dms:
            snippet = "".join(run["text"] for run in dms[0].get("snippetText", {}).get("runs", []))
        views = (v.get("viewCountText") or {}).get("simpleText", "")
        out.append({
            "source": "youtube",
            "title": title,
            "url": "https://www.youtube.com/watch?v=%s" % v["videoId"],
            "provider": "".join(run["text"] for run in (v.get("ownerText") or {}).get("runs", [])),
            "is_free": True,
            "length": (v.get("lengthText") or {}).get("simpleText"),
            "popularity": int("".join(ch for ch in views if ch.isdigit()) or 0),
            "description": snippet,
        })
    return out


def search_youtube(s, lim, c):
    out = []
    for q, limit in ((c.get("q_en"), YT_EN_LIMIT), (c.get("q_fa"), YT_FA_LIMIT)):
        if not q:
            continue
        res = _yt_query(s, lim, q, limit)
        if res is None:
            return None
        out.extend(res)
    return out


# ---------------------------------------------------------------- coursera
def search_coursera(s, lim, c):
    if c.get("iran_specific") or not c.get("q_en"):
        return []
    r = get(s, lim, "https://www.coursera.org/search?language=English&query=" + quote(c["q_en"]))
    if r is None or r.status_code != 200:
        return None
    key = "window.__APOLLO_STATE__ = "
    i = r.text.find(key)
    if i < 0:
        return None
    state, _ = json.JSONDecoder().raw_decode(r.text[i + len(key):])
    out = []
    for v in state.values():
        if not isinstance(v, dict) or v.get("__typename") != "Search_ProductHit":
            continue
        if not v.get("url"):
            continue
        out.append({
            "source": "coursera",
            "title": v["name"],
            "url": "https://www.coursera.org" + v["url"],
            "provider": ", ".join(v.get("partners") or []),
            "is_free": bool(v.get("isCourseFree")),
            "difficulty": (v.get("productDifficultyLevel") or "").lower() or None,
            "product_type": v.get("productType"),
            "skills": v.get("skills") or [],
            "rating": v.get("avgProductRating"),
            "popularity": v.get("numProductRatings"),
            "description": "",
        })
        if len(out) >= COURSERA_LIMIT:
            break
    return out


SOURCES = {
    "maktabkhooneh": (search_maktab, True),
    "aparat": (search_aparat, False),
    "youtube": (search_youtube, False),
    "coursera": (search_coursera, True),
}


def run_source(name, concepts, refresh, log_lock):
    search, needs_description = SOURCES[name]
    path = RAW_DIR / ("%s.json" % name)
    cache = load_json(path, {})
    s, lim = make_session(), RateLimiter(DELAY[name])
    for n, c in enumerate(concepts, 1):
        cid = c["concept_id"]
        if cid in cache and not refresh:
            continue
        results = search(s, lim, c)
        if results is None:
            with log_lock:
                print("[%s] %s: FAILED" % (name, cid), flush=True)
            continue
        if needs_description:
            for cand in [x for x in results if matches(x["title"], c["match"])][:DESCRIBE_TOP]:
                describe_page(s, lim, cand)
        for cand in results:
            cand["language"] = language_of(cand["title"])
        cache[cid] = results
        save_json(path, cache)
        with log_lock:
            hit = sum(matches(x["title"], c["match"]) for x in results)
            print("[%s] %d/%d %s: %d results, %d title matches" % (name, n, len(concepts), cid, len(results), hit), flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default=",".join(SOURCES))
    ap.add_argument("--concepts", default="")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    concepts = load_seeds()
    if args.concepts:
        wanted = set(args.concepts.split(","))
        concepts = [c for c in concepts if c["concept_id"] in wanted]
    lock = threading.Lock()
    threads = [threading.Thread(target=run_source, args=(name, concepts, args.refresh, lock))
               for name in args.sources.split(",")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()

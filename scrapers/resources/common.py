"""Shared helpers for the learning-resource collector."""
import html as html_lib
import json
import re
import threading
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "resources"
RAW_DIR = DATA_DIR / "raw"
SEEDS_PATH = DATA_DIR / "concept_seeds.json"

# Browser UA plus an identifying token (NF-08: identify the collector).
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 "
    "RahnamaCareerBot/0.1 (Rahnama College hackathon; learning-resource catalogue)"
)

# Seconds between requests to the same host.
DELAY = {"maktabkhooneh": 1.5, "aparat": 1.5, "youtube": 2.0, "coursera": 2.0}

PERSIAN_RE = re.compile(r"[؀-ۿ]")
ACCESSIBLE_FROM_IRAN = {"maktabkhooneh": True, "aparat": True, "youtube": False, "coursera": False}


def make_session():
    s = requests.Session()
    # The Windows system proxy (local VPN client) times out on Iranian sites;
    # every source is reachable directly.
    s.trust_env = False
    s.headers["User-Agent"] = USER_AGENT
    s.headers["Accept-Language"] = "fa,en;q=0.8"
    return s


class RateLimiter:
    def __init__(self, delay):
        self.delay = delay
        self.last = 0.0
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            gap = self.delay - (time.monotonic() - self.last)
            if gap > 0:
                time.sleep(gap)
            self.last = time.monotonic()


def get(session, limiter, url, retries=2, **kw):
    """GET with rate limiting and simple retries; returns Response or None."""
    for attempt in range(retries + 1):
        limiter.wait()
        try:
            r = session.get(url, timeout=25, **kw)
            r.encoding = "utf-8"  # all sources serve UTF-8; requests sometimes guesses latin-1
            if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(5 * (attempt + 1))
                continue
            return r
        except requests.RequestException:
            if attempt == retries:
                return None
            time.sleep(3 * (attempt + 1))
    return None


def normalize(text):
    text = (text or "").lower()
    text = text.replace("ي", "ی").replace("ك", "ک").replace("ة", "ه")
    text = text.replace("‌", " ").replace("‌", " ")
    return re.sub(r"\s+", " ", text).strip()


def matches(title, patterns):
    """True if title contains any pattern; 'a+b' requires both a and b."""
    t = normalize(title)
    for p in patterns:
        parts = [normalize(x) for x in p.split("+")]
        if all(part and part in t for part in parts):
            return True
    return False


def language_of(text):
    return "fa" if PERSIAN_RE.search(text or "") else "en"


def load_seeds():
    return json.loads(SEEDS_PATH.read_text(encoding="utf-8"))["concepts"]


def load_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def meta_description(html):
    for name in ("description", "og:description"):
        m = re.search(
            r'<meta[^>]+(?:name|property)="%s"[^>]*content="([^"]*)"' % re.escape(name), html
        )
        if m:
            return html_lib.unescape(m.group(1)).strip()
    return ""

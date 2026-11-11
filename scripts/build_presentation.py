"""Build docs/presentation/index.html from index.src.html + assets/demo_data.json.

Usage:  python scripts/build_presentation.py
Edit slides in index.src.html; demo_data.json holds the real engine output shown on the
roadmap and job slides (regenerate it if the taxonomy or job data change).
"""
import json
from pathlib import Path

DECK = Path(__file__).resolve().parents[1] / "docs" / "presentation"

src = (DECK / "index.src.html").read_text(encoding="utf-8")
data = json.loads((DECK / "assets" / "demo_data.json").read_text(encoding="utf-8"))
(DECK / "index.html").write_text(src.replace("/*DATA*/null", json.dumps(data, ensure_ascii=False)), encoding="utf-8")
print("built", DECK / "index.html")

"""
Pipeline: parse resume (PDF/DOCX) -> analyze -> show results.
Integrates resume_parser.py and resume_analyzer.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from resume_parser import parse_resume_file
from resume_analyzer import analyze_resume_file, ResumeAnalysisResult


def run_pipeline(resume_path: str, k_titles: int = 5) -> ResumeAnalysisResult:
    print(f"Parsing resume: {resume_path}")
    # If input is PDF/DOCX, parse it; otherwise assume plain text
    p = Path(resume_path)
    if p.suffix.lower() in (".pdf", ".docx"):
        text = parse_resume_file(p)
    else:
        text = p.read_text(encoding="utf-8")

    # Write temporary parsed text if needed (analyzer expects a file path)
    tmp_path = p.with_suffix(p.suffix + ".parsed.txt")
    tmp_path.write_text(text, encoding="utf-8")
    print(f"Parsed text saved temporarily to: {tmp_path}")

    print(f"Analyzing resume (k={k_titles})...")
    result = analyze_resume_file(tmp_path, k=k_titles)
    return result


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Resume Pipeline: parse + analyze")
    ap.add_argument("resume", help="Path to resume (.pdf, .docx, or .txt)")
    ap.add_argument("--k", type=int, default=5, help="Number of suggested titles")
    args = ap.parse_args()

    result = run_pipeline(args.resume, k_titles=args.k)
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(result.model_dump_json(indent=2, ensure_ascii=False))

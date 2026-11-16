"""Social media manager - step 1 (email intake) and step 2 (LLM1: KPI extraction).

Usage:
    # Step 1 only: fetch and save emails
    python main.py gmail [--query "to:posts@yourco.com"] [--max 10] [--mark-processed]
    python main.py eml samples/sample_request.eml

    # Step 1 + 2: fetch, extract the brief, mark processed only if extraction succeeded
    python main.py gmail --extract --mark-processed

    # Step 2 on emails already saved by step 1
    python main.py kpi data/intake/sample_request.json [more.json ...]

Intake JSON goes to data/intake/, briefs (PostKPIs) to data/kpis/.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from email_intake import GmailIntake, IncomingEmail, load_eml

INTAKE_DIR = Path("data/intake")


def save_intake(email_obj: IncomingEmail) -> Path:
    INTAKE_DIR.mkdir(parents=True, exist_ok=True)
    out = INTAKE_DIR / f"{email_obj.message_id}.json"
    out.write_text(email_obj.to_json(indent=2))
    return out


def run_extraction(extractor, em: IncomingEmail) -> bool:
    """Run LLM1 on one email, print and save the brief. Returns True on success."""
    from kpi_extraction import ExtractionError

    try:
        result = extractor.extract(em)
    except ExtractionError as e:
        print(f"!! LLM1 failed for {em.message_id}: {e}", file=sys.stderr)
        return False

    path = result.save()
    k = result.kpis
    if k.is_post_request:
        print(f"[LLM1] {em.message_id}: post request for {k.company.name or 'unknown company'}"
              f" ({k.platform or 'platform not stated'})")
    else:
        print(f"[LLM1] {em.message_id}: not a post request - {k.not_a_request_reason}")
    print(json.dumps(result.to_dict()["kpis"], indent=2, ensure_ascii=False))
    print(f"-> saved {path}  (tokens in/out: {result.usage['input_tokens']}/{result.usage['output_tokens']})\n")
    return True


def make_extractor(args):
    if args.backend == "ollama":
        from kpi_extraction.ollama_extractor import OllamaKPIExtractor

        return OllamaKPIExtractor(model=args.model) if args.model else OllamaKPIExtractor()

    from kpi_extraction import KPIExtractor

    kwargs = {}
    if getattr(args, "model", None):
        kwargs["model"] = args.model
    if getattr(args, "effort", None):
        kwargs["effort"] = args.effort
    return KPIExtractor(**kwargs)


def add_llm_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--backend", choices=["claude", "ollama"], default="claude",
                   help="claude = Anthropic API, ollama = model running on this computer")
    p.add_argument("--model", help="override the LLM1 model (default claude-opus-5-5)")
    p.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"])


def main() -> None:
    ap = argparse.ArgumentParser(description="Social media manager pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gmail", help="fetch unread emails from Gmail")
    g.add_argument("--query", default=os.getenv("GMAIL_QUERY", ""), help="extra Gmail search filter")
    g.add_argument("--max", type=int, default=10)
    g.add_argument("--mark-processed", action="store_true", help="label as smm-processed and mark read")
    g.add_argument("--extract", action="store_true", help="also run LLM1 KPI extraction")
    add_llm_args(g)

    e = sub.add_parser("eml", help="parse a local .eml file")
    e.add_argument("path")
    e.add_argument("--extract", action="store_true", help="also run LLM1 KPI extraction")
    add_llm_args(e)

    k = sub.add_parser("kpi", help="run LLM1 on intake JSON files from data/intake/")
    k.add_argument("paths", nargs="+")
    add_llm_args(k)

    args = ap.parse_args()

    if args.cmd == "gmail":
        intake = GmailIntake(
            credentials_file=os.getenv("GMAIL_CREDENTIALS", "credentials.json"),
            token_file=os.getenv("GMAIL_TOKEN", "token.json"),
        )
        extractor = make_extractor(args) if args.extract else None
        emails = list(intake.fetch_new(query=args.query, max_results=args.max))
        if not emails:
            print("No new emails.")
        for em in emails:
            print(f"-> saved {save_intake(em)}")
            ok = run_extraction(extractor, em) if extractor else True
            # With --extract, only mark the email processed once LLM1 succeeded,
            # so a failed extraction is retried on the next run.
            if args.mark_processed and ok:
                intake.mark_processed(em.message_id)

    elif args.cmd == "eml":
        em = load_eml(args.path)
        print(em.to_json(indent=2))
        print(f"-> saved {save_intake(em)}")
        if args.extract:
            run_extraction(make_extractor(args), em)

    else:  # kpi
        extractor = make_extractor(args)
        failed = 0
        for p in args.paths:
            if not run_extraction(extractor, IncomingEmail.load(p)):
                failed += 1
        if failed:
            sys.exit(1)# code 1 signal to script or automation tools that something went wrong


if __name__ == "__main__":
    main()

"""Social media manager - step 1 (email intake), step 2 (LLM1: KPI extraction), step 3 (LLM2: ideation),
step 4 (LLM3: judge).

Usage:
    # Step 1 only: fetch and save emails
    python main.py gmail [--query "to:posts@yourco.com"] [--max 10] [--mark-processed]
    python main.py eml samples/sample_request.eml

    # Step 1 + 2: fetch, extract the brief, mark processed only if extraction succeeded
    python main.py gmail --extract --mark-processed

    # Step 1 + 2 + 3: also write post ideas for every email that is a post request
    python main.py gmail --ideate --mark-processed
    python main.py eml samples/sample_request.eml --ideate

    # Step 2 on emails already saved by step 1 (add --ideate to continue with step 3)
    python main.py kpi data/intake/sample_request.json [more.json ...]

    # Step 3 on briefs already saved by step 2 (add --judge to continue with step 4)
    python main.py ideas data/kpis/sample_request.json [more.json ...]

    # Step 1 to 4: also score the ideas and pick one
    python main.py gmail --judge --mark-processed
    python main.py eml samples/sample_request.eml --judge

    # Step 4 on ideas already saved by step 3 (the brief is read from data/kpis/; Laya only)
    python main.py judge data/ideas/sample_request.json [more.json ...]

Add --backend ollama to any LLM command to use the local model instead of the Claude API
(--backend and --model are for LLM1 and LLM2 only).
LLM3 always judges with the Laya decision model, on this computer (see README). Add
--judge-model english|multilingual|auto to pick the Laya checkpoint (default: multilingual).
Intake JSON goes to data/intake/, briefs (PostKPIs) to data/kpis/, ideas to data/ideas/,
scores and the chosen idea to data/judgements/.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

from email_intake import GmailIntake, IncomingEmail, load_eml

INTAKE_DIR = Path("data/intake")
KPI_DIR = Path("data/kpis")


def save_intake(email_obj: IncomingEmail) -> Path:
    INTAKE_DIR.mkdir(parents=True, exist_ok=True)
    out = INTAKE_DIR / f"{email_obj.message_id}.json"
    out.write_text(email_obj.to_json(indent=2))
    return out


def run_extraction(extractor, em: IncomingEmail) -> Optional[dict]:
    """Run LLM1 on one email, print and save the brief. Returns the brief, or None if LLM1 failed."""
    from kpi_extraction import ExtractionError

    try:
        result = extractor.extract(em)
    except ExtractionError as e:
        print(f"!! LLM1 failed for {em.message_id}: {e}", file=sys.stderr)
        return None

    path = result.save()
    k = result.kpis
    if k.is_post_request:
        print(f"[LLM1] {em.message_id}: post request for {k.company.name or 'unknown company'}"
              f" ({k.platform or 'platform not stated'})")
    else:
        print(f"[LLM1] {em.message_id}: not a post request - {k.not_a_request_reason}")
    print(json.dumps(result.to_dict()["kpis"], indent=2, ensure_ascii=False))
    print(f"-> saved {path}  (tokens in/out: {result.usage['input_tokens']}/{result.usage['output_tokens']})\n")
    return result.to_dict()


def run_ideation(ideator, brief: dict) -> Optional[dict]:
    """Run LLM2 on one brief, print and save the ideas. Returns the ideas, or None if LLM2 failed."""
    from ideation import IdeationError

    email_id = brief.get("email_id", "unknown")
    try:
        result = ideator.generate(brief)
    except IdeationError as e:
        print(f"!! LLM2 failed for {e}", file=sys.stderr)
        return None

    path = result.save()
    print(f"[LLM2] {email_id}: {len(result.ideas)} ideas")
    for idea in result.ideas:
        print(f"  {idea.idea_id}. {idea.title}: {idea.angle}")
    print(f"-> saved {path}  (tokens in/out: {result.usage['input_tokens']}/{result.usage['output_tokens']})\n")
    return result.to_dict()


def run_judging(judge, brief: dict, ideas: dict) -> bool:
    """Run LLM3 on one set of ideas, print and save the scores and the winner. False if LLM3 failed."""
    from judging import JudgingError

    email_id = brief.get("email_id", "unknown")
    print(f"[LLM3] {email_id}: judging {len(ideas.get('ideas', []))} ideas with {judge.model} ...")

    def show(j) -> None:
        status = "ok" if j.passed_hard_rules else "FAILS HARD RULES"
        print(f"  idea {j.idea_id} ({j.title}): {j.final_score}/100  [{status}]")

    try:
        result = judge.judge(brief, ideas, on_idea_done=show)
    except JudgingError as e:
        print(f"!! LLM3 failed for {e}", file=sys.stderr)
        return False

    path = result.save()
    d = result.decision
    print(f"[LLM3] {email_id}: winner is idea {d.winner_idea_id} ({d.winner.title}), "
          f"ranking {d.ranking}")
    for reason in d.review_reasons:
        print(f"  needs review: {reason}")
    print(f"-> saved {path}  (tokens in/out: {result.usage['input_tokens']}/{result.usage['output_tokens']})\n")
    return True


def continue_from_brief(brief: dict, ideator=None, judge=None) -> bool:
    """LLM2 and then LLM3 on one brief, as far as was asked. Returns False if a step failed."""
    if ideator is None:
        return True
    if not brief.get("kpis", {}).get("is_post_request"):
        print(f"[LLM2] {brief.get('email_id', 'unknown')}: skipped - not a post request\n")
        return True
    ideas = run_ideation(ideator, brief)
    if ideas is None:
        return False
    return run_judging(judge, brief, ideas) if judge else True


def process_email(em: IncomingEmail, extractor, ideator=None, judge=None) -> bool:
    """LLM1, then LLM2 and LLM3 if they are given. Returns False if a step failed."""
    brief = run_extraction(extractor, em)
    if brief is None:
        return False
    return continue_from_brief(brief, ideator, judge)


def load_json(path) -> dict:
    return json.loads(Path(path).read_text())


def make_ideator(args):
    from ideation import Ideator

    return Ideator(backend=args.backend, model=args.model, effort=args.effort, count=args.count)


def make_judge(args):
    from judging import Judge

    # LLM3 is always Laya; --backend and --model only choose the model for LLM1 and LLM2.
    return Judge(model=args.judge_model)


def make_extractor(args):
    if args.backend == "ollama":
        from kpi_extraction.ollama_extractor import OllamaKPIExtractor

        return OllamaKPIExtractor(model=args.model) if args.model else OllamaKPIExtractor()

# --------------------------------
    from kpi_extraction import KPIExtractor

    kwargs = {}
    if getattr(args, "model", None):
        kwargs["model"] = args.model
    if getattr(args, "effort", None):
        kwargs["effort"] = args.effort
    return KPIExtractor(**kwargs)


def add_llm_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--backend", choices=["claude", "ollama"], default="claude",
                   help="for LLM1 and LLM2: claude = Anthropic API, ollama = model running on this "
                        "computer (LLM3 always uses Laya)")
    p.add_argument("--model", help="override the model for LLM1 and LLM2 in this run "
                                   "(default: claude-opus-5-5, or gemma4:e2b-it-qat with ollama)")
    p.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"],
                   help="how hard Claude thinks (ignored by ollama)")
    p.add_argument("--count", type=int, choices=[4, 5], default=5, help="how many ideas LLM2 writes")
    p.add_argument("--judge-model", choices=["multilingual", "english", "auto"],
                   help="Laya checkpoint for LLM3 (default: multilingual, which reads 1024 tokens; "
                        "english reads only 512). LLM3 always uses Laya.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Social media manager pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gmail", help="fetch unread emails from Gmail")
    g.add_argument("--query", default=os.getenv("GMAIL_QUERY", ""), help="extra Gmail search filter")
    g.add_argument("--max", type=int, default=10)
    g.add_argument("--mark-processed", action="store_true", help="label as smm-processed and mark read")
    g.add_argument("--extract", action="store_true", help="also run LLM1 KPI extraction")
    g.add_argument("--ideate", action="store_true", help="also run LLM1 and then LLM2 ideation")
    g.add_argument("--judge", action="store_true", help="also run LLM1, LLM2 and then LLM3 judge")
    add_llm_args(g)

    e = sub.add_parser("eml", help="parse a local .eml file")
    e.add_argument("path")
    e.add_argument("--extract", action="store_true", help="also run LLM1 KPI extraction")
    e.add_argument("--ideate", action="store_true", help="also run LLM1 and then LLM2 ideation")
    e.add_argument("--judge", action="store_true", help="also run LLM1, LLM2 and then LLM3 judge")
    add_llm_args(e)

    k = sub.add_parser("kpi", help="run LLM1 on intake JSON files from data/intake/")
    k.add_argument("paths", nargs="+")
    k.add_argument("--ideate", action="store_true", help="also run LLM2 ideation on each brief")
    k.add_argument("--judge", action="store_true", help="also run LLM2 and then LLM3 judge")
    add_llm_args(k)

    i = sub.add_parser("ideas", help="run LLM2 on briefs from data/kpis/")
    i.add_argument("paths", nargs="+")
    i.add_argument("--judge", action="store_true", help="also run LLM3 judge on the new ideas")
    add_llm_args(i)

    j = sub.add_parser("judge", help="run LLM3 on idea files from data/ideas/")
    j.add_argument("paths", nargs="+")
    add_llm_args(j)

    args = ap.parse_args()

    # Each later step needs the ones before it: --judge implies --ideate, --ideate implies --extract.
    want_judge = getattr(args, "judge", False) or args.cmd == "judge"
    want_ideas = want_judge or getattr(args, "ideate", False) or args.cmd == "ideas"
    want_extract = want_ideas or getattr(args, "extract", False)
    ideator = make_ideator(args) if want_ideas and args.cmd != "judge" else None
    judge = make_judge(args) if want_judge else None

    if args.cmd == "gmail":
        intake = GmailIntake(
            credentials_file=os.getenv("GMAIL_CREDENTIALS", "credentials.json"),
            token_file=os.getenv("GMAIL_TOKEN", "token.json"),
        )
        extractor = make_extractor(args) if want_extract else None
        emails = list(intake.fetch_new(query=args.query, max_results=args.max))
        if not emails:
            print("No new emails.")
        for em in emails:
            print(f"-> saved {save_intake(em)}")
            ok = process_email(em, extractor, ideator, judge) if extractor else True
            # Only mark the email processed once every requested LLM step succeeded,
            # so a failed email is retried on the next run.
            if args.mark_processed and ok:
                intake.mark_processed(em.message_id)
        return

    if args.cmd == "eml":
        em = load_eml(args.path)
        print(em.to_json(indent=2))
        print(f"-> saved {save_intake(em)}")
        ok = process_email(em, make_extractor(args), ideator, judge) if want_extract else True
        if not ok:
            sys.exit(1)
        return

    failed = 0
    if args.cmd == "kpi":
        extractor = make_extractor(args)
        for p in args.paths:
            if not process_email(IncomingEmail.load(p), extractor, ideator, judge):
                failed += 1

    elif args.cmd == "ideas":
        for p in args.paths:
            if not continue_from_brief(load_json(p), ideator, judge):
                failed += 1

    else:  # judge
        for p in args.paths:
            ideas = load_json(p)
            brief_path = KPI_DIR / f"{ideas.get('email_id')}.json"
            if not brief_path.exists():
                print(f"!! LLM3 failed for {p}: no brief at {brief_path}", file=sys.stderr)
                failed += 1
            elif not run_judging(judge, load_json(brief_path), ideas):
                failed += 1

    if failed:
        sys.exit(1)# code 1 signal to script or automation tools that something went wrong


if __name__ == "__main__":
    main()

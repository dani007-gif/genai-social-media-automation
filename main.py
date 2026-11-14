"""Social media manager - step 1: email intake.

Usage:
    python main.py gmail [--query "to:posts@yourco.com"] [--max 10] [--mark-processed]
    python main.py eml samples/sample_request.eml

Each email is printed as JSON. The `IncomingEmail` objects are what LLM1 (KPI extraction) will take next.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from email_intake import GmailIntake, load_eml

OUTPUT_DIR = Path("data/intake")


def save(email_obj) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"{email_obj.message_id}.json"
    out.write_text(email_obj.to_json(indent=2))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Step 1: read incoming post-request emails")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gmail", help="fetch unread emails from Gmail")
    g.add_argument("--query", default=os.getenv("GMAIL_QUERY", ""), help="extra Gmail search filter")
    g.add_argument("--max", type=int, default=10)
    g.add_argument("--mark-processed", action="store_true", help="label as smm-processed and mark read")

    e = sub.add_parser("eml", help="parse a local .eml file")
    e.add_argument("path")

    args = ap.parse_args()

    if args.cmd == "gmail":
        intake = GmailIntake(
            credentials_file=os.getenv("GMAIL_CREDENTIALS", "credentials.json"),
            token_file=os.getenv("GMAIL_TOKEN", "token.json"),
        )
        emails = list(intake.fetch_new(query=args.query, max_results=args.max))
        if not emails:
            print("No new emails.")
        for em in emails:
            print(em.to_json(indent=2))
            print(f"-> saved {save(em)}\n")
            if args.mark_processed:
                intake.mark_processed(em.message_id)
    else:
        em = load_eml(args.path)
        print(em.to_json(indent=2))
        print(f"-> saved {save(em)}")


if __name__ == "__main__":
    main()

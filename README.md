# genai-social-media-automation
Email-driven, multi-LLM pipeline that turns a customer’s request into a brand-aligned social media post and publishes it automatically through MCP tool calling. Containerized with Docker and Kubernetes, with CI/CD on GitHub.

# Applied GenAI – Social Media Handling

An end-to-end generative AI system that automates social media posting. A customer sends
an email describing the post they want. A chain of specialised LLM stages extracts the
requirements, brainstorms ideas, picks the best one, writes the post, publishes it via
MCP, and replies to the customer once it is live.

## How it works

1. **Input (email)**: the customer's request arrives by email.
2. **LLM 1, KPI extraction**: the email is parsed into structured requirements:
   - post size / format
   - company name and logo (including logo placement)
   - post theme
   - must-have, nice-to-have and not-to-have elements
   - whether similar posts already exist (for reference)
3. **LLM 2, idea generation**: a strong system prompt takes the KPIs and generates 4–5 post ideas (text).
4. **LLM 3, selection**: the Laya decision model scores each idea against the KPIs, and the code chooses the best one.
5. **LLM 4, post generation**: writes the final post from the selected idea.
6. **MCP tool calling**: the post is published to the company's social media account through an MCP server.
7. **Confirmation**: a reply email is sent to the customer after the post is live.

## Tech stack

- **LLM / VLM**: separate models for extraction, ideation, scoring and generation
- **MCP (Model Context Protocol)**: tool calling to the social media account
- **Docker**: containerized services
- **Kubernetes**: orchestration and deployment
- **Cloud**: hosting
- **CI/CD**: GitHub (Actions) for build, test and deploy

## Key design ideas

- **Multi-stage LLM chain**: each stage has one job, which makes outputs easier to debug and improve.
- **Structured KPIs as the contract** between stages, so generated posts stay on-brief.
- **Generate-then-select**: producing several ideas and scoring them for relevance improves quality over a single-shot post.
- **Human-free loop**: from inbound email to published post to customer confirmation.

## Setup

The project runs on Python 3.12 (macOS's built-in Python is 3.9, which no longer gets security
fixes). `uv` downloads Python 3.12 into your home folder, no admin rights needed:

```bash
python3 -m pip install --user uv
~/Library/Python/3.9/bin/uv venv --python 3.12 --seed .venv
.venv/bin/pip install -r requirements.txt

# test with the sample email (gemma4 reads the logo image and writes the ideas; Laya judges)
.venv/bin/python main.py eml samples/sample_request.eml --judge --backend ollama
```

## LLM 3: judging with Laya

LLM3 always uses [Laya](https://huggingface.co/convaiinnovations/laya); `--backend` and `--model`
only choose the model for LLM1 and LLM2. Laya is a decision model, not a chat model: it answers
typed questions (yes/no, 1-5 score) with probabilities. `judging/laya_judge.py` turns the brief into
those questions (one per must-have, rule and quality criterion) and fills in the verdict from the
answers; `judging/scoring.py` then turns the verdicts into scores and picks the winner.

Laya runs inside `main.py`, in the same `.venv` as the rest of the project: no second terminal, no
server, no port. The `laya` package is in `requirements.txt`, so the Setup step above installs it.

```bash
.venv/bin/python main.py judge data/ideas/sample_request.json
```

The first Laya run downloads the multilingual model from Hugging Face (about 650 MB, into
`~/.cache/huggingface`); later runs read it from disk. The model is loaded once per run and reused
for every idea, and is freed when `main.py` ends. On this Mac, judging 5 ideas takes about 30
seconds and about 1.2 GB of memory.

Safety:
- The version is pinned (`laya==0.4.35`, the tested one) so a later release cannot change answers
  or break the judge without you noticing. Upgrade on purpose and re-test.
- Everything runs on this Mac: after the one-time model download, briefs and ideas are not sent
  anywhere, and nothing listens on the network.
- On an 8 GB Mac, quit Ollama while Laya judges if things slow down.
- `laya` brings PyTorch (about 1 GB in `.venv`). Python only loads it when LLM3 runs, so runs that
  stop after LLM1 or LLM2 stay as fast as before.

Settings: `--judge-model english|multilingual|auto` picks the checkpoint (default `multilingual`,
because a brief plus one idea is longer than the English checkpoint's 512 tokens),
`SMM_LAYA_THRESHOLD` (default 0.5) is the yes/no cut-off.

Length limit: the multilingual checkpoint reads 1024 tokens of brief plus idea. The sample uses
about 600 and a real brief about 830. If a brief and idea are longer, LLM3 stops with a "Laya cut
off ... tokens" error instead of judging half the text (with `--mark-processed`, the email stays
unprocessed).

Optional, only if you ever want Laya on a separate server instead (for example on another
machine): install `"laya[serve]==0.4.35"` there, start it with
`LAYA_HOST=127.0.0.1 LAYA_MODELS=multilingual laya-serve` (by default it listens on `0.0.0.0` with
no password), and set `SMM_LAYA_URL=http://localhost:8000/v1/systemone`. When `SMM_LAYA_URL` is
not set, Laya runs in-process.

Out of the box Laya is close to chance on this kind of decision and over-confident (see its model
card), so check its winners by hand (`needs_review` in the judgement file helps) before relying on
it, and fine-tune it on checked judgements from `data/judgements/`.

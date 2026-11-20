# Progress Report: Social Media Manager, Step 4 (LLM3 Judge with Laya)

**Date and time:** 2026-11-20, 20:59 IST
**Project:** `Projects/Social_media_manager`
**GitHub:** `dani007-gif/genai-social-media-automation` (branch `main`)
**Previous reports:**
- `docs/2026-11-14_14-44_progress_report.md` (step 1, email intake)
- `docs/2026-11-16_19-38_progress_report.md` (step 2, LLM1 KPI extraction)
- `docs/2026-11-17_21-24_progress_report.md` (step 3, LLM2 ideation)

---

## 1. Summary

Step 4 of the pipeline, **LLM3 judge**, is built and runs end to end. It scores every idea from LLM2 against the brief from LLM1 and picks one. **The judge is the Laya decision model** (`convaiinnovations/laya`, multilingual checkpoint). It runs inside `main.py` on this Mac: no server, no API cost, and the data never leaves the computer.

Changes since the last report:

1. **The bug from the last report is fixed.** `main.py` now calls LLM2, and the `ideas` command and `--ideate` work.
2. **The project's Python moved from 3.9 to 3.12.** Laya needs Python 3.10 or newer. The old environment is kept as a backup in `.venv-py39/`.
3. **New package `judging/`** (LLM3). It is built in two layers:
   - Laya answers yes/no and 1–5 questions about each idea.
   - Plain code turns those answers into scores and picks the winner.
4. **LLM3 went through two versions.** A first version used a chat model (gemma4 or llama3.2 through Ollama) as the judge. It was then replaced by Laya, which is now the only judge (section 5).

**Main finding:** the code works, but Laya as shipped does not yet judge well. On the sample email it says, with 91–99% certainty, that every idea breaks the rule "Do not include people's faces", although none shows a person. So all 5 ideas fail the hard rules and every result is marked `needs_review` (section 8). Laya's own model card says it needs fine-tuning for this kind of decision.

None of the changes since commit `fd61022` are committed yet (section 10).

---

## 2. All steps done so far

### 2.1 The planned pipeline

| # | Step | Status |
|---|---|---|
| 1 | Email intake (Gmail API) | **Done** (2026-11-14) |
| 2 | LLM1: KPI extraction into structured JSON, with image analysis | **Done** (2026-11-16) |
| 3 | LLM2: ideation, 4–5 text ideas from the KPIs | **Done** (2026-11-17); command-line bug fixed 2026-11-18 |
| 4 | LLM3: judge, scores each idea against the KPIs and picks one | **Done with Laya** (2026-11-18 to 11-19); quality not yet reliable, see section 8 |
| 5 | LLM4: post generation, caption and image at the requested size | Not started |
| 6 | Approval gate: preview for the customer or reviewer | Not started |
| 7 | MCP tool call: publish | Not started |
| 8 | Reply email with confirmation and post link | Not started |

**Progress:** 4 of 8 steps.

### 2.2 Timeline

| Date | Work | Git commit |
|---|---|---|
| 2026-11-11 to 11-14 | Email intake, Google Cloud and Gmail OAuth set up, first real emails fetched | — |
| 2026-11-14 | Report 1; GitHub repository created and connected | `156a9c2`, `bcafba8`, `ed8f76f`, `d04d611` |
| 2026-11-16 | LLM1 on Claude, then switched to Ollama `gemma4:e2b-it-qat` because the API is costly; report 2 | `b8c1cd9` |
| 2026-11-17 | LLM2 ideation, shared `llm_backends.py`; report 3 | `484568f`, `fd61022` |
| 2026-11-18 | `main.py` bug fixed. LLM3 first version with a chat-model judge (gemma4, then `llama3.2:3b`). Quote checks and the caption rule added. Environment rebuilt on Python 3.12 with `uv`; `laya` installed | not committed |
| 2026-11-19 | Laya made the only LLM3 judge (`judging/laya_judge.py`); README updated with setup and Laya notes | not committed |
| 2026-11-20 | Laya judge re-run on the sample email for this report | — |

### 2.3 Data flow

```
Gmail / .eml file
      │  step 1: email_intake/
      ▼
data/intake/<email id>.json        (+ data/attachments/<email id>/)
      │  step 2: kpi_extraction/   (LLM1: gemma4 via Ollama, or Claude; reads text and images)
      ▼
data/kpis/<email id>.json          (the brief, PostKPIs)
      │  step 3: ideation/         (LLM2: gemma4 via Ollama, or Claude; text only)
      ▼
data/ideas/<email id>.json         (4–5 ideas)
      │  step 4: judging/          (LLM3: Laya, on this Mac; then plain-code scoring)
      ▼
data/judgements/<email id>.json    (scores, reasons, ranking, winner, needs_review)
```

`data/` is in `.gitignore`.

---

## 3. File-by-file comparison with the previous reports

**Added** means new. **Updated** means it existed and changed. **Removed** means deleted.

### 3.1 Earlier steps (already described in reports 1–3)

| Step | Files | Commit |
|---|---|---|
| 1 Email intake | `email_intake/` (models, parser, gmail_client, eml_loader), `samples/sample_request.eml`, `main.py`, `requirements.txt`, `.gitignore` | `ed8f76f` |
| 2 LLM1 | `kpi_extraction/` (schema, prompts, extractor, ollama_extractor); updates to `email_intake/models.py`, `main.py`, `requirements.txt`, `.gitignore` | `b8c1cd9` |
| 3 LLM2 | `llm_backends.py`, `ideation/` (schema, prompts, ideator); updates to `main.py`, `kpi_extraction/extractor.py`, `.gitignore` | `484568f` |
| Docs | the three earlier reports | `ed8f76f`, `b8c1cd9`, `fd61022` |

Not changed since report 3: everything in `email_intake/` and `kpi_extraction/`, plus `ideation/schema.py` and `ideation/ideator.py`.

### 3.2 Changes since report 3 (step 4 and setup)

Listed in the order they depend on each other, which is also a sensible order for reading them.

| # | File | Change | Why |
|---|---|---|---|
| 1 | `judging/schema.py` | **Added** | The shape of one verdict (`IdeaVerdict`: must-have checks, not-to-have checks, invented claims, four 1–5 scores, summary) and of the saved result (`IdeaJudgement`, `Decision`). Scores can only be 1–5 |
| 2 | `judging/scoring.py` | **Added** | Plain code with no model. It runs checks of its own (every must-have has a placement; text placed "on the image" really is in `on_image_text`). It checks quotes: a rule break or invented claim only counts if its text is really in the idea. It applies the caption rule, the weights and the penalties, then picks the winner. The same verdicts always give the same winner |
| 3 | `judging/laya_judge.py` | **Added** | Turns the brief into typed questions for Laya and Laya's answers into an `IdeaVerdict` (section 5.3) |
| 4 | `judging/judge.py`, `judging/__init__.py` | **Added** | `Judge` class: loads the brief and the ideas, checks they belong together, judges one idea at a time with Laya, then calls `scoring.py` and saves `data/judgements/<id>.json` |
| — | `judging/prompts.py` | Added on 2026-11-18, **removed** on 2026-11-19 | The written reviewer prompt for the chat-model judge. Laya takes no prompt, so it was no longer used. Its 1–5 scale texts now live in `SCALES` in `laya_judge.py` |
| 5 | `ideation/prompts.py` | **Updated** | New `clean_brief()`, so LLM2 and LLM3 read the brief the same way (no empty fields, no `"null"` words), without copied code |
| 6 | `llm_backends.py` | **Updated** | New `ask_laya()`, which runs Laya inside this process, or on a `laya-serve` server if `SMM_LAYA_URL` is set. The model loads once per run and is reused for every idea. Also: if a model without "thinking" (for example llama3.2) rejects that setting, Ollama is asked once more without it |
| 7 | `main.py` | **Updated** | Fixes the bug from report 3: `ideas` and `--ideate` work again. Adds the `judge` command, `--judge` on `gmail`, `eml`, `kpi` and `ideas`, and `--judge-model multilingual|english|auto`. `--judge` includes LLM1 and LLM2, and with `--mark-processed` an email is marked only if every step succeeded. `eml` now exits with code 1 if a step fails. `--backend` and `--model` now apply to LLM1 and LLM2 only |
| 8 | `requirements.txt` | **Updated** | Added `laya==0.4.35`, pinned so a new release cannot change the judge's answers unnoticed (it brings PyTorch, about 1 GB). `anthropic` stays below 1.0, because the code uses the 0.x call `beta.messages.parse(output_format=...)` |
| 9 | `.gitignore` | **Updated** | Added `.venv-py39/`, the Python 3.9 backup environment |
| 10 | `README.md` | **Updated** | Step 4 now names Laya. New "Setup" section (Python 3.12 with `uv`) and "LLM 3: judging with Laya" section (how it runs, memory, safety, settings, the 1024-token limit, the optional server) |
| 11 | `docs/2026-11-20_20-59_progress_report.md` | **Added** | This report |

### 3.3 Changes outside the code

| Change | Detail | Why |
|---|---|---|
| New Python environment | `.venv` rebuilt on **Python 3.12.16** with `uv` (installed with `pip install --user uv`; it lives in `~/Library/Python/3.9/bin/uv`). Old 3.9 environment kept as `.venv-py39/` | `laya` needs Python 3.10 or newer, and macOS's own Python 3.9 no longer gets security fixes. `uv` installs Python 3.12 in the home folder, without admin rights |
| Installed packages | `laya 0.4.35`, `torch 2.15.0`, `transformers 5.23.0`, `anthropic 0.125.0`, `pydantic 2.14.3`. `.venv` is now 1.1 GB (the 3.9 one was 148 MB) | Laya runs on PyTorch |
| Laya model files | Multilingual checkpoint downloaded once into `~/.cache/huggingface/hub` (647 MB) | Later runs read it from disk, with no download |
| Ollama models | `llama3.2:3b` (2.0 GB) downloaded on 2026-11-18 for the chat-model judge test. **No longer used** since Laya became the judge. `gemma4:e2b-it-qat` is still used for LLM1 and LLM2 | Remove with `ollama rm llama3.2:3b` if the disk space is needed |

---

## 4. What LLM3 does

1. Reads the ideas (`data/ideas/<id>.json`) and the brief for the same email (`data/kpis/<id>.json`).
2. Checks both files: same email, a real post request, 4–5 valid ideas.
3. Judges **one idea at a time**. This keeps each input inside Laya's 1,024-token window and stops the judge from favouring an idea because of where it sits in a list.
4. For each idea, Laya answers typed questions. The answers are turned into an `IdeaVerdict`.
5. `scoring.py` applies the hard rules, weights and penalties, ranks the ideas and picks a winner.
6. Saves everything to `data/judgements/<id>.json`, including `needs_review` and the reasons a person should look.

### 4.1 Scoring rules (`judging/scoring.py`)

| Part | Rule |
|---|---|
| Hard rules | Every must-have included (must-have check, plus a code check that `must_have_placement` has an entry for it). No not-to-have broken. An idea that breaks a hard rule ranks below all ideas that pass |
| Caption rule | A must-have placed "in the caption" counts as included, because LLM4 writes the full caption later |
| Quote check | A rule break or invented claim only counts if its quoted text really appears in the idea. An "invented" claim is dropped if the brief contains the same words |
| Quality score | relevance 40%, audience and tone 25%, format fit 20%, clarity 15%. All 1s = 0, all 5s = 100 |
| Penalty | 10 points per problem: each invented claim, or text placed "on the image" while `on_image_text` is empty |
| Winner | Passes the hard rules first, then highest final score. Ties: fewer problems, then higher relevance, then lower idea number |
| `needs_review` | Set when no idea passed the hard rules, when the winner has problems, or on a close call (the runner-up is less than 5 points behind) |

---

## 5. How the judge changed: chat model, then Laya

### 5.1 First version: a chat model as the judge (2026-11-18)

A written reviewer prompt (`judging/prompts.py`) asked a chat model, through `ask_ollama` or `ask_claude`, to fill the `IdeaVerdict` with a written reason for each score. Results on the sample email:

| Judge model | What happened |
|---|---|
| `gemma4:e2b-it-qat` (the model that also wrote the ideas) | Gave almost every idea 5/5 on every criterion, so the winner came from a tie-break. Without quote checks, it said all 4 ideas broke "no faces", though none showed a person |
| `llama3.2:3b` | Separated the ideas well (70, 52.5, 41.2, 30 out of 100) and gave the same scores on two runs. Found the invented "pre-order" claim. Mistakes: it called "officially launched" an invented fact, and failed an idea whose price was placed in the caption |

These tests led to two code rules that are still in `scoring.py`: the **quote check** and the **caption rule**.

### 5.2 Why Laya

The user chose Laya as the decision model for LLM3. It is built for typed decisions, runs locally on a small machine, and is Apache-2.0 licensed. It needed the Python 3.12 environment (section 3.3).

### 5.3 How Laya is used (`judging/laya_judge.py`)

Laya does not write text. It answers typed questions about a "state" with probabilities. So each part of the verdict becomes questions about one idea:

| Verdict part | Question type | Questions per idea (sample) |
|---|---|---|
| Each must-have | yes/no: "does the idea clearly include it?" | 2 |
| Each not-to-have | yes/no for each field (`visual`, `on_image_text`, `caption_hook`, `call_to_action`): "does this field break the rule?" | 3–4 |
| Invented facts | yes/no for each audience-facing field: "does it claim a fact the brief does not state?" | 2–3 |
| Relevance, audience and tone, format fit, clarity | score on a 5-level scale (the same descriptions as the old prompt) | 4 |

The answers become the verdict like this:
- **yes/no:** "yes" from probability 0.5 (`SMM_LAYA_THRESHOLD`).
- **Not-to-have:** the field most likely to break the rule decides.
- **Scores:** Laya's expected level, rounded to a whole number from 1 to 5.
- **Quotes:** Laya cannot quote, so the quote is the whole field the question was about. This keeps the quote checks in `scoring.py` working.
- **Summary:** built by the code ("strongest on …, weakest on …").

The state sent to Laya is the cleaned brief plus only the parts of the idea it needs (`title`, `concept`, `visual`, `on_image_text`, `caption_hook`, `call_to_action`, `must_have_placement`).

### 5.4 Settings

| Setting | Default | Meaning |
|---|---|---|
| `--judge-model` / `SMM_LAYA_MODEL` | `multilingual` | Laya checkpoint: `multilingual` (reads 1,024 tokens), `english` (512 tokens, too short for brief + idea), or `auto` (Laya picks one from the language) |
| `SMM_LAYA_THRESHOLD` | `0.5` | Probability from which a yes/no answer counts as "yes" |
| `SMM_LAYA_URL` | not set | Only to use a separate `laya-serve` server instead of running in-process |
| `SMM_LAYA_API_KEY` | not set | Password for that server, if it has one |

If Laya has to cut the brief and idea to fit its window, LLM3 stops with a "Laya cut off … tokens" error instead of judging half the text. With `--mark-processed`, that email stays unprocessed.

---

## 6. Order of execution

```
python main.py judge data/ideas/sample_request.json
   │
main.py          reads the ideas file, finds data/kpis/<same email id>.json
   │             make_judge(): Judge(model="multilingual")
   ▼
judge.py         checks both files (same email? post request? 4–5 ideas?)
   │             clean_brief() from ideation/prompts.py
   ▼  for each idea:
laya_judge.py    builds the yes/no and score questions
llm_backends.py  ask_laya(): loads Laya once (first idea only), answers all questions in one call
laya_judge.py    answers → IdeaVerdict (stops if the input was cut off)
scoring.py       code checks, quote checks, caption rule, weights, penalty → IdeaJudgement
main.py          prints "idea n (title): score/100 [ok / FAILS HARD RULES]"
   ▼  after all ideas:
scoring.py       decide(): ranking, winner, needs_review reasons
judge.py         saves data/judgements/<id>.json
main.py          prints the winner and the review reasons
```

In a full run (`gmail --judge` or `eml --judge`), this follows LLM1 and LLM2. Each option includes the steps before it: `--judge` also runs LLM2, and `--ideate` also runs LLM1. PyTorch is only loaded when LLM3 runs, so runs that stop after LLM1 or LLM2 are as fast as before.

---

## 7. How to run

Setup, once (from `README.md`):

```
python3 -m pip install --user uv
~/Library/Python/3.9/bin/uv venv --python 3.12 --seed .venv
.venv/bin/pip install -r requirements.txt
```

Runs (keep the Ollama app open for LLM1 and LLM2):

```
# LLM3 only, on ideas already saved
.venv/bin/python main.py judge data/ideas/sample_request.json

# LLM2 + LLM3 on a saved brief
.venv/bin/python main.py ideas data/kpis/sample_request.json --judge --backend ollama

# Sample email: all steps 1 to 4
.venv/bin/python main.py eml samples/sample_request.eml --judge --backend ollama

# Gmail: all steps, mark an email processed only if every step succeeded
.venv/bin/python main.py gmail --max 5 --judge --backend ollama --mark-processed
```

On an 8 GB Mac, quit Ollama while Laya judges if things slow down.

---

## 8. Test results (data)

Run on 2026-11-20 with `main.py judge data/ideas/sample_request.json`: the sample email (Acme Coffee, Pumpkin Spice Latte), 5 ideas written by gemma4, judged by Laya `multilingual`.

### 8.1 Speed and size

| Measure | Value |
|---|---|
| Time for 5 ideas, including loading Laya | 19.1 s |
| Peak memory | 1.21 GB |
| Input per idea (brief + idea) | 586–624 tokens of the 1,024 allowed; nothing cut off |
| Tokens counted for the run | 43,548 in, 0 out (Laya writes no text) |
| Repeatability | Same scores and winner as the saved run of 2026-11-18 |

### 8.2 Scores

| Idea | Title | Quality (0–100) | Penalty | Final | Hard rules |
|---|---|---|---|---|---|
| 5 | Quick & Exciting Launch Announcement | 68.8 | 30 | **38.8** | fails ("no faces") |
| 4 | Autumn Mood Aesthetic | 53.8 | 20 | 33.8 | fails ("no faces") |
| 2 | Vibrant Autumn Harvest Scene | 53.8 | 30 | 23.8 | fails ("no faces") |
| 1 | Cozy Autumn Morning Vibe | 47.5 | 30 | 17.5 | fails ("no faces") |
| 3 | Latte Focus & Texture Close-up | 43.8 | 30 | 13.8 | fails ("no faces") |

**Winner: idea 5. Ranking: 5, 4, 2, 1, 3. `needs_review`: true**, because no idea passed the hard rules and the winner has 3 flagged claims.

The 1–5 scores came out as 2, 3 or 4, with Laya's confidence between 0.01 and 0.24 (low). Both must-haves were found in every idea (p = 0.96–0.99), which is correct.

### 8.3 Laya's raw yes/no answers

Probability of "yes" for each question:

| Idea | "Breaks 'no faces'?" (per field) | "Claims a fact not in the brief?" (per field) |
|---|---|---|
| 1 | 0.94–0.98 | 0.92–0.93 |
| 2 | 0.95–0.98 | 0.82–0.84 |
| 3 | 0.91–0.96 | 0.63–0.72 |
| 4 | 0.97–0.99 | 0.90–0.94 |
| 5 | 0.98–0.99 | 0.91 |

**What this shows:** Laya says "yes" to almost every yes/no question, whatever the text. For example, it says the on-image text "NEW! Pumpkin Spice Latte - 4.50 EUR" breaks "no faces" and claims something the brief does not state, although the brief asks for exactly that price. So these answers do not tell good ideas from bad ones yet.

Two consequences:
- **The ranking mostly follows the penalties.** Idea 4 has no on-image text, so it had one question fewer to fail and lost 20 points instead of 30.
- **A few flags are right.** "pre-order", "Link in bio" and "Find us in stores starting this week" are real claims the brief does not make. But Laya flags correct text just as strongly, so these flags can't be trusted on their own.

### 8.4 Other checks

- Error cases give clear messages and exit code 1: no matching brief, ideas from a different email, a brief that is not a post request. These were tested on 2026-11-18; the code for them has not changed since. The "too long for Laya" error is in the code, but has not been triggered in a test.
- `--judge-model` accepts only Laya checkpoints. An Ollama model name is rejected before anything loads.
- The full chain LLM1 → LLM2 → LLM3 ran on 2026-11-18 (with the chat-model judge, about 1.5 minutes). With Laya, LLM3 adds about 20 seconds.
- **Not tested:** a real Claude API call for LLM1 or LLM2 (no `ANTHROPIC_API_KEY` on this machine), and `laya-serve` server mode (`SMM_LAYA_URL`).

---

## 9. Known gaps and risks

- **Laya is not a reliable judge yet.** As section 8.3 shows, its yes/no answers are close to constant without fine-tuning. Every winner needs a person to check it. Laya's model card says the same: base checkpoints are near chance on typed decisions, score questions are its weakest type, and its probabilities are over-confident.
- **Every idea fails the hard rules** on the sample email, because of the false "no faces" answers. The hard-rule ranking therefore has no effect, and the winner comes from scores and penalties alone.
- **Correct text gets penalised.** The required price "4.50 EUR" is flagged as invented. The quote check can't drop it, because the quote is the whole field, not just the words from the brief.
- **Length limit.** Brief plus idea must fit in 1,024 tokens. The sample uses about 600 and a real brief about 830, so a long brief will stop LLM3 with an error.
- **Size.** `laya` brings PyTorch: `.venv` grew from 148 MB to 1.1 GB, plus 647 MB of model files.
- **Unused files.** `llama3.2:3b` (2 GB) is no longer used. `.venv-py39/` is only a backup.
- **Still open from earlier reports:**
  - The default backend for LLM1 and LLM2 is still `claude`, so always add `--backend ollama`.
  - Small-model quality issues in LLM1 and LLM2.
  - No automated tests, no scheduler, the Google token expires every 7 days in Testing mode.
  - `anthropic` is still pinned below 1.0.
- **Uncommitted work.** Everything in section 3.2 is not in git yet.

---

## 10. Suggested next steps

1. **Commit and push** the current work:
   ```
   git add .
   git status     # expect judging/, llm_backends.py, main.py, ideation/prompts.py,
                  # requirements.txt, .gitignore, README.md, this report; no .venv-py39/ or data/
   git commit -m "Add LLM3 judge with Laya, Python 3.12 setup"
   git pull origin main --no-rebase
   git push
   ```
2. **Make Laya's answers useful.**
   - Check by hand which ideas really break a rule or invent a claim, and save those labels next to `data/judgements/`.
   - Fine-tune Laya on them, as its model card suggests (its Kaggle notebook).
   - Until then, consider raising `SMM_LAYA_THRESHOLD`, or rewording the yes/no questions as two-option "choice" questions, as the model card recommends.
3. **Make the price check smarter.** Before flagging a field, remove the facts the brief already gives (price, product name), so a correct price is not counted as invented.
4. Build **LLM4, post generation**, from the winner in `data/judgements/<id>.json` (it holds a full copy of the winning idea).
5. Still open from earlier: make `ollama` the default backend, add automated tests, and add a scheduler.

# Progress Report: Social Media Manager, Step 3 (LLM2 Ideation)

**Date and time:** 2026-11-17, 21:24 IST
**Project:** `Projects/Social_media_manager`
**GitHub:** `dani007-gif/genai-social-media-automation` (branch `main`)
**Previous reports:**
- `docs/2026-11-14_14-44_progress_report.md` (step 1, email intake)
- `docs/2026-11-16_19-38_progress_report.md` (step 2, LLM1 KPI extraction)

---

## 1. Summary

Step 3 of the pipeline, **LLM2 ideation**, is built and tested on the local Ollama model. It reads the brief made by LLM1 and writes **4 or 5 different text ideas** for the post. LLM3, the judge, will score these ideas and pick one.

This report covers:
- all the work done so far, steps 1 to 3 (section 2)
- every file in the project, compared with the previous reports: when it was added, when it changed, and why (section 3)
- the new ideation step in detail (sections 4 to 7)

All the work is committed and pushed to GitHub. The latest commit is `484568f`. **That commit has one known bug:** the end of `main.py` does not yet call LLM2, so the `ideas` command and the `--ideate` option do not work from the command line. See section 9.

---

## 2. All steps done so far

### 2.1 The planned pipeline

| # | Step | Status |
|---|---|---|
| 1 | Email intake (Gmail API) | **Done** (2026-11-14) |
| 2 | LLM1: KPI extraction into structured JSON, with image analysis | **Done** (2026-11-16) |
| 3 | LLM2: ideation, 4–5 text ideas from the KPIs | **Done**: code and tests (2026-11-17). `main.py` wiring has a bug, see section 9 |
| 4 | LLM3: judge, scores each idea against the KPIs and picks one | Not started |
| 5 | LLM4: post generation, caption and image at the requested size | Not started |
| 6 | Approval gate: preview for the customer or reviewer | Not started |
| 7 | MCP tool call: publish | Not started |
| 8 | Reply email with confirmation and post link | Not started |

**Progress:** 3 of 8 steps.

### 2.2 Timeline

| Date | Work | Git commit |
|---|---|---|
| 2026-11-11 to 11-14 | Built email intake. Set up Google Cloud, the Gmail API and OAuth, and fixed the `403 access_denied` error by adding a test user. Fetched real emails. | — |
| 2026-11-14 | Wrote report 1. Created the GitHub repository (README, initial commit). Connected the local folder and merged the GitHub history into it (`--allow-unrelated-histories`). | `156a9c2`, `bcafba8`, `ed8f76f`, `d04d611` |
| 2026-11-16 | Built LLM1 on the Claude API first, then switched to Ollama (`gemma4:e2b-it-qat`) because the API is costly. Ran it on Gmail. Wrote report 2. | `b8c1cd9` |
| 2026-11-17 | Built LLM2 with a shared Claude/Ollama module. Fixed the "no API key" crash in LLM1. Tested on Ollama. | `484568f` |

### 2.3 Data flow so far

```
Gmail / .eml file
      │  step 1: email_intake/
      ▼
data/intake/<email id>.json        (+ data/attachments/<email id>/)
      │  step 2: kpi_extraction/   (LLM1, reads text and images)
      ▼
data/kpis/<email id>.json          (the brief, PostKPIs)
      │  step 3: ideation/         (LLM2, text only)
      ▼
data/ideas/<email id>.json         (4–5 ideas, for LLM3)
```

`data/` is in `.gitignore`, because it holds real emails.

---

## 3. File-by-file comparison with the previous reports

**Added** means the file is new. **Updated** means it existed and was changed.

### 3.1 Step 1: email intake (report 1, commit `ed8f76f`)

| File | Change | Why |
|---|---|---|
| `email_intake/models.py` | Added | Holds the `IncomingEmail` and `Attachment` data classes, the format every later step reads |
| `email_intake/parser.py` | Added | Turns a raw email into an `IncomingEmail`: converts HTML to text, removes quoted replies, saves attachments |
| `email_intake/gmail_client.py` | Added | Gmail login, search for new emails, download, and the `smm-processed` label |
| `email_intake/eml_loader.py` | Added | Lets the pipeline run on a local `.eml` file without Gmail |
| `email_intake/__init__.py` | Added | Makes the folder a package and exports the main classes |
| `samples/sample_request.eml` | Added | A made-up post request (Acme Coffee, Pumpkin Spice Latte), used for all tests so real emails are never needed |
| `main.py` | Added | Command line: `gmail` and `eml` commands |
| `requirements.txt` | Added | Google API libraries |
| `.gitignore` | Added | Keeps `credentials.json`, `token.json`, `data/`, `.venv/`, `.env` and `__pycache__/` out of git |
| `docs/2026-11-14_14-44_progress_report.md` | Added | Report 1 |

### 3.2 Step 2: LLM1 KPI extraction (report 2, commit `b8c1cd9`)

| File | Change | Why |
|---|---|---|
| `kpi_extraction/schema.py` | Added | `PostKPIs`, the exact shape of the brief, so the model cannot answer in free text |
| `kpi_extraction/prompts.py` | Added | LLM1 system prompt; the email is wrapped in `<email>` tags and treated as data, not instructions |
| `kpi_extraction/extractor.py` | Added | The Claude version of LLM1, sending images and text in one call. Also holds the shared `KPIResult`, `ExtractionError` and image checks |
| `kpi_extraction/ollama_extractor.py` | Added | The Ollama version of LLM1, free and local, because the Claude API is costly |
| `kpi_extraction/__init__.py` | Added | Exports the LLM1 classes |
| `email_intake/models.py` | Updated | Added `from_dict()` and `load()`, so LLM1 can reread saved emails without fetching Gmail again |
| `main.py` | Updated | Added the `kpi` command, `--extract`, and `--backend/--model/--effort`. `--mark-processed` now waits for LLM1 to succeed |
| `requirements.txt` | Updated | Added `anthropic>=0.125,<1` (the 0.x line, for Python 3.9) and `pydantic>=2.5` |
| `.gitignore` | Updated | Added the two personal PDF notes |
| `docs/2026-11-16_19-38_progress_report.md` | Added | Report 2 |

### 3.3 Step 3: LLM2 ideation (this report, commit `484568f`)

| File | Change | Why |
|---|---|---|
| `llm_backends.py` | **Added** | One shared way to ask Claude or Ollama for an answer in a fixed JSON shape (`ask_claude`, `ask_ollama`). LLM2 uses it now, and LLM3 and LLM4 can reuse it, so the API code is not copied three times. It has the same Ollama settings as LLM1, so Ollama does not reload the model between steps |
| `ideation/schema.py` | **Added** | `PostIdea` and `IdeaSet`, the shape of one idea and the rule "4 to 5 ideas" |
| `ideation/prompts.py` | **Added** | LLM2 system prompt, plus `build_user_text()`, which cleans the brief before sending it |
| `ideation/ideator.py` | **Added** | `Ideator`: checks the brief, calls the chosen backend, numbers the ideas and saves them. `IdeaResult` and `IdeationError` are also here |
| `ideation/__init__.py` | **Added** | Exports the LLM2 classes |
| `main.py` | **Updated** | Added `run_ideation()`, `process_email()`, `make_ideator()`, the `--count` option, the `ideas` command and `--ideate`. `run_extraction()` now returns the brief instead of `True`/`False`, so LLM2 can use it directly. **The last part, the code that calls these, is missing; see section 9** |
| `kpi_extraction/extractor.py` | **Updated** | With `--backend claude` and no API key, LLM1 crashed with a long Python traceback. It now prints: *"No Anthropic API key found. Set ANTHROPIC_API_KEY, or add --backend ollama to use the local model."* |
| `.gitignore` | **Updated** | Added `personal_understanding`, so the whole personal-notes folder stays private |
| `docs/2026-11-17_21-24_progress_report.md` | **Added** | This report |

Files **not** changed in step 3: everything in `email_intake/`, `kpi_extraction/schema.py`, `kpi_extraction/prompts.py`, `kpi_extraction/ollama_extractor.py` and `requirements.txt`. LLM2 needs no new package.

---

## 4. What LLM2 does

1. Reads one brief from `data/kpis/<email id>.json`.
2. If `is_post_request` is false, it skips the brief and does not call a model.
3. Sends the brief to the model (Ollama or Claude) with a creative-lead system prompt.
4. Gets back 4 or 5 ideas in a fixed JSON shape, checked by Pydantic.
5. Saves them to `data/ideas/<email id>.json`.

It is **text only**. No images are sent, because LLM1 already described them in the brief. No images are created; that is LLM4's job.

### 4.1 One idea (`PostIdea`)

| Field | Meaning |
|---|---|
| `idea_id` | 1, 2, 3… |
| `title` | Short working name |
| `angle` | What makes this idea different from the others |
| `concept` | 2–3 sentences: what the post says and why it serves the objective |
| `must_have_placement` | One entry per must-have: the requirement, and where it goes (in the image, in the on-image text, or in the caption) |
| `visual` | What the image shows: subject, setting, colours, layout, and where the logo and text sit |
| `on_image_text` | All text written on the image, or `null` |
| `caption_hook` | First line of the caption |
| `call_to_action` | What the audience should do, or `null` |
| `nice_to_haves_used` | Nice-to-have items this idea uses |
| `assumptions` | Choices the brief did not specify, for the customer to confirm |

`must_have_placement` is placed **before** `visual` on purpose. The model writes fields in order, so it first decides where each requirement goes, then describes an image that shows it.

### 4.2 Output file

`data/ideas/<email id>.json` contains `email_id`, `subject`, `backend`, `model`, `generated_at`, `usage` (tokens in and out) and `ideas`.

---

## 5. The prompt (`ideation/prompts.py`)

The model is told it is the agency's creative lead. The brief is inside `<brief>` tags and is treated as data, not instructions. The five rules:

1. **Follow the brief.** Every idea has every must-have and nothing from not-to-have. Nice-to-haves are optional.
2. **Really different ideas.** They can differ in what the image is built around (the product, a scene from the audience's life, mostly text), in the feeling, and in how they speak to the audience.
3. **Fit the platform, format and size.** Text on the image must be readable on a phone.
4. **Only facts from the brief.** No invented prices, dates, discounts or claims. Open choices go in `assumptions`.
5. **Match the brand.** Follow tone, audience and colours, and keep the logo spot free.

Customer-facing text (`on_image_text`, `caption_hook`, `call_to_action`) is written in the post's language. Everything else is in English for the team.

Before sending, `build_user_text()` removes empty fields and placeholder words (`"null"`, `"none"`, `"n/a"`) from the brief. The local LLM1 model writes these (report 2, section 10), and they confused LLM2.

---

## 6. Backends and settings

| | Ollama (local) | Claude API |
|---|---|---|
| Option | `--backend ollama` | `--backend claude` (default) |
| Model | `gemma4:e2b-it-qat` | `claude-opus-5-5`, effort `medium` |
| Cost | Free | Paid per call |
| Temperature | 0.8: ideas should vary (LLM1 uses 0) | Not set (the API default) |

| Environment variable | Default | Meaning |
|---|---|---|
| `SMM_LLM2_MODEL` | `claude-opus-5-5` | Claude model for LLM2 |
| `SMM_LLM2_EFFORT` | `medium` | Claude effort for LLM2 |
| `SMM_LLM2_TEMPERATURE` | `0.8` | Ollama temperature for LLM2 |
| `SMM_OLLAMA_MODEL`, `SMM_OLLAMA_NUM_CTX`, `SMM_OLLAMA_URL` | as in report 2 | Shared with LLM1 |

New command-line option: `--count 4` or `--count 5` (default 5).

---

## 7. Changes made during testing

Two problems from the first test runs were fixed before the commit:

| Problem seen | Fix |
|---|---|
| All 5 ideas listed the price as "covered", but only 1 actually put it anywhere in the post | Replaced the yes/no list with `must_have_placement`, which names a place for each requirement, and moved it before `visual`. After the fix, 4 of 5 ideas put the price in the on-image text and the fifth put it in the caption |
| The small model copied the example angles from the prompt as idea titles | Rule 2 now describes ways ideas can differ instead of listing ready-made angles |

---

## 8. Test results

All tests used the made-up sample email. Real Gmail emails were not sent to any API.

| Test | Result |
|---|---|
| LLM2 on `data/kpis/sample_request.json`, Ollama, 5 ideas | 5 valid ideas in about 1 minute; 2,075 tokens in, 1,706 out |
| LLM1 then LLM2 chained, Ollama, `--count 4` | 4 valid ideas in about 53 s: "Cozy Autumn Pour", "Seasonal Ingredient Showcase", "Aesthetic Autumn Vibe", "The Launch Reveal" |
| Brief that is not a post request | Skipped, no model call |
| Ollama not running | Clear error message |
| Only 3 ideas returned, or `count=7` | Rejected |
| Malformed brief | Rejected with `IdeationError` |
| Claude backend with a fake client | Correct request: model, `max_tokens` 16000, effort, fallback setting. A refusal gives a clear error |
| Claude backend with no API key (LLM1 and LLM2) | Clear message instead of a traceback |

**Not tested:** a real Claude API call, for LLM1 or LLM2, because no `ANTHROPIC_API_KEY` is set on this machine.

**Test status after the commit:** the tests above were run with the full `main.py`. The committed `main.py` is missing its last part (section 9), so `python main.py ideas …` and `--ideate` fail at the moment. The `ideation/` code itself is unchanged and works.

---

## 9. Known gaps and risks

- **Bug in the committed `main.py`.** The ideation helpers and options are in the file, but the `main()` section at the bottom is still the step-2 version. As a result:
  - `python main.py ideas data/kpis/sample_request.json` is handled as the `kpi` command and crashes with `KeyError: 'message_id'`, because it tries to read a brief as an email.
  - `--ideate` is accepted on `gmail`, `eml` and `kpi` but does nothing.

  Fix: change the end of `main()` so that the `gmail`, `eml` and `kpi` branches call `process_email(em, extractor, ideator)` when `--ideate` is given, and add an `ideas` branch that reads each brief JSON and calls `run_ideation()`. Then commit and push.
- **Quality of the small model.** Seen in the tests:
  - One idea described large text on the image but left `on_image_text` empty.
  - Placements are short ("in the image") instead of saying where in the image.
  - Small invented details in calls to action ("pre-order", "before they sell out"), which breaks rule 4.

  LLM3 (the judge) should catch these. Until then, a person should read the ideas.
- **Slow.** About 1 minute per brief on this Mac, plus about 20–70 s for LLM1.
- **The default backend is still Claude.** Forgetting `--backend ollama` sends data to the paid API, or fails without a key.
- **LLM2 depends on LLM1 quality.** Mistakes in the brief, such as invented `image_analysis` entries (report 2), pass straight into the ideas.
- **Results overwrite each other.** A new run replaces `data/ideas/<email id>.json`.
- **Still open from earlier reports:** no automated tests, no scheduler, Google token expiry in Testing mode, the 500-email cap on `--max`, and the Ollama path still needing the `anthropic` package.

---

## 10. How to run (once the `main.py` fix is in)

Keep the Ollama app open.

```
# LLM2 only, on a brief already saved by LLM1
python main.py ideas data/kpis/sample_request.json --backend ollama

# LLM1 + LLM2 on a saved email, 4 ideas
python main.py kpi data/intake/sample_request.json --ideate --backend ollama --count 4

# Sample .eml file: steps 1 to 3
python main.py eml samples/sample_request.eml --ideate --backend ollama

# Gmail: steps 1 to 3, mark an email processed only if every step succeeded
python main.py gmail --max 5 --ideate --backend ollama --mark-processed
```

---

## 11. Suggested next steps

1. Fix the end of `main()` in `main.py` (section 9), test `python main.py ideas …`, then commit and push.
2. Build **LLM3, the judge**. It reads `data/kpis/<id>.json` and `data/ideas/<id>.json`, scores each idea against the brief (must-haves placed, nothing from not-to-have, no invented facts, fits the format, brand fit), and saves the chosen idea with its reasons. It can reuse `llm_backends.py`.
3. Make `ollama` the default backend, or read it from an environment variable.
4. Add simple code checks after LLM2: every must-have has a placement, and anything placed "in the on-image text" really appears in `on_image_text`.
5. Write a few automated tests on the sample email for LLM1 and LLM2, using a fake model answer so they run quickly and for free.
6. Still open from earlier: the scheduler, and moving the shared LLM1 parts out of `extractor.py`.

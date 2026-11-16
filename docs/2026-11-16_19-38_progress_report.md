# Progress Report: Social Media Manager, Step 2 (LLM1 KPI Extraction)

**Date and time:** 2026-11-16, 19:38 IST
**Project:** `Projects/Social_media_manager`
**Previous report:** `docs/2026-11-14_14-44_progress_report.md` (step 1, email intake)

---

## 1. Summary

Step 2 of the pipeline, **LLM1 KPI extraction**, is built and working end to end. It takes an email saved by step 1 and turns it into a structured post brief (`PostKPIs`) that a designer and a copywriter can work from. Text extraction and image analysis happen in **one model call**: the images from the email are sent with the text to a vision-language model.

The step was first written for the Claude API (model `claude-opus-5-5`). **Since the Claude API is costly, we changed it to Ollama with the model `gemma4:e2b-it-qat`, so that it runs free on localhost.** The Claude version is still in the code and can be chosen with `--backend claude`.

Changes since the last report:

- New package `kpi_extraction/` (schema, prompt, Claude extractor, Ollama extractor).
- `email_intake/models.py`: emails saved in `data/intake/` can now be loaded back.
- `main.py`: new `kpi` command, `--extract` on `gmail` and `eml`, and a `--backend` choice between Claude and Ollama.
- `requirements.txt` and `.gitignore` updated.

None of these changes are committed to git yet.

---

## 2. Changes in `email_intake/models.py`

Two class methods were added to `IncomingEmail`, so step 2 can run on emails already saved by step 1 without fetching them from Gmail again.

| Method | What it does |
|---|---|
| `IncomingEmail.from_dict(d)` | Rebuilds an `IncomingEmail` (with its `Attachment` objects) from the saved JSON. Ignores keys that are calculated, not stored, such as `needs_vision` and `is_image`. |
| `IncomingEmail.load(path)` | Opens a JSON file from `data/intake/` and returns the `IncomingEmail`. Used by the new `kpi` command. |

No other file in `email_intake/` changed.

---

## 3. KPI extraction (`kpi_extraction/`)

| File | Purpose |
|---|---|
| `schema.py` | The output format: Pydantic model `PostKPIs` and its parts |
| `prompts.py` | The system prompt and the template for the email text |
| `extractor.py` | Claude version of LLM1 (`KPIExtractor`), plus the shared `KPIResult`, `ExtractionError` and image checks |
| `ollama_extractor.py` | Ollama version of LLM1 (`OllamaKPIExtractor`); see section 4 |
| `__init__.py` | Exports `ExtractionError`, `KPIExtractor`, `KPIResult`, `PostKPIs` |

### 3.1 Output format: `schema.py`

`PostKPIs` is the brief. Every field is always present; "unknown" is written as `null` or an empty list, never as a guess.

| Group | Fields |
|---|---|
| Is it a request? | `is_post_request`, `not_a_request_reason` |
| Where and what shape | `platform`, `post_format` (feed post, story, reel/video, carousel, banner, other, not specified), `post_size` (width, height, aspect ratio, and whether the size was stated, a platform default or not specified) |
| Company | `company`: name, website, industry, brand colours, and `logo` (provided?, attachment filename, placement, and whether the placement was stated or inferred from a reference post) |
| Content | `theme`, `objective`, `key_message`, `call_to_action`, `target_audience`, `tone`, `post_language` |
| Requirements | `must_have`, `nice_to_have`, `not_to_have`, `hashtags`, `deadline` (ISO date) |
| Images | `reference_posts` (source and what to take from it) and `image_analysis`: one entry per image with filename, role (logo, sample post, product photo, brand asset, signature/decoration, unrelated), description, dominant colours and design notes |
| Gaps | `missing_information`: questions to ask the customer |

### 3.2 Prompt: `prompts.py`

The system prompt casts the model as the agency's requirements analyst. Its rules:

1. Decide first whether the email is a post request. Newsletters, job alerts, receipts and notifications are not; for those, explain why and leave the other fields empty.
2. Record only what the customer said or clearly implied. Leave missing details empty and add a question to `missing_information`.
3. Sort requirements into must-have, nice-to-have and not-to-have by how strongly they were stated.
4. Post size: use stated sizes, otherwise the platform's standard size (for example Instagram feed 1080x1350, story 1080x1920, LinkedIn 1200x1200).
5. Images: one `image_analysis` entry per image, using the exact filename; read brand colours from a logo; use a sample post to infer logo placement.
6. Post language: as requested, otherwise the language of the email.
7. Deadlines as ISO dates, with relative dates ("next Friday") worked out from the email's sent date.

The email is wrapped in `<email>` tags and treated as untrusted data, so instructions written inside an email are not followed.

### 3.3 Claude version: `extractor.py`

This was the first version of LLM1.

- `KPIExtractor.build_content()` builds the message: each image, labelled with its filename, then the email text. Non-image attachments and skipped images are listed in the text.
- Images are skipped if they are not JPEG, PNG, GIF or WebP, are larger than 5 MB, are missing on disk, or exceed 20 per email (`_skip_reason`).
- `KPIExtractor.extract()` calls the Claude API with structured output, so the answer must match `PostKPIs`. The model is `claude-opus-5-5` with effort `medium`, both changeable with `SMM_LLM1_MODEL` and `SMM_LLM1_EFFORT`. The API key is read from `ANTHROPIC_API_KEY`.
- API errors (bad key, rate limit, connection), refusals and cut-off answers are turned into `ExtractionError` with a readable message.
- `KPIResult` holds the brief plus email ID, subject, sender, model, time, images sent and skipped, and token counts. `KPIResult.save()` writes it to `data/kpis/<email id>.json`.

---

## 4. Switch to Ollama (local model)

### 4.1 Why

The Claude API charges for every email. **Since the Claude API is costly, we changed LLM1 to Ollama with the model `gemma4:e2b-it-qat`, so that it can be run free on localhost.** Other options were looked at first:

| Option | Cost | Why it was not chosen |
|---|---|---|
| Claude API | Paid per email | Cost |
| Hugging Face Inference Providers (for example `google/gemma-4-31B-it`) | Paid; free accounts get no included credit | Cost |
| OpenRouter free models | Free, limited to 50 requests per day | No guaranteed JSON format, daily limit, and free services may keep the emails sent to them |
| **Ollama on this Mac** | **Free** | **Chosen.** Emails also never leave the computer. |

### 4.2 Model: `gemma4:e2b-it-qat`

| Property | Value |
|---|---|
| Model | Google Gemma 4 E2B, instruction-tuned, Apache 2.0 licence |
| Type | Vision-language model: text and images in, text out |
| Size | 2.3 billion "effective" parameters (5.1 billion including lookup tables) |
| Format | 4-bit, quantization-aware trained (`qat`), 4.3 GB download |
| Memory when loaded | About 1.7–2.4 GB |
| Longest input | 128K tokens |

The larger Gemma 4 models do not fit this Mac's 8 GB of memory: E4B is about 6–9.5 GB and 31B about 20 GB.

### 4.3 Setup done

1. Installed the Ollama app (version 0.40.16) on macOS. It runs in the background and is shown as a llama icon in the menu bar.
2. Downloaded the model: `ollama pull gemma4:e2b-it-qat`.
3. Tested it in Terminal: `ollama run gemma4:e2b-it-qat`.

Ollama serves its API at `http://localhost:11434`. It needs no key and no internet connection. The model loads automatically when a request arrives and is unloaded after 5 minutes without use.

### 4.4 New file: `kpi_extraction/ollama_extractor.py`

`OllamaKPIExtractor` does the same job as `KPIExtractor` and returns the same `KPIResult`, so the rest of the pipeline did not change.

- **Request:** sent to Ollama's `/api/chat` with Python's built-in `urllib`, so no extra package is needed.
- **Images:** sent base64-encoded with the message, after a numbered list of their filenames, so the model can match each image to its name. The same `_skip_reason` checks as the Claude version are used.
- **Strict format:** `PostKPIs` is passed as `format`, so Ollama forces the answer into the schema's shape. The schema is also written into the prompt, because the model only learns what each field means from the prompt. The answer is checked again with Pydantic.
- **Settings:** `temperature 0` for repeatable answers, thinking off, `stream` off, and a reading window (`num_ctx`) of 20,480 tokens. This fits the longest email saved so far (17,320 tokens) plus the answer.
- **No silent cutting:** by default Ollama cuts a too-long email and answers anyway. `truncate: false` and `shift: false` turn this off, so a too-long email gives a clear error instead of a wrong brief.
- **Errors:** "Ollama not running", "email too long" and "answer does not match the schema" each raise `ExtractionError` with a hint on what to do.

Settings that can be changed with environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `SMM_OLLAMA_MODEL` | `gemma4:e2b-it-qat` | Ollama model name |
| `SMM_OLLAMA_NUM_CTX` | `20480` | Tokens the model can read at once (email + images + answer) |
| `SMM_OLLAMA_URL` | `http://localhost:11434/api/chat` | Address of the Ollama API |

### 4.5 `main.py` changes for Ollama

- New option `--backend {claude,ollama}` in `add_llm_args`, available on `gmail`, `eml` and `kpi`. The default is `claude`, so `--backend ollama` must be given to use the local model.
- `make_extractor()` returns `OllamaKPIExtractor` when the backend is `ollama`. `--model` overrides the Ollama model name; `--effort` is ignored for Ollama.

---

## 5. All other changes in `main.py`

| Change | Detail |
|---|---|
| Docstring | Now describes step 1 and step 2, with usage examples for every command |
| Imports | Added `json`, `sys` and `IncomingEmail` |
| Renames | `OUTPUT_DIR` → `INTAKE_DIR`; `save()` → `save_intake()` (same behaviour) |
| New `run_extraction()` | Runs LLM1 on one email, prints a one-line verdict (`[LLM1] <id>: post request for <company> (<platform>)` or `not a post request - <reason>`), prints the brief, saves it to `data/kpis/`, and returns `True` or `False`. A failure prints `!! LLM1 failed for <id>: <reason>` and does not stop the run. |
| New `make_extractor()` | Builds the Claude or Ollama extractor from the command-line options |
| New `add_llm_args()` | Adds `--backend`, `--model` and `--effort` to each command |
| `gmail` command | New `--extract` option. **`--mark-processed` now waits for LLM1:** with `--extract`, an email is marked processed only if its brief succeeded, so a failed email is retried on the next run (this was a next step in the last report). The email JSON is **no longer printed** in this mode; only `-> saved data/intake/<id>.json` is shown. |
| `eml` command | New `--extract` option |
| New `kpi` command | Runs LLM1 on one or more JSON files already in `data/intake/`. Exits with code 1 if any email failed, so scripts can detect it. |
| Description | `"Step 1: read incoming post-request emails"` → `"Social media manager pipeline"` |

---

## 6. Other files

- **`requirements.txt`:** added `anthropic>=0.125,<1` (the 0.x line, because the project's `.venv` is Python 3.9 and `anthropic` 1.x needs 3.10) and `pydantic>=2.5`. Ollama needs no Python package; the Ollama app itself is installed separately.
- **`.gitignore`:** added `token_json_explained.pdf` and `Gmail_Email_Intake_Setup_Pipeline.pdf` (personal notes in `personal_understanding/`).

---

## 7. How to run

Keep the Ollama app open (llama icon in the menu bar). To check it: `curl http://localhost:11434` should answer `Ollama is running`.

```
# Sample email: parse it, then extract the brief
python main.py eml samples/sample_request.eml --extract --backend ollama

# Briefs for all emails already saved in data/intake/
python main.py kpi data/intake/*.json --backend ollama

# 5 newest unread emails from Gmail, with briefs
python main.py gmail --max 5 --extract --backend ollama

# Same, and mark the successful ones processed in Gmail
python main.py gmail --max 5 --extract --backend ollama --mark-processed
```

Useful Ollama commands in Terminal:

| Command | What it does |
|---|---|
| `ollama ps` | Shows whether the model is loaded in memory |
| `ollama stop gemma4:e2b-it-qat` | Unloads the model now instead of after 5 minutes |
| Menu bar icon → Quit Ollama | Stops the app. Not needed before shutdown. |

---

## 8. Test results

| Test | Result |
|---|---|
| Sample email (`samples/sample_request.eml`, 1 logo image) | Valid brief in about 20–45 s. Platform, size, logo placement, price, must-have, nice-to-have and not-to-have were all correct. 2,714 tokens in, 571 out. |
| Ollama app not running | Clear error: `Could not get an answer from Ollama ... Is the Ollama app running?` |
| Email longer than the reading window | Clear error telling you to raise `SMM_OLLAMA_NUM_CTX` |
| Three of the earlier Gmail emails (2 with images, 1 very long) | Valid JSON for all, in 23–68 s each |
| Gmail run on 2026-11-16 (`--max 5 --extract --backend ollama`) | 5 briefs saved in `data/kpis/`: 1 post request, 4 not post requests |

The code and the JSON format work every time. The **quality of the answers** is the weak point; see section 10.

The Claude version (`--backend claude`) has not been run end to end yet, because no `ANTHROPIC_API_KEY` is set on this machine.

---

## 9. How far this is from the expected flow

| Stage | Description | Status |
|---|---|---|
| 1. Email intake | Read emails, parse them, save attachments, mark them processed | **Done** |
| 2. LLM1: KPI extraction | Turn the email into a structured brief (`PostKPIs`) | **Done** (Ollama, local) |
| 3. VLM: image analysis | Classify images and read colours and layout | **Done**, merged into stage 2: one model call reads text and images |
| 4. Post generation and later steps | Not defined in the code yet | **Not started** |

Items from the last report's next steps that are now done: LLM1 design and build (1, 2), image analysis (3), marking processed after LLM1 succeeds (4), and git initialized and connected to GitHub (6).

---

## 10. Known gaps and risks

- **Answer quality of the small model.** Gemma 4 E2B is much weaker than Claude or the larger Gemma models. Seen in tests:
  - It writes the word `"null"` into lists (hashtags, colours) instead of leaving them empty.
  - It invents `image_analysis` entries for emails that had no images. In the 2026-11-16 Gmail run, no images were sent, but 4 of the 5 briefs list 1–6 images.
  - It misses images: for one email with 5 images, only 3 were analysed.
  - It fills `must_have` lists for emails it has marked "not a post request", which the prompt forbids.

  Briefs need a human check before use.
- **Slow.** About 20–70 seconds per email on this Mac, longer for long emails.
- **`anthropic` is still needed for Ollama.** `ollama_extractor.py` reuses code from `extractor.py`, which imports `anthropic`, so that package must stay installed.
- **Default backend is Claude.** Forgetting `--backend ollama` sends the email to the paid Claude API (or fails without a key).
- **Results overwrite each other.** Both backends save to `data/kpis/<email id>.json`; the `model` field shows which one made the file.
- **Not tested:** GIF and WebP images, and emails with more than 5 images.
- **Still open from the last report:** no automated tests, no scheduler, the 7-day Google token expiry in Testing mode, and the 500-email cap on `--max`.
- **Uncommitted work.** `kpi_extraction/` and the changes to `main.py`, `models.py`, `requirements.txt` and `.gitignore` are not committed yet.

---

## 11. Suggested next steps

1. Commit the current work to git.
2. Make `ollama` the default backend, or read it from an environment variable, so the paid API is never used by mistake.
3. Add simple checks after the model answers: drop `"null"` strings, drop `image_analysis` entries whose filename was not sent, and empty the requirement lists when `is_post_request` is false.
4. Build a small test set of emails with the correct briefs written by hand, and compare models on it (for example E2B locally against a larger Gemma 4 model).
5. Move the shared parts (`KPIResult`, `ExtractionError`, `_skip_reason`) out of `extractor.py`, so the Ollama path no longer needs `anthropic`.
6. Design step 4, post generation from the brief.
7. Add automated tests and a scheduler, as listed in the last report.

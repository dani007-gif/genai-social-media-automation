# Progress Report: Social Media Manager, Step 1 (Email Intake)

**Date and time:** 2026-11-14, 14:44 IST
**Project:** `Projects/Social_media_manager`

---

## 1. Summary

Step 1 of the pipeline, **email intake**, is built and working end to end. The code reads unread post-request emails from Gmail (or a local `.eml` file), parses them into structured JSON, saves attachments, and marks processed emails so they are not fetched twice.

The steps after intake (LLM1 KPI extraction and image analysis) are **not started**.

---

## 2. Tasks completed

### Code (in `email_intake/` and `main.py`)

| Task | File | Status |
|---|---|---|
| Data models (`IncomingEmail`, `Attachment`) | `models.py` | Done |
| Raw email parser: sender, recipients, subject, date, plain-text body, HTML body | `parser.py` | Done |
| HTML-to-text conversion for the LLM prompt | `parser.py` | Done |
| Attachment and inline-image saving, with safe and unique filenames and a size limit | `parser.py` | Done |
| Local `.eml` loader (for testing without Gmail) | `eml_loader.py` | Done |
| Gmail OAuth login with saved token and silent refresh | `gmail_client.py` | Done |
| Search for unread, unprocessed emails (`is:unread -label:smm-processed`) | `gmail_client.py` | Done |
| Fetch and decode a raw email by ID | `gmail_client.py` | Done |
| `smm-processed` label: find or create, then mark the email as read | `gmail_client.py` | Done |
| Command-line interface (`gmail` and `eml` modes, `--query`, `--max`, `--mark-processed`) | `main.py` | Done |

### Setup and testing

- Created a virtual environment (`.venv`) and installed the Gmail libraries from `requirements.txt`.
- Tested the parser with `samples/sample_request.eml` (output in `data/intake/sample_request.json`).
- Set up a Google Cloud project, enabled the Gmail API, and created OAuth credentials (`credentials.json`).
- Hit the Google `403 access_denied` error. Fixed by adding the Gmail account as a test user on the OAuth consent screen.
- Signed in successfully, so `token.json` was created.
- Fetched real emails from Gmail on Nov 11 and Nov 14.
- Ran with `--mark-processed`. Confirmed that processed emails were marked read and labeled `smm-processed` in Gmail, and that a repeat run printed `No new emails.` for them.

### Current output

- **13 files** in `data/intake/` as of this report: 12 Gmail emails plus 1 sample.
- Attachments are saved under `data/attachments/<message_id>/`. Folders exist only for emails that had attachments or inline images.

---

## 3. How far this is from the expected flow

The expected flow is taken from the project's own notes in the code, because no separate design document was found. These notes say: *"step 1: email intake"*, *"`IncomingEmail` objects are what LLM1 (KPI extraction) will take next"*, and *"Images to send to the VLM (logos, sample posts)"*.

| Stage | Description | Status |
|---|---|---|
| 1. Email intake | Read emails, parse them, save attachments, mark them processed | **Done** |
| 2. LLM1: KPI extraction | Send `body_text` to an LLM and extract the request details and KPIs | **Not started** |
| 3. VLM: image analysis | Send images (`image_attachments`, flagged by `needs_vision`) to a vision model | **Not started** |
| 4. Post generation and later steps | Not defined in the code yet | **Not started** |

**Estimated progress:** the first stage of at least four is complete. The intake output is already shaped for the next stages, since `body_text` is ready for the LLM prompt and `needs_vision` flags emails with images. That makes stage 2 a clean next step.

---

## 4. Known gaps and risks

- **Manual runs only.** Intake runs when you type the command. There is no scheduler or automatic trigger.
- **Marking is opt-in.** Emails are marked processed only with `--mark-processed`. Without it, the same emails come back on every run.
- **Marking happens at fetch time.** The email is marked processed right after it is saved. Nothing checks yet that a later pipeline stage succeeded. When LLM1 is added, `mark_processed` should move to after LLM1 succeeds.
- **No automated tests.** Testing so far has been manual.
- **Token expiry.** While the Google app is in Testing mode, the login expires after about 7 days. Delete `token.json` and sign in again when that happens.
- **Single fetch call.** `--max` is capped at 500 by the Gmail API, because the code makes one list request with no paging.
- **Secrets.** `credentials.json` and `token.json` are in `.gitignore`. The folder is not a git repository yet, so there is no version history.

---

## 5. Suggested next steps

1. Design the LLM1 input and output: the KPI schema and the prompt, using `IncomingEmail.body_text`.
2. Build the LLM1 step and test it on the saved JSON files in `data/intake/`.
3. Add the VLM step for emails where `needs_vision` is true.
4. Move `mark_processed` to run after LLM1 succeeds.
5. Add a few automated tests for the parser, using `samples/sample_request.eml`.
6. Initialize git and commit.
7. Add a scheduler to run intake automatically.

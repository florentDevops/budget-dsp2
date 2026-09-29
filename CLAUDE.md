# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Budget DSP2: a personal, local-first budgeting app. It pulls bank transactions via open banking (DSP2) through Enable Banking, classifies them, separates essential from optimizable spending, and surfaces savings opportunities on a dependency-free web dashboard. Stack: Python, FastAPI, SQLite, optional Claude (Anthropic) for merchant classification.

## Commands

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload      # serves the app + dashboard on :8000
python -m scripts.seed_demo        # load 6 months of fake statement data (or POST /api/demo)
pytest -q                          # run the full suite (19 tests)
pytest tests/test_core.py -k test_detect_recurring   # run a single test
```

There is no build/lint step configured; `app/static/index.html` is a static, dependency-free dashboard served directly (no bundler).

## Architecture

```
Bank ──DSP2──> Enable Banking ──> enable_banking.py ──> SQLite (db.py)
                                                             │
                          classifier.py (rules > MCC > LLM) ┤
                                                             │
                          insights.py (subscriptions, drift)┴──> FastAPI (main.py) ──> dashboard (static/index.html)
```

- **`app/enable_banking.py`** — Enable Banking (DSP2/AISP aggregator) client: RS256-JWT-signed requests, consent flow (`start_auth` → bank SCA → `create_session`), paginated `iter_transactions`. `normalize_transaction` maps their payload to our schema and drops pending (`PDNG`) transactions.
- **`app/normalize.py`** — strips French bank label noise (card/SEPA prefixes, dates, long reference numbers, trailing city/legal-form tokens) to derive a stable `merchant` grouping key from a raw label/counterparty.
- **`app/classifier.py`** — cascading classification, first match wins: (1) a user's manual correction (`merchant_overrides`, remembered per merchant and applied to all its history, past and future), (2) regex rules in `app/rules.yaml` matched against the cleaned label (most specific rules first in the file), (3) MCC code via `categories.MCC_MAP` if the bank sends one, (4) Claude, called once per unknown merchant then cached as an override with `source="llm"`, (5) otherwise `inconnu`. Positive amounts (money in) default to `revenus` unless the matched category is in `_CREDIT_CATEGORIES` (`epargne`, `virements`, `revenus`).
- **`app/llm.py`** — only normalized merchant names are ever sent to Claude, never amounts/dates/IBAN/balances. Batches unknown merchants (60 per call), parses a strict JSON response, never raises (a failed batch just leaves merchants unclassified for the next sync).
- **`app/categories.py`** — single source of truth for categories, each with a `nature`: `essentiel`, `optimisable`, `epargne`, `revenu`, `transfert`, plus `RENEGOTIABLE` categories and `SAVINGS_RATE` (recoverable share per category used to estimate savings potential).
- **`app/insights.py`** — all detection thresholds live at the top of the file. Computes, per month: recurring subscriptions/contracts (`detect_recurring`: same merchant, amount stable ±15%, ~monthly cadence, seen 3+ months, still active), bank fees, categories drifting >20% vs. the prior 3-month average, repeated micro-spending (<15€, 6+ times/month at the same merchant), and a `savings_estimate` derived from `SAVINGS_RATE`. Also flags which transactions to highlight in the UI.
- **`app/db.py`** — single-file SQLite, no server; `accounts` and `transactions` tables, plus merchant overrides. `settings.db_path` (from `.env`, default `data/budget.db`) controls the file location.
- **`app/main.py`** — FastAPI routes tying the above together (`/api/connect`, `/callback`, `/api/sync`, `/api/summary`, `/api/merchants/{merchant}`, `/api/reclassify`, `/api/demo`); see README's API table for the full list.

## Notes

- Enable Banking requires a private key at `keys/private.pem` and `ENABLE_BANKING_APP_ID` in `.env`; without them `settings.bank_enabled` is `False` and only the demo/manual-sync-free paths work. Without `ANTHROPIC_API_KEY`, `settings.llm_enabled` is `False` and classification relies solely on rules/MCC (unmatched merchants stay `inconnu`).
- After editing `app/rules.yaml`, call `POST /api/reclassify` (or restart) — `classifier.load_rules` is `lru_cache`d.
- This app is designed for local, single-user use; it has no authentication layer.

<!-- BACKLOG.MD GUIDELINES START -->
<!-- backlog.md-instructions-version: 1.53.0 -->
<CRITICAL_INSTRUCTION>

## Backlog.md Workflow

This project uses Backlog.md for task and project management.

**At the beginning of each conversation in this project, run `backlog instructions overview` before answering or taking action. Re-read it only if you have not read it yet in the current conversation.**

Use the overview to decide whether to search, read, create, or update Backlog tasks.

Before task lifecycle actions, read the matching detailed guide:
- `backlog instructions task-creation` before creating or splitting tasks
- `backlog instructions task-execution` before planning, changing status or assignee, adding a plan or implementation notes, or implementing task work
- `backlog instructions task-finalization` before checking acceptance criteria, writing final summaries, or moving tasks to terminal statuses

Use `backlog <command> --help` before running unfamiliar commands. Help shows options, fields, and examples.

Do not edit Backlog task, draft, document, decision, or milestone markdown files directly. Use the `backlog` CLI so metadata, relationships, and history stay consistent.

</CRITICAL_INSTRUCTION>
<!-- BACKLOG.MD GUIDELINES END -->

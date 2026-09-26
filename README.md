# AI Job Search Agent

Upload your CV, set your criteria, and the agent scans open job boards and
employers' own ATS boards, then ranks every posting by how well it fits you —
with a per-posting tailored CV and cover letter on demand.

**Bring your own LLM.** Claude Code (no API key), the Anthropic API, or any
OpenAI-compatible endpoint including fully local models via Ollama / LM Studio.

---

## Quick start

Requirements: Python 3.12+, Node.js 20+, and one model provider (see below).

```bash
git clone https://github.com/diyaralma/ai-job-search-agent.git
cd ai-job-search-agent/agent

python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
cp .env.example .env                       # pick your provider here
./.venv/bin/python scripts/check_llm.py    # verify model access

cd ../web && npm install && cd ..
./start.sh    # agent :8000, web :3001   —   ./stop.sh to stop
```

Then open **http://localhost:3001**.

If `python3 -m venv` fails (Debian/Ubuntu may lack `python3-venv`):

```bash
sudo apt install python3-venv python3-pip     # or, without sudo:
curl -LsSf https://astral.sh/uv/install.sh | sh
~/.local/bin/uv venv .venv && ~/.local/bin/uv pip install --python .venv/bin/python -r requirements.txt
```

### Windows

The app itself is cross-platform — only `start.sh` / `stop.sh` are bash (they use
process groups and PID files under `/tmp`). Two options:

**WSL2 (recommended).** Everything above works unchanged inside the Ubuntu shell.

**Native Windows.** Skip the scripts and run the two services in two terminals:

```powershell
# terminal 1 — agent
cd agent
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# terminal 2 — web
cd web
npm install
npm run dev          # http://localhost:3001
```

Stop with Ctrl+C in each. PDF export picks up Arial from `C:\Windows\Fonts` when
DejaVu Sans is not installed, so tailored CVs download normally.

---

## Choose your LLM

One line in `agent/.env` decides which engine runs everything:

| `LLM_PROVIDER` | What it needs | Good for |
|---|---|---|
| `claude_cli` (default) | Claude Code installed and logged in | Anyone with a Claude Pro/Max subscription — **no API key, no credit** |
| `anthropic` | `ANTHROPIC_API_KEY` | Running on a server or in a container |
| `openai` | `LLM_MODEL` + (usually) an API key | OpenAI, OpenRouter, Groq, Together, DeepSeek, Google's OpenAI endpoint — and **fully local, free** setups via Ollama / LM Studio / vLLM |

```bash
# OpenAI
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...

# Fully local, no key, no cost (Ollama)
LLM_PROVIDER=openai
LLM_MODEL=llama3.1:8b
LLM_BASE_URL=http://localhost:11434/v1

# Any model through OpenRouter
LLM_PROVIDER=openai
LLM_MODEL=anthropic/claude-sonnet-4.5
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=sk-or-...
```

Verify with `cd agent && ./.venv/bin/python scripts/check_llm.py`. The active
provider is also shown in the page header at localhost:3001 — green dot means
ready, amber tells you exactly what is missing.

Every step of the pipeline expects a response matching a Pydantic schema. Each
provider uses the strongest tool it has (`--json-schema` on the CLI, structured
outputs on the Anthropic API, `response_format` on OpenAI-compatible endpoints)
and the result is **always** validated in `agent/app/llm.py`. On a server without
schema support, `LLM_JSON_MODE=auto` steps down to weaker modes and remembers
what worked.

---

## Using it

### 1. Upload a CV

PDF, DOCX or TXT — 25 MB max, drag-and-drop works.

Text is extracted locally, then the model turns it into a structured profile:
target titles, skills, years of experience, seniority, languages, education.
Takes **10-25 seconds**. If the seniority or titles come out wrong, the PDF's
reading order was probably scrambled (common with two-column designs) — upload
the same CV as DOCX.

The profile is cached in the browser, so a refresh does not mean re-uploading.
Use **"Upload a different CV"** on the profile card to start over.

### 2. Set criteria

| Field | Notes |
|---|---|
| **Countries / Cities** | Comma separated. Leave empty for no geographic filter. |
| **Work mode** | Remote / Hybrid / Onsite. With "Remote", a posting's **own** geo restriction is checked too — a "Remote — US only" job is not shown to a candidate in Turkey. |
| **Seniority** | All levels if none selected. |
| **Exclude keywords** | Dropped if they appear in the job **title** (`sales, unpaid, commission`). |
| **Exclude companies** | Former employers, companies you'd rather not see. |
| **Max posting age (days)** | Default 45. |
| **Number of results** | Default 40. |

### 3. Search and read the results

A search takes **30-90 seconds** and stays open for the whole HTTP request —
don't close the tab. In that time it builds a search plan, scans the sources in
parallel, applies rule-based filtering, and has the model score what survives.

The four numbers at the top of the results show that funnel: **fetched → after
dedupe → passed pre-filter → scored by AI**. A big drop is normal; the rule layer
removes obvious mismatches.

Each card carries a score (0-100), a verdict (`strong` / `good` / `stretch` /
`poor`), matched and missing skills, the reasoning behind the score, and any
risks worth checking before applying. Two banners can appear:

- **"The pool matching your criteria is thin"** — very little passed the filter;
  loosen the criteria or raise the posting age.
- **"Nothing matched your criteria"** — nothing survived, so filters were
  relaxed automatically; the results shown may fall outside your criteria.

### 4. Generate a tailored CV and cover letter

**"Tailor a CV for this job"** on any card produces a kit in **20-40 seconds**:
an adapted CV (downloadable as **PDF** and **DOCX**), a cover letter in the
posting's language, a "Why me?" answer, talking points, and a transparency
section. Each text block has a **Copy** button for pasting into application
forms.

The model only reframes facts already in your profile. It never claims
experience you do not have — anything the posting wants and you lack is listed
under "May come up in the interview" instead. That constraint is deliberate: an
interview won on a false claim collapses at the first technical question, and a
submitted application cannot be recalled.

### 5. Apply

The link on the card takes you to the posting itself. Applications always go
through the job owner's own system — the app never fills in forms on your
behalf. Auto-apply is only reliable on employer ATS boards
(Greenhouse/Lever/Ashby/Workable); postings from aggregators redirect through
click trackers to arbitrary employer sites that cannot be resolved
programmatically.

When you're done: `./stop.sh`.

### Searching in Turkey

None of the key-free sources carry Turkish job listings. Jooble does, its API is
free, and **every user needs their own key** — nothing is shipped in this repo.

The app asks for it: a box at the top of the page links to the signup, takes the
key, and stores it in your local `agent/.env`. Pick the region first — **Jooble
keys are regional**, and a key issued on `jooble.org` queries the US index (a
search for "Turkey" returns the town of Turkey, North Carolina) while getting a
403 on `tr.jooble.org`. For Turkish listings, choose Turkey and get the key from
[tr.jooble.org/api/about](https://tr.jooble.org/api/about).

The key never leaves your machine: the agent binds to 127.0.0.1, writes the key
to `agent/.env`, and never sends it back to the browser. You can also set
`JOOBLE_API_KEY` / `JOOBLE_HOST` in that file by hand — same thing.

Measured difference on a "Turkey + Ankara/Istanbul" search: without a key, 320
postings fetched and **zero** based in Turkey; with a Turkish Jooble key, 368
postings and half the results in Istanbul/Ankara. The free quota is 500 requests,
and one search spends one request per city.

### What a search costs

Roughly **6 model calls** per search (1 plan + 4 scoring batches + 1 per kit; CV
analysis is 1 more). On `claude_cli` these count against your subscription usage
with no token charge. On a paid provider the biggest line item is scoring:
halving `LLM_SCORE_LIMIT` (32 → 16) halves it, at the cost of evaluating fewer
postings.

### Troubleshooting

| Symptom | What to do |
|---|---|
| Amber dot / amber warning box | The provider is not ready. `cd agent && ./.venv/bin/python scripts/check_llm.py` prints the exact reason. |
| `Model output did not match the schema` | The model can't hold the schema — usually a small local one. Try a bigger model, or `LLM_JSON_MODE=object` (some servers need `prompt`). |
| `The response was cut off at LLM_MAX_TOKENS` | Raise `LLM_MAX_TOKENS`, or lower `SCORE_BATCH_SIZE`. |
| Rate/quota limit (429) | Lower `MAX_CONCURRENCY`. |
| No Turkish postings in the results | None of the key-free sources carry Turkish listings — add your own free Jooble key from the box at the top of the page (see [Searching in Turkey](#searching-in-turkey)). |
| "Could not reach the agent service" | `tail -30 /tmp/jobagent-agent.log` — the service may have crashed. |
| Port 3001 in use | Run the web app on another port and add that address to `CORS_ORIGINS` in `agent/.env`. |

---

## Configuration

Main settings in `agent/.env` (full list with comments in `agent/.env.example`):

| Variable | Default | What it does |
|---|---|---|
| `LLM_PROVIDER` | `claude_cli` | `claude_cli` / `anthropic` / `openai` |
| `LLM_MODEL` | provider default | Model name; required for the `openai` provider |
| `LLM_API_KEY` | — | Key; `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` are read too |
| `LLM_BASE_URL` | — | OpenAI-compatible endpoint (most need a trailing `/v1`) |
| `LLM_TIMEOUT` | `300` | Seconds per model call |
| `LLM_MAX_TOKENS` | `16000` | Token ceiling per response |
| `LLM_JSON_MODE` | `auto` | Schema enforcement (`openai` only): `auto`/`schema`/`object`/`prompt` |
| `LLM_SCORE_LIMIT` | `32` | How many postings reach the LLM — the main cost lever |
| `SCORE_BATCH_SIZE` | `8` | Postings per call |
| `MAX_CONCURRENCY` | `4` | Batches in flight at once |
| `JOOBLE_HOST` | `https://jooble.org` | Region the key came from; `https://tr.jooble.org` for Turkey |
| `ADZUNA_APP_ID/KEY`, `JOOBLE_API_KEY` | — | Empty disables that source silently |

**Companies to track:** add ATS board ids to `agent/app/sources/companies.json`.
You can read the id off a posting URL: `boards.greenhouse.io/<token>`,
`jobs.lever.co/<company>`, `jobs.ashbyhq.com/<board>`, `<account>.workable.com`.
A broken id is skipped silently. **The bundled list is US-centric sample data —
replace it with your own targets.**

---

## How it works

```
CV (PDF/DOCX/TXT)
  └─> local text extraction                        agent/app/cv/
        └─> [LLM] CandidateProfile
              └─> [LLM] SearchPlan (queries, titles, must-have skills)
                    └─> parallel fetch from sources        agent/app/sources/
                          └─> dedupe + hard filters (rules)
                                └─> pre-ranking + per-source quota → 32 postings
                                      └─> [LLM] fit scoring (4 parallel batches)
                                            └─> ranked results with reasoning
```

Two-stage filtering is deliberate: sources return hundreds of postings and
sending all of them to a model is slow and pointless. The rule layer drops the
obvious mismatches; the LLM only looks at postings that need real judgement. No
single source may take more than half the LLM budget — ATS boards return much
longer posting text, which would otherwise let a handful of tracked companies
crowd out everything else.

**Sources:** Remotive, Jobicy, Himalayas, RemoteOK, Arbeitnow and employer ATS
boards (Greenhouse, Lever, Ashby, Workable) need no key. Adzuna (free tier) and
Jooble (free) need one. Jobicy and Himalayas expose geo restrictions as
structured data, so "Remote — United States" is filtered on data rather than
guesswork.

**No LinkedIn or Indeed:** neither has a usable public API for this (LinkedIn's
Job Postings API is limited to partner ATS vendors, Indeed closed its publisher
API to new applicants). Scraping violates their terms and gets blocked. The
legitimate route is Google Jobs via SerpAPI (~$50/month), which indexes both —
adding it means one new class under `agent/app/sources/`.

### Verification scripts

```bash
cd agent
./.venv/bin/python scripts/test_prefilter.py   # rule-layer unit tests (no LLM, seconds)
./.venv/bin/python scripts/smoke_sources.py    # are the sources alive (no LLM)
./.venv/bin/python scripts/smoke_pipeline.py   # whole pipeline (LLM faked)
./.venv/bin/python scripts/check_llm.py        # model access (1 real call)
```

### Known limits

- **Search is synchronous and slow** (~85s), held open for the whole HTTP
  request. Production would need a queue plus job-status polling.
- **PDF text extraction is local**, so heavily designed or two-column PDFs can
  come out in the wrong reading order. Scanned PDFs fail with a clear error —
  upload DOCX/TXT.
- **Single user.** SQLite, no auth. Multi-user would need Postgres + auth;
  `agent/app/store.py` was written with that migration in mind.
- **Salary filtering is not applied.** `min_salary` is collected but most
  postings do not expose salary as structured data.
- **`claude_cli` does not work in Docker** — there is no Claude Code session
  inside the container. Use the `anthropic` or `openai` provider there.

### Layout

```
agent/                     Python FastAPI agent service
  app/
    cv/                    CV → text → CandidateProfile
    search/                planner (LLM) + prefilter (rules, quota, geo penalty)
    match/                 LLM scoring in parallel batches
    tailor/                per-posting CV generation + PDF/DOCX rendering
    sources/               job sources + companies.json
    providers/             model providers (claude_cli / anthropic / openai)
    llm.py                 provider selection + schema validation (single entry point)
    pipeline.py            end-to-end flow
    schemas.py             every data type (including the API contract)
  scripts/                 verification scripts
web/                       Next.js UI (3 step flow)
start.sh / stop.sh         start/stop both services
```

`web/lib/types.ts` mirrors `agent/app/schemas.py` — they are kept in sync by hand.

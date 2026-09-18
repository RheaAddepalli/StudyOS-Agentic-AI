# StudyOS

An agentic system that takes an arbitrary learning goal — "teach me Python from
scratch", "I want research-level understanding of Transformers, 1hr/day" —
and produces a personalized, resource-grounded, adaptive curriculum. No
subject is hardcoded: the same graph that handles Python handles Kubernetes,
German, or compilers, because it reasons about the goal instead of looking up
a prewritten roadmap.

This repo has two parts, sibling folders:

```
studyos-combined/
  studyos/            backend — FastAPI + LangGraph agent + CLI
  studyos-frontend/   frontend — React app (paths list, per-stage practice, submissions)
```

## What this actually is

An explicit [LangGraph](https://github.com/langchain-ai/langgraph) agent
pipeline, backed by real tools (web search, arXiv, GitHub, a sandboxed Python
executor) exposed both as in-process functions and as a genuine [MCP](https://modelcontextprotocol.io)
server, with persistent learner state (SQLite locally, Postgres in
production) so progress survives a restart. On top of that sits a React
frontend with a dashboard per learning "path," where every concept has its
own independent Practice button and permanent submission history.

```
goal_understanding → prerequisite_reasoning → research → resource_evaluation
   → curriculum_planning → [ practice_generation ⇄ assessment (interactive)
                              ⇄ progress_tracking_and_replan ]  (loops per concept)
```

The loop over concepts is driven by `cli.py` (terminal) or `api.py` (web),
not entirely inside one LangGraph graph — see "Design decisions" below for why.

## Backend setup

```bash
cd studyos
python -m venv .venv && source .venv/bin/activate
pip install -e .
pip install -r requirements.txt
cp .env.example .env   # fill in GROQ_API_KEY
```

Uses [Groq](https://console.groq.com) (`openai/gpt-oss-120b` by default —
override with `STUDYOS_MODEL` in `.env`) via its OpenAI-compatible chat
completions endpoint, wrapped in `llm.py`. Swapping providers again later
means editing `llm.py`'s `get_client()`/`complete()` only — nothing else in
the codebase talks to the LLM directly.

### Two ways to use the backend: CLI or web API

**CLI** — good for quick local testing, no frontend needed:

```bash
python -m studyos.cli --learner rhea --path transformers "I want to learn \
Transformers from the fundamentals and eventually understand the Attention \
Is All You Need paper. I know Python and basic neural networks, 1 hour a day."
```

A learner can run several independent `--path` values (e.g. `--path python`,
`--path transformers`) without them interfering — same idea as the web
frontend's "topics." Run it again with the same `--learner`/`--path` and no
goal text to resume exactly where you left off.

Run the MCP server standalone, for any MCP client to connect to:
```bash
python -m studyos.mcp_server
```

**Web API** (what the frontend talks to):
```bash
uvicorn studyos.api:app --reload --port 8000
```

By default this persists to the local SQLite file, same as the CLI. To use
Postgres instead (needed for a real deployment — see "Persistence" below),
set `DATABASE_URL` in `.env` to a Postgres connection string (a free
[Neon](https://neon.tech) database works well) before starting it.

A learner can have several independent learning paths at once (e.g.
"python" and "transformers" in parallel) — endpoints are scoped by both
`learner_id` and `path_name`. Key routes: `GET /learners/{id}/paths` (list
this learner's paths), `GET /learners/{id}/paths/{path}/goal/stream` (SSE —
builds a new path's curriculum), `GET
/learners/{id}/paths/{path}/concepts/{concept_id}/practice` (practice for
*any* concept in the curriculum, not just the sequential "current" one —
a learner can jump ahead or revisit a finished concept independently),
`POST .../concepts/{concept_id}/practice/restart` (discard in-progress
questions, keep mastery), `GET .../concepts/{concept_id}/submissions`
(permanent Q&A history for that concept), `POST
.../concepts/{concept_id}/practice/{item_id}/answer` (grades one answer;
only advances/remediates the real curriculum if this concept is the actual
sequential current one — otherwise just updates that concept's own mastery).
Each round is a fixed 5 questions. No auth — a learner is just a name,
matching the frontend's username-only identity.

## Frontend setup

```bash
cd studyos-frontend
npm install
cp .env.example .env    # point VITE_API_URL at your local backend
npm run dev
```

Runs on `http://localhost:5173` by default. Requires the backend running
(above) with `ALLOWED_ORIGINS` including `http://localhost:5173`.

No login: a learner is just a name typed once and stored in the browser
(`localStorage`). Every request sends that name to the backend, which uses it
as the key for that learner's saved state.

**Layout**: a "Your topics" list per learner → open a topic → a stage
timeline with resources, mastery badges, and an independent **Practice**
button per stage (practicing "advanced" doesn't require finishing "basics"
first) → each stage that's been attempted also has a **view submissions**
link showing every question you've ever answered for it, with your answer
and the grading feedback, permanently.

## Persistence: why the backend needs Postgres, not SQLite, in production

SQLite writes to a file on local disk. That's fine for the CLI and for local
API testing, but Render's free/starter web services have an **ephemeral
filesystem** — it's wiped on every redeploy. `state.py` supports both
backends behind the same interface (`StateStoreBase`); set `DATABASE_URL` and
it switches automatically, no other code changes.

Render's own free Postgres also isn't the answer here: it **expires 30 days
after creation** (1GB cap, 14-day grace period, then deletion) — it would
just relocate the same problem. [Neon](https://neon.tech) has a genuinely
permanent free tier and is plain Postgres, so this was the straightforward
choice: host compute on Render, host state on Neon.


## Tests and evaluation — two different things

Backend:
```bash
cd studyos
pytest tests/            # fast, offline, LLM calls mocked — checks wiring & logic
python eval/run_eval.py  # real LLM calls, real cost — checks output quality across 8 diverse goals
```
`tests/` verifies the deterministic parts are actually correct: topological
sort, cycle detection, curriculum assembly, mastery thresholds, state
persistence round-tripping, the LangGraph pipeline wiring end-to-end, the
FastAPI endpoints (goal generation through SSE, practice fetch including
off-path concepts, answer grading, per-answer persistence, rejecting a
duplicate answer), and that practicing a concept ahead of or behind the real
sequential position never disturbs the actual curriculum's progression. None
of this requires an API key.

`eval/` is different — it runs the real pipeline against goals spanning
Python, Transformers, Kubernetes, German, statistics, OS concepts, RAG, and
compilers, and reports structural metrics (no LLM involved: does the
prerequisite order hold, does every resource have a real URL) alongside
LLM-judge scores (an LLM rating curriculum quality — a cheap proxy signal,
*not* ground truth; see `eval/metrics.py` docstring for why).

Frontend:
```bash
cd studyos-frontend
npm test
```
Component tests with the API layer mocked (`vitest` + `@testing-library/react`,
jsdom — no real browser needed). These caught real bugs during development:
a `submitAnswer` call-signature mismatch, a component accidentally importing
itself (infinite render loop), and a UX bug where the final graded answer was
hidden the instant a concept was mastered instead of staying visible.

## What's real vs. simplified — read this before presenting it as finished

- **Research tools are real and unauthenticated**: DuckDuckGo web search,
  arXiv, GitHub — no API keys required to run the demo. Tested against the
  live GitHub API during development.
- **Code sandbox is a subprocess sandbox, not a container.** Timeout + CPU/
  memory rlimits + fresh temp dir, verified to actually kill runaway loops and
  over-allocating processes. It is not isolated from the filesystem or network
  the way a container/VM is. Fine for a portfolio demo grading your own
  practice submissions; do not point it at arbitrary untrusted input from
  strangers without swapping in a real sandbox (Docker `--network=none`,
  gVisor, or a hosted option like E2B).
- **MCP server is genuinely wired up** (verified: all 6 tools register and
  are callable) but the LangGraph pipeline itself calls the tool functions
  in-process rather than through the MCP server — see "Design decisions".
- **The eval harness's LLM-judge scores are a proxy, not a benchmark.** Real
  evaluation of "is this actually a good curriculum" needs a human opening
  the recommended links, which this doesn't automate.
- **YouTube video discovery is not implemented.** The spec mentions videos as
  an example resource type; there's no free, unauthenticated YouTube search
  API, so this was left out rather than faked with scraping. Swapping in the
  YouTube Data API (needs a key) is a small, isolated addition to `tools/`.
- **Assessment grading is LLM-based, not a fixed rubric checker** — reasonable
  for conceptual questions, weaker for exact-match style grading. It's
  intentionally generous-but-skeptical per the grading prompt in
  `graph/nodes.py`.
- **No authentication on the web app.** A learner is just a name — anyone who
  knows or guesses a name can view and answer as that learner. Fine for a
  personal/portfolio tool; a real multi-user product would need actual auth
  before this design would be appropriate.
- **SSE reconnection isn't handled.** If the connection drops mid-curriculum-
  build (closed laptop, flaky wifi), the frontend shows the error and the
  person has to resubmit the goal — it doesn't automatically resume the
  stream or pick up a partially-built curriculum.
- **Groq's free tier rate-limits fairly aggressively.** `llm.py` retries on
  429s but caps the wait at 12 seconds and fails fast with a clear error past
  that, rather than silently hanging an interactive request for minutes.

## Design decisions worth knowing before you extend this

**Why assessment isn't a LangGraph node.** Grading needs a learner's answer
per practice item, which is inherently interactive. Rather than fake this
with LangGraph's `interrupt()`/checkpointer machinery (real, but adds a
persistence layer of its own that would compete with the state store this
project already needs for other reasons), `cli.py`/`api.py` own the
interactive loop and call `grade_practice_item()` directly per answer. The
two LangGraph graphs either side of it (`build_progress_graph`,
`build_replan_graph`) stay small, synchronous, and independently testable.

**Why curriculum_planning has no LLM call.** Given a validated concept graph
and evaluated resources, assembling stages in dependency order is
deterministic. Making it a Python function instead of another prompt is the
"clear separation between LLM reasoning and deterministic application logic"
the spec asks for, taken literally: reasoning nodes use `complete_json`
against a schema; assembly nodes don't call the LLM at all.

**Why progress_tracking_and_replan uses fixed thresholds instead of an LLM
judgment call.** Same reason — whether a 6.5 average means "advance" should
be a rule, not a mood. The LLM's role is generating better remediation
content next time (`practice_generation` reads `weak_areas` and is told to
simplify), not deciding whether remediation is needed.

**Why practicing an off-path concept doesn't disturb real progression.**
A learner can click "Practice" on any concept, not just the current one —
useful for jumping ahead or reviewing something already mastered. That
practice session still updates the concept's own mastery (so a review
session actually counts), but it must never accidentally advance or rewind
the *real* curriculum queue just because you happened to practice something
off-path. `api.py` handles this by running the replan node against a deep
copy of the learner's state and only merging back the queue/current-concept
changes when the practiced concept really was the sequential current one —
otherwise only the mastery update is kept.

## Layout

```
studyos/
  src/studyos/
    schemas.py         typed domain models + LLM-I/O wrapper schemas
    config.py           env-driven settings
    state.py             SQLite (local) or Postgres (DATABASE_URL) persistence
    llm.py                 Groq wrapper: complete() / complete_json()
    tools/                  web_search, arxiv_search, github_search, code_exec
    graph/
      state.py                LangGraph TypedDict state
      nodes.py                  one function per pipeline stage
      build_graph.py              wires nodes into three compiled graphs
    mcp_server.py                  same tools, exposed over real MCP
    cli.py                          interactive terminal runner (--learner, --path)
    api.py                            FastAPI backend for the web frontend
  tests/                              offline, mocked-LLM unit + wiring + API tests
  eval/                                  online, real-LLM evaluation across 8 goals
  render.yaml                              Render Web Service config for api.py

studyos-frontend/
  src/
    App.jsx, LearnerGate.jsx             identity + top-level routing
    PathsList.jsx, NewPathForm.jsx       topic list + create-new-topic flow
    Dashboard.jsx, StageRow.jsx          per-path curriculum timeline
    PracticeSection.jsx, PracticePanel.jsx   per-stage practice flow
    SubmissionsView.jsx                  per-stage permanent Q&A history
    api.js                               backend client
  __tests__/                             vitest + testing-library component tests
```
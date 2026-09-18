# StudyOS

An agentic system that takes an arbitrary learning goal — "teach me Python from
scratch", "I want research-level understanding of Transformers, 1hr/day" —
and produces a personalized, resource-grounded, adaptive curriculum. No
subject is hardcoded: the same graph that handles Python handles Kubernetes,
German, or compilers, because it reasons about the goal instead of looking up
a prewritten roadmap.

## What this actually is

An explicit [LangGraph](https://github.com/langchain-ai/langgraph) agent
pipeline, backed by real tools (web search, arXiv, GitHub, a sandboxed Python
executor) exposed both as in-process functions and as a genuine [MCP](https://modelcontextprotocol.io)
server, with SQLite-backed persistent learner state so progress survives a
restart.

```
goal_understanding → prerequisite_reasoning → research → resource_evaluation
   → curriculum_planning → [ practice_generation ⇄ assessment (interactive)
                              ⇄ progress_tracking_and_replan ]  (loops per concept)
```

The loop over concepts is driven by `cli.py`, not entirely inside one LangGraph
graph — see "Design decisions" below for why.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env   # fill in GROQ_API_KEY
```

Uses [Groq](https://console.groq.com) (`openai/gpt-oss-120b` by default —
override with `STUDYOS_MODEL` in `.env`) via its OpenAI-compatible chat
completions endpoint, wrapped in `llm.py`. Swapping providers again later
means editing `llm.py`'s `get_client()`/`complete()` only — nothing else in
the codebase talks to the LLM directly.

## Two ways to use it: CLI or web app

The original interface is the terminal (`cli.py`) — good for quick local
testing. There's also a full web app: a [FastAPI backend](#web-backend-apipy)
plus a [separate React frontend](../studyos-frontend) with a live-updating
dashboard, deployable to Render. Both sit on top of the exact same
`schemas.py` / `graph/` / `tools/` code — neither is a special case of the
other.

### CLI

```bash
python -m studyos.cli --learner rhea "I want to learn Transformers from the \
fundamentals and eventually understand the Attention Is All You Need paper. \
I know Python and basic neural networks, 1 hour a day."
```

Run it again with the same `--learner` and no goal text to resume exactly
where you left off — state is loaded from SQLite (`studyos_state.db` by
default).

Run the MCP server standalone, for any MCP client to connect to:

```bash
python -m studyos.mcp_server
```

### Web backend (`api.py`)

```bash
uvicorn studyos.api:app --reload --port 8000
```

By default this persists to the local SQLite file, same as the CLI. To use
Postgres instead (needed for a real deployment — see "Persistence" below),
set `DATABASE_URL` in `.env` to a Postgres connection string (a free
[Neon](https://neon.tech) database works well) before starting it.

Endpoints: `GET /learners/{id}` (state summary), `GET
/learners/{id}/goal/stream` (SSE — builds the curriculum, streaming the same
progress lines the CLI prints), `GET /learners/{id}/practice` (practice items
for the current concept), `POST /learners/{id}/practice/{item_id}/answer`
(grades one answer, saves immediately, advances/remediates once the stage is
done). No auth — a learner is just a name, matching the frontend's
username-only identity.

The frontend lives in a separate repo/folder (`studyos-frontend`) — see its
own README for local dev and deployment.

### Persistence: why the backend needs Postgres, not SQLite, in production

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

### Deploying

- **Backend**: `render.yaml` in this repo configures a Render Web Service.
  Push this repo, connect it in Render, and set the `sync: false` env vars
  (`GROQ_API_KEY`, `DATABASE_URL` from Neon, `ALLOWED_ORIGINS` — your
  frontend's URL once you have it) in the Render dashboard.
- **Frontend**: see `studyos-frontend/README.md` — deploys as a Render
  Static Site (or Vercel/Netlify), pointed at the backend's URL via
  `VITE_API_URL`.
- Order matters slightly: deploy the backend first to get its URL, use that
  for the frontend's `VITE_API_URL`, then come back and set the frontend's
  URL as the backend's `ALLOWED_ORIGINS` — they reference each other.

## Tests and evaluation — two different things

```bash
pytest tests/          # fast, offline, LLM calls mocked — checks wiring & logic
python eval/run_eval.py  # real LLM calls, real cost — checks output quality across 8 diverse goals
```

`tests/` verifies the deterministic parts are actually correct: topological
sort, cycle detection, curriculum assembly, mastery thresholds, state
persistence round-tripping, the LangGraph pipeline wiring end-to-end, and
(`test_api.py`) the FastAPI endpoints themselves — goal generation through
SSE, practice fetch, answer grading, per-answer persistence, and rejecting a
duplicate answer to an already-graded item. None of this requires an API key.
The frontend has its own separate test suite — see `studyos-frontend/README.md`.

`eval/` is different — it runs the real pipeline against goals spanning
Python, Transformers, Kubernetes, German, statistics, OS concepts, RAG, and
compilers, and reports structural metrics (no LLM involved: does the
prerequisite order hold, does every resource have a real URL) alongside
LLM-judge scores (an LLM rating curriculum quality — a cheap proxy signal,
*not* ground truth; see `eval/metrics.py` docstring for why).

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
  YouTube Data API (needs a key) is a small, isolated addition to
  `tools/`.
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

## Design decisions worth knowing before you extend this

**Why assessment isn't a LangGraph node.** Grading needs a learner's answer
per practice item, which is inherently interactive. Rather than fake this
with LangGraph's `interrupt()`/checkpointer machinery (real, but adds a
persistence layer of its own that would compete with the SQLite store this
project already needs for other reasons), `cli.py` owns the interactive loop
and calls `grade_practice_item()` directly per answer. The two LangGraph
graphs either side of it (`build_progress_graph`, `build_replan_graph`) stay
small, synchronous, and independently testable.

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

## Layout

```
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
  cli.py                          interactive terminal runner
  api.py                            FastAPI backend for the web frontend
tests/                              offline, mocked-LLM unit + wiring + API tests
eval/                                  online, real-LLM evaluation across 8 goals
render.yaml                              Render Web Service config for api.py

../studyos-frontend/     separate React app — see its own README
```

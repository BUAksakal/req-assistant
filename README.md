<p align="center">
  <img src="docs/assets/reqlens-header.svg" alt="ReqLens: AI agents that review automotive requirements" width="100%">
</p>

<p align="center">
  <a href="https://guhlixj93lndfluucdkk35.streamlit.app/"><img src="https://img.shields.io/badge/live%20demo-open-111111?logo=streamlit&logoColor=white" alt="Live demo"></a>
  <a href="https://github.com/BUAksakal/reqlens/actions/workflows/ci.yml"><img src="https://github.com/BUAksakal/reqlens/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/LangGraph-supervisor%20agent-1C3C3C" alt="LangGraph">
  <img src="https://img.shields.io/badge/LlamaIndex-agent%20%2B%20RAG-7C3AED" alt="LlamaIndex">
  <img src="https://img.shields.io/badge/LLM-Gemini-4285F4?logo=googlegemini&logoColor=white" alt="Gemini">
  <img src="https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white" alt="Docker">
</p>

<p align="center">
  <b>ReqLens reads automotive PDF specifications, extracts the requirements and finds the ones that are ambiguous or contradict each other, before they turn into expensive bugs.</b>
</p>

<p align="center">
  <a href="https://reqlens.streamlit.app/"><b>▶ Try the live demo</b></a> · upload any text-based specification PDF (max. 60 pages)
</p>

---

## What ReqLens is

ReqLens is an **end-to-end requirements review tool built around AI agents**. You upload a specification, and ReqLens:

1. **finds every requirement** in it, whatever ID format the document uses,
2. **flags vague wording** that cannot be tested (*"fast"*, *"sufficient"*),
3. lets an **AI agent search the document for contradicting requirements**,
4. lets a **supervisor agent double-check** every contradiction the first agent reports,
5. **pauses for the engineer**, who approves or rejects each finding,
6. **stores the decision**, so you can see how often the AI was right.

The AI proposes, the engineer decides. Both supervisor decisions fall back to a simple rule when no model answers, and every LLM answer is cached, so a second run of the same document costs nothing.

## The problem

Car makers send their suppliers specifications (*Lastenhefte*) with hundreds of requirements. Engineers still copy them out of the PDF by hand and check them by eye:

- Is a requirement **ambiguous**? *"The system shall brake **fast**."* How fast?
- Do two requirements **contradict** each other? One section says the warning must appear within **10 s**, another says **5 s**.

These problems are usually written by different teams, end up 40 pages apart and are found months later, during testing. ReqLens finds them in minutes and lets the engineer decide.

<p align="center">
  <img src="docs/assets/reqlens-before-after.svg" alt="Two engineers at their desks. Without ReqLens: copying requirements from the PDF into a spreadsheet and comparing 91 pairs by eye. With ReqLens: the review screen with 2 findings to approve, 45 times fewer checks" width="100%">
</p>

## How it works

<p align="center">
  <img src="docs/assets/reqlens-agent-flow.svg" alt="ReqLens workflow: PDF, classic extraction, LLM extraction, vague check, LlamaIndex conflict agent with semantic index, LangGraph supervisor agent that decides the extraction path and verifies conflicts, engineer review, report" width="100%">
</p>

The whole flow is a **LangGraph** graph. Two agents work inside it:

- a **LlamaIndex conflict agent** that searches the document on its own, and
- a **supervisor agent** that makes the routing and verification decisions.

| Step | What happens | Why this way |
|---|---|---|
| **Classic extraction** | PyMuPDF reads the text page by page, a regex finds IDs like `AEB-001` | Free, fast and deterministic. Tried first |
| **Supervisor: extraction** | Looks for *shall* sentences the regex missed. If there are any, Gemini decides: accept or switch to the LLM | The workflow chooses its own path per document |
| **LLM extraction** | Gemini reads the PDF in **8-page chunks** (1-page overlap) and returns typed `Requirement` objects. IDs are normalised, each chunk is cached | One call for a long document stopped halfway. Chunks keep it complete |
| **Ambiguity check** | Flags words such as *fast*, *about*, *sufficient* | Cheap baseline, no LLM |
| **Conflict check** | A **LlamaIndex agent** looks up related requirements through a semantic index (RAG) and decides whether they contradict. At most 12 checks per document, the most similar requirements first | The agent writes its own search query for every requirement |
| **Supervisor: verification** | Gemini takes a second look at every conflict the agent reported: `real`, `false_alarm` or `unsure`. Only clear false alarms are dropped | Fewer wrong findings, without hiding real ones |
| **Engineer review** | The workflow **pauses** (LangGraph `interrupt` + checkpointer) and resumes after the engineer's answer | LLMs can be confidently wrong. A human makes the final call |
| **Report** | Findings and decisions go into SQLite. The approval rate is the measured precision | Shows how often the AI was right |

**Guardrails.** Supervisor answers are typed (`accept` / `use_llm`, `real` / `false_alarm` / `unsure`), so the LLM cannot invent a new path. Every answer is cached per document, so a second run costs no quota. When all five Gemini models are busy, the supervisor falls back to a rule and keeps every conflict for the engineer instead of dropping it. Documents over 60 pages are refused before any LLM call.

## Results

### Extraction on real documents

| Document | Pages | Classic (regex) | LLM (Gemini) |
|---|:---:|:---:|:---:|
| [UN Regulation No. 152](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ:L_202402497) (AEBS for M1/N1 vehicles) | 38 | **0** ❌ | **144** ✅ |
| [AUTOSAR SWS StandardTypes](https://autosar.org/fileadmin/standards/R24-11/CP/AUTOSAR_CP_SWS_StandardTypes.pdf) | 29 | **0** ❌ | **24** ✅ |

- **UN R152:** 97 of 99 numbered *shall* paragraphs in the main body were found. The two missing ones are section headings. Annex requirements keep their annex (`Annex 3 3.1`), so they do not collide with the main body. No IDs were invented.
- **AUTOSAR:** all 22 requirements with an *Upstream requirements* line, plus 2 written in a different format.

The regex only knows the format it was written for. The supervisor notices this and hands the document to the LLM.

### Analysis on the example specification

[`examples/aeb_lastenheft.pdf`](examples/aeb_lastenheft.pdf): 18 requirements for an emergency braking system, with errors seeded on purpose and an [answer key](eval/ground_truth.jsonl).

| Seeded problem | Found |
|---|:---:|
| Conflicts (`AEB-001 ↔ AEB-002`, `AEB-014 ↔ AEB-018`) | **2 / 2** ✅ |
| Ambiguous wording | **1 / 3** ⚠️ |
| Untestable requirement | not checked yet |

### Benchmark: three levels, with decoys

Inspired by [GAIA](https://huggingface.co/papers/2311.12983): one specification with an unambiguous [answer key](bench/acc_benchmark.yaml), conflicts at three levels of difficulty, and **decoys**, pairs that look like conflicts but are not. Guessing "conflict" everywhere costs precision.

[`bench/acc_benchmark.pdf`](bench/acc_benchmark.pdf): 25 requirements for an Adaptive Cruise Control, IDs like `ACC-R-010`.

| Level | Conflicts found by the agent | Kept by the supervisor | Vague wording found |
|---|:---:|:---:|:---:|
| 1: next to each other | 2/2 | 2/2 | 2/2 |
| 2: pages apart | 2/2 | 2/2 | 1/2 |
| 3: only visible after a unit conversion (`0.3 g` vs `2.5 m/s²`) | 1/2 | 1/2 | 0/2 |

- **Extraction:** 25/25 requirements, the regex found 0.
- **Conflict agent:** 5 of 6 conflicts found, **all 5 correct**, no decoy reported.
- **Supervisor:** keeps all 5 correct conflicts, and rejects **2/2 decoys** when they are handed to it as conflicts.
- **Time:** 57 s from PDF to engineer review on a fresh run.

**What the benchmark changed.** The first version of the supervisor only accepted a conflict "if a system cannot satisfy both", so it dropped *within 2 s* vs *no later than 4 s*. The benchmark measured the damage, the prompt was changed, and the same run was scored again:

| Supervisor | Correct conflicts kept | Decoys rejected |
|---|:---:|:---:|
| v1: "conflict only if both cannot be met" | 3/5 | not measured |
| v2: "drop only clear false alarms, keep when unsure" | **5/5** | **2/2** |

Still open: one unit-conversion conflict (`5 m/s` vs `30 km/h`) is not found, and the word list misses vague phrases at level 2 and 3.

```bash
uv run reqlens bench            # score one run (answers are cached)
uv run reqlens bench --fresh    # ask every LLM answer again, to measure run-to-run variation
```

## Quick start

### Live demo

Open **[the live demo](https://guhlixj93lndfluucdkk35.streamlit.app/)**, upload a specification PDF and click **Analyze**. The demo runs on the free Gemini tier, so it may answer slowly or ask you to try again later.

### Local

```bash
git clone https://github.com/BUAksakal/reqlens.git
cd reqlens
uv sync
echo "GEMINI_API_KEY=your-key" > .env   # free key: https://aistudio.google.com/apikey
```

```bash
uv run streamlit run app.py                               # web interface
uv run reqlens parse examples/aeb_lastenheft.pdf          # classic extraction
uv run reqlens parse path/to/spec.pdf --ai                # LLM extraction
uv run reqlens analyze examples/aeb_lastenheft.pdf        # full workflow with review
uv run reqlens history                                    # past runs and approval rate
```

### Docker

```bash
docker build -t reqlens .
docker run --rm -p 8501:8501 --env-file .env reqlens      # open http://localhost:8501
```

The image runs as a non-root user and contains no secrets: `.env`, the database and all PDFs are excluded by `.dockerignore`, and the API key is only passed at run time.

<details>
<summary><b>Example CLI session</b></summary>

```text
$ uv run reqlens analyze examples/aeb_lastenheft.pdf

AEB-003: vague words ['fast']
Real problem? [y/N]: y

AEB-018: AEB-014: Both requirements specify different maximum time limits
(5 s vs 10 s) for displaying the same failure warning signal.
Real problem? [y/N]: y

18 requirements found.
AEB-003: vague words ['fast']
AEB-018: AEB-014: Both requirements specify different maximum time limits ...
2 findings approved by the engineer.
Saved as run #1 in reqlens.db
```

</details>

## Deployment

| | |
|---|---|
| **Live demo** | Streamlit Community Cloud, deployed from `main`. Every merged pull request updates the demo |
| **Secrets** | The Gemini key lives in the platform's secret store, never in the code or the repository |
| **Container** | The same app ships as a Docker image, ready for any container host (AWS, Azure, on-premise) |
| **CI** | GitHub Actions runs ruff and pytest on every pull request |
| **Abuse protection** | At most 3 analyses per visitor session and 25 per day for all visitors together, counted in SQLite, so a bot that reloads the page cannot use up the free Gemini quota |
| **Privacy** | Each visitor only sees their own analyses. Uploaded file names and requirement IDs are escaped before they are shown, and every SQL query is parameterized |

## Tech stack

| Area | Tools |
|---|---|
| PDF reading | PyMuPDF |
| LLM and embeddings | Gemini (five models with automatic fallback, `gemini-embedding-001`) |
| Agents and orchestration | LangGraph (supervisor agent, conditional edges, `interrupt`, checkpointer, streaming) |
| Document agent and RAG | LlamaIndex (`FunctionAgent`, `VectorStoreIndex`, structured output) |
| Storage | SQLite (runs, review decisions, LLM answer cache) |
| Interface | Streamlit (web), typer (CLI) |
| Data models | pydantic |
| Deployment | Docker, Streamlit Community Cloud |
| Engineering | uv, pytest, ruff, pre-commit, GitHub Actions, branch → PR workflow |

<details>
<summary><b>Project structure</b></summary>

```text
app.py                    # Streamlit web interface with live workflow view
src/reqlens/
├── models.py             # Requirement model (pydantic)
├── pdf_reader.py         # PyMuPDF reading + classic regex extraction
├── ai_parser.py          # chunked LLM extraction with structured output
├── llm.py                # Gemini models, embeddings, fallback on 429/503
├── ambiguity.py          # vague word check
├── requirement_index.py  # semantic index over requirements
├── analysis_agent.py     # LlamaIndex conflict agent
├── supervisor.py         # supervisor agent: extraction decision, conflict verification
├── benchmark.py          # GAIA-style benchmark scoring (reqlens bench)
├── workflow.py           # LangGraph workflow with engineer review
├── cache.py              # LLM answer cache
├── storage.py            # SQLite runs and review decisions
└── cli.py                # reqlens parse / analyze / bench / history
tests/                    # pytest, no API key needed
scripts/build_examples.py # renders the example spec PDF and answer keys from YAML
scripts/build_benchmark.py # renders the benchmark PDF and answer key
examples/                 # example specification (YAML source + PDF)
eval/                     # answer keys
bench/                    # benchmark specification, PDF and answer key
Dockerfile                # container image for the web interface
```

</details>

## Limitations

Being honest about what does not work yet:

- **Ambiguity** uses a word list and misses phrases like *"as smooth as possible"* or *"appropriately"*.
- **LLM answers vary** between runs, and the conflict agent misses conflicts that need a unit conversion (`5 m/s` vs `30 km/h`). That is why the engineer review exists.
- **The same pair can be checked twice** (`A ↔ B` and `B ↔ A`) and get two different verdicts.
- **Free Gemini tier** is limited (few requests per day, frequent `503`). ReqLens switches between five models and caches every answer, but a full analysis can take minutes.
- **Document size:** the LLM reads at most **60 pages** per document (9 requests) and uploads are capped at **20 MB**, so one file cannot use up the daily quota. Longer specifications have to be split.
- **Demo history** is stored inside the running app and resets when the demo restarts.
- The conflict analysis has been measured on two fictional specifications (example and benchmark), not yet on a real one.

## Roadmap

<p align="center">
  <img src="docs/assets/reqlens-voyage.svg" alt="ReqLens roadmap as a treasure map: a ship with the 001 agent and a PDF sails past eight finished islands towards an X that marks what comes next" width="100%">
</p>

<details>
<summary><b>Roadmap as a list</b></summary>

- [x] Classic and LLM extraction
- [x] LlamaIndex conflict agent with semantic search
- [x] LangGraph workflow with engineer review
- [x] SQL storage of runs and review decisions (measured precision)
- [x] Streamlit web interface
- [x] Supervisor agent with guardrails
- [x] Analysis on a real regulation (UN R152)
- [x] Docker image and live demo
- [x] GAIA-style benchmark with three levels and decoys
- [x] Supervisor keeps conflicts it is unsure about (measured with the benchmark)
- [ ] Check each requirement pair only once
- [ ] LLM-based ambiguity check
- [ ] Deployment on AWS

</details>

---

<sub>The example specification and the company *Musterwerk Automotive GmbH* are fictional and were written for testing. AUTOSAR and UN documents are not included in this repository.</sub>

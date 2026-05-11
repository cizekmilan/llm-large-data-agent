# LLM Agent for Large-Scale Data Processing on Models with Limited Context

> Experimental orchestration framework exploring how LLM agents can process datasets significantly larger than the model context window using iterative retrieval and semantic reduction.


# Motivation

Modern LLMs are powerful reasoning systems, but they are still limited by:

- finite context windows
- expensive token usage
- limited reliability when processing large datasets
- inability to safely paginate external APIs autonomously

In real-world environments, external systems often return:

- thousands of records
- large JSON structures
- verbose logs
- ticket histories
- monitoring data
- enterprise API payloads

These datasets frequently exceed the context capacity of the model.

The goal of this project is to explore an architecture that allows an LLM agent to:

- work with large-scale external data
- iteratively load and process data
- semantically reduce tool outputs
- preserve only relevant information
- continue reasoning within limited context budgets


# Main Idea

The project separates the system into multiple specialized layers:

| Component | Responsibility |
|---|---|
| **LLM1 (Main Agent / Orchestrator)** | reasoning, planning, tool selection |
| **Tool Adapter** | OpenAPI → tool schema conversion |
| **Tool Executor** | API/MCP execution, pagination, chunk orchestration |
| **LLM2 (Reducer)** | semantic reduction and aggregation of large payloads |

Instead of allowing the main model to directly process extremely large datasets, the architecture:

1. loads data iteratively
2. processes them in chunks
3. semantically compresses results
4. injects only reduced outputs back into the agent context


# Architecture Overview

![Architecture Diagram](docs/architecture_v3.svg)

Core concepts:

- separation of orchestration and reduction
- adaptive pagination
- chunk-based processing
- semantic reduction pipeline
- OpenAPI-driven tool generation
- short-term vs long-term memory separation


# Key Features

## OpenAPI Tool Generation

The framework dynamically parses `openapi.json` and generates:

- tool schemas for the LLM
- internal executor metadata

This allows external APIs to be integrated with minimal changes.


## Internal Pagination Handling

The LLM itself is intentionally isolated from pagination logic.

Pagination logic is handled internally by the executor layer:

- metadata retrieval (`meta_only`)
- token estimation
- adaptive chunk sizing
- iterative API calls
- chunk orchestration

This significantly improves reliability compared to prompt-based pagination.


## Semantic Data Reduction

Large tool outputs are processed by a secondary LLM reducer.

The reducer:

- removes irrelevant data
- preserves linking identifiers
- compresses verbose structures
- aggregates repeated information
- minimizes context growth

This enables multi-step reasoning over datasets that would otherwise exceed model limits.


## Context Management

The project distinguishes between:

### Short-Term Memory

Working memory used during orchestration:

- user messages
- tool calls
- tool outputs
- intermediate reasoning

### Long-Term Memory

Persistent conversation history:

- user queries
- final assistant answers

This prevents uncontrolled context growth.


# Project Structure

```text
/
├── agent.py                         # Main orchestration agent
├── reducer.py                       # Semantic reducer (LLM2)
├── misc.py                          # Shared helper functions
├── mock_api.py                      # Mock OpenAPI server
│
├── mockdata/                        # Large mock datasets
│   ├── customer4_anonymized.json
│   └── ...
│
├── logs/
│   └── debug_*.log                  # Runtime logs
│
├── docs/
│   ├── architecture_v3.png          # Architecture diagram in PNG format
│   └── architecture_v3.svg          # Architecture diagram in SVG format
│
├── .env                             # Runtime configuration
├── requirements.txt
└── README.md
```


# Workflow

## 1. User Query

The user sends a query to the orchestrator.

Example:

```text
Zjisti vše o uživateli Baláž.
```


## 2. Tool Selection

LLM1 decides whether external data are required.

The model receives:

- dynamically generated tools
- tool descriptions
- parameter schemas


## 3. Metadata Retrieval

If the endpoint supports pagination:

```text
GET /tickets?meta_only=true
```

The API returns:

- estimated data token size
- total item count
- optional data path metadata


## 4. Adaptive Chunking

The executor calculates:

- average tokens per item
- optimal chunk size
- number of API calls required


## 5. Iterative Data Loading

The executor retrieves data in pages:

```text
GET /tickets?offset=0&limit=29
GET /tickets?offset=29&limit=29
GET /tickets?offset=58&limit=29
...
```


## 6. Semantic Reduction

Each chunk is processed by the reducer model.

Reducer responsibilities:

- semantic filtering
- summarization
- aggregation
- removal of irrelevant payload data


## 7. Final Aggregation

Reduced chunk outputs are merged and injected back into the orchestrator context.

The main agent then continues reasoning using compressed information.


# Example Reduction Statistics

The following values are approximate examples from experimental runs.

| Dataset | Original Tokens | Reduced Tokens | Reduction |
|---|---:|---:|---:|
| Large ticket dataset | 355,000 | 18,000 | 94.9% |
| Customer communication history | 120,000 | 9,500 | 92.1% |
| Monitoring logs | 210,000 | 14,000 | 93.3% |

The actual reduction ratio depends on:

- dataset structure
- user query specificity
- reducer prompt quality
- aggregation strategy


# Logging

The project includes runtime logging for:

- selected tools
- API calls
- pagination
- chunk processing
- token reduction statistics
- reducer activity
- error handling

Example log output:

```text
[TOOL SELECTED] get_tickets
[META] total_items=261 total_tokens_est=355116
[STRATEGY] PAGING ACTIVATED
[PAGE] offset=0 limit=29 items=29
[TOKEN CHANGE] 39135 -> 1842 (-95.3%)
```


# Current Limitations

This project is currently experimental.

Known limitations:

- reducer outputs are not fully deterministic
- token estimation is heuristic
- no recursive reduction strategy yet
- no retry orchestration layer
- structured output reliability depends on model behavior
- context overflow handling is still evolving


# Future Work

Planned improvements:

- recursive reduction pipelines
- vector memory integration
- automatic retry strategies
- context-aware reducer prompts
- structured JSON schema enforcement
- streaming chunk processing
- distributed tool execution
- MCP-native adapters


# Requirements

- Python 3.10+
- OpenAI-compatible Responses API
- FastAPI
- Uvicorn


# Running the Mock API

```bash
uvicorn mock_api:app --port 9001 --reload
```


# Running the Agent

```bash
python agent.py
```


# Environment Variables

Example `.env`:

```env
LLM_API_BASE_URL=http://127.0.0.1:8000/v1
LLM_API_KEY=dummy
LLM_NAME=gpt-4.1-mini
LLM_MAX_CONTEXT=131072
LLM_CONTEXT_UTILIZATION=0.25
LLM_TEMPERATURE=0.0
LLM_TOP_P=1.0
LLM_TIMEOUT=60
```


# Research Goal

This project explores whether LLM agents can reliably operate over datasets that significantly exceed their native context window by combining:

- iterative retrieval
- semantic compression
- orchestration loops
- adaptive chunking
- external tool integration

The project focuses primarily on:

- orchestration reliability
- context preservation
- scalable tool usage
- semantic reduction strategies

rather than traditional chatbot interaction.


# Status

Current status:

- architecture prototype implemented
- OpenAPI integration functional
- adaptive pagination functional
- reducer pipeline functional
- semantic chunk reduction experimental


# License

Experimental / educational project.


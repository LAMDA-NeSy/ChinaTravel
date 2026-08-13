# ChinaTravel

[English](README.md) | [简体中文](README.zh-CN.md)

**ChinaTravel: An Open-Ended Travel Planning Benchmark with Compositional
Constraint Validation for Language Agents** (ICLR 2026)

ChinaTravel is a real-world travel-planning benchmark for language agents. It
combines structured sandbox data, natural-language requests, executable DSL
constraints, commonsense validation, and preference-based scoring.

[![Webpage](https://img.shields.io/badge/Webpage-Visit-blue)](https://www.lamda.nju.edu.cn/shaojj/chinatravel/)
[![Paper](https://img.shields.io/badge/Paper-View-red)](https://arxiv.org/abs/2412.13682)
[![Dataset](https://img.shields.io/badge/Dataset-HuggingFace-yellow)](https://huggingface.co/datasets/LAMDA-NeSy/ChinaTravel)
[![TPC@IJCAI2026](https://img.shields.io/badge/Competition-TPC%40IJCAI2026-green)](https://chinatravel-competition.github.io/IJCAI2026/)

## Post-Competition Release

This branch consolidates the engineering work completed during and after
TPC@IJCAI 2026:

- a refactored OpenAI-compatible model runtime supporting Chat Completions and
  the Responses API;
- explicit Chinese and English query/sandbox selection through `--lang zh` and
  `--lang en`;
- the final evaluator fixes for entity grounding, activity chronology,
  transport validation, meal counting, hard-logic execution, invalid-plan
  scoring, deterministic data loading, and evaluation caches;
- the modular synthetic-query generator, constraint catalog, audit pipeline,
  and release exporter;
- the Chinese-to-English DSL/query translation, rule and LLM audit, selective
  repair, conservative re-audit, and human-adjudication tools;
- a reproducible exporter for canonicalized English sandbox data.

Generated competition data, private test splits, API credentials, and local
model outputs are not committed to this branch.

## Repository Map

| Path | Purpose |
| --- | --- |
| `chinatravel/` | Core agents, bilingual sandbox, DSL, and evaluators |
| `agent_env/` | Structured tools, CLI/HTTP/MCP adapters, and split harness |
| `synthetic_query_generation/` | Synthetic query generation and independent audit |
| `scripts/` | Translation, repair, and fixed-sandbox export utilities |
| `tests/` | Regression tests for evaluator, language, DSL, and data tools |
| `run_exp.py`, `run_tpc.py` | Agent execution entrypoints |
| `eval_exp.py`, `eval_tpc.py` | Standard and TPC evaluation entrypoints |

## Installation

Python 3.12 or newer is required by `pyproject.toml`.

With `uv`:

```bash
uv sync
source .venv/bin/activate
```

Or with Conda and pip:

```bash
conda create -n chinatravel python=3.12
conda activate chinatravel
pip install -r requirements.txt
```

Download the official sandbox data from [Google Drive](https://drive.google.com/drive/folders/1bJ7jA5cfExO_NKxKfi9qgcxEbkYeSdAU)
or [NJU Drive](https://box.nju.edu.cn/d/dd83e5a4a9e242ed8eb4/), then place it as:

```text
chinatravel/environment/database/       # Chinese sandbox
chinatravel/environment/database_en/    # English sandbox
```

The requested language must exist locally. The standard run/evaluation scripts
default to Chinese for backward compatibility; pass `--lang en` explicitly for
English data.

## Model Runtime

ChinaTravel accepts built-in aliases such as `deepseek`, `gpt-4o`, and
`glm4-plus`, or any model exposed through an OpenAI-compatible endpoint.

```bash
export OPENAI_API_KEY="your-key"
export OPENAI_BASE_URL="https://your-provider.example/v1"

# chat: OpenAI-compatible Chat Completions (default)
# responses: OpenAI Responses API
export CHINATRAVEL_OPENAI_WIRE_API="chat"

# Optional provider-specific token field.
export CHINATRAVEL_OPENAI_TOKEN_LIMIT_ARG="max_tokens"
```

Additional runtime variables include:

- `CHINATRAVEL_OPENAI_MODEL`: default model when `--llm` is omitted;
- `CHINATRAVEL_OPENAI_API_KEY`: key override before `OPENAI_API_KEY`;
- `CHINATRAVEL_OPENAI_BASE_URL`: base URL override before `OPENAI_BASE_URL`;
- `CHINATRAVEL_OPENAI_RAISE_ERRORS=1`: surface provider errors while debugging;
- `CHINATRAVEL_OPENAI_STRICT_TOOLS=1`: export strict OpenAI tool schemas.

Responses mode requires `openai>=1.66.0`. API keys must remain in environment
variables or ignored local configuration files.

## Running Agents

Run an English or Chinese split:

```bash
python run_exp.py \
  --splits easy \
  --agent LLMNeSy \
  --llm provider/model-name \
  --lang en

python run_exp.py \
  --splits easy \
  --agent LLMNeSy \
  --llm provider/model-name \
  --lang zh
```

To expose oracle annotations to an algorithm that explicitly requires them:

```bash
python run_exp.py \
  --splits human \
  --agent LLM-modulo \
  --llm provider/model-name \
  --refine_steps 10 \
  --oracle_translation \
  --lang en
```

`--oracle_translation` exposes `hard_logic_py` and `hard_logic_nl`. Normal
participant-facing runs should omit it. Query files must use the current JSON
schema; when present, `hard_logic_py` must be a JSON list rather than a
string-encoded list.

Results are written under `results/<method>/`.

## Evaluation

Evaluate a generated result directory with the same language as the query and
sandbox data:

```bash
python eval_exp.py --splits human --method YOUR_METHOD --lang en
python eval_tpc.py --splits tpc_phase1 --method YOUR_METHOD --lang en
```

The TPC evaluator reports schema, commonsense, hard-constraint, FPR, and
preference metrics. Plans that fail required validity checks contribute zero to
the affected preference average; preference scores are not a bypass for an
invalid itinerary.

The hardened evaluator additionally enforces:

- database grounding for referenced entities and transports;
- chronological, non-overlapping activities and valid transport departure
  ordering;
- valid intercity transport placement and type-independent position handling;
- at most one hotel breakfast per day for the free-breakfast exception;
- canonical bilingual concept values and temporary legacy aliases;
- safe DSL execution and legacy apostrophe normalization.

## Agent Environment and Harness

`agent_env` exposes ChinaTravel through structured Python, CLI, HTTP, MCP, Chat
Completions tool-call, and Responses function-call interfaces.

```bash
python -m agent_env --lang en tools
python -m agent_env --lang en call attractions_keys '{"city":"Shanghai"}'
CHINATRAVEL_LANG=en python -m agent_env.mcp_stdio
```

For split-level harness execution:

```bash
cp agent_env/config.toml.example agent_env/config.toml
python agent_env/scripts/solve_script_with_harness.py
```

The tracked example defaults to English. The local `config.toml` is ignored
because it may contain provider credentials. See the
[Agent Environment guide](agent_env/README.md) for OpenCode, Codex, resume,
output, HTTP, and MCP details.

## Synthetic Query Generation

The generator samples executable constraints only from already valid seed
plans, validates every candidate, validates the final combination again, and
writes an auditable manifest.

```bash
python -m synthetic_query_generation seed-queries \
  --output-dir /tmp/chinatravel_seed_queries \
  --num-records 100 \
  --lang en \
  --seed 2026

python -m synthetic_query_generation from-plans \
  --plans-dir results/seed_planner \
  --output-dir /tmp/chinatravel_synthetic \
  --num-records 100 \
  --lang en \
  --seed 2026 \
  --copy-seed-plans

python -m synthetic_query_generation.audit \
  --dataset-dir /tmp/chinatravel_synthetic \
  --expected-records 100 \
  --profile full \
  --lang en
```

Constraint families and individual template keys can be enabled, disabled, or
prioritized independently. See [Synthetic Query Generation](synthetic_query_generation/README.md).

## Translation and Data Repair

The translation pipeline supports OpenAI-compatible Chat Completions APIs,
custom `base_url`, headers, model parameters, concurrency, and top-level
`extra_body` request fields. It combines deterministic checks with LLM review
and changes only records selected by the configured audit policy.

```bash
cp translation_api_config.example.json translation_api_config.json
export TRANSLATION_API_KEY="your-key"

python scripts/build_translation_assets.py
python scripts/audit_phase1_translations.py
python scripts/repair_phase1_translations.py
```

See [Translation and Audit Pipeline](scripts/TRANSLATION_PIPELINE.md).

To export canonicalized English sandbox data without modifying the source:

```bash
python scripts/export_fixed_sandbox.py /tmp/ChinaTravel_sandbox_en_fixed \
  --archive /tmp/ChinaTravel_sandbox_en_fixed.zip
```

The archive contains a manifest, change report, and checksums. See
[Fixed Sandbox Export](scripts/SANDBOX_EXPORT.md).

## Tests

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python -m compileall -q chinatravel agent_env scripts synthetic_query_generation tests
```

The regression suite covers bilingual propagation, query resolution, evaluator
grounding and scoring, chronology, meal limits, performance caches, safe DSL
control flow, synthetic constraints, and translation repair.

## Documentation

- [Chinese README / 中文说明](README.zh-CN.md)
- [Environment](chinatravel/environment/readme.md)
- [Constraint verification](chinatravel/symbol_verification/readme.md)
- [Agent environment](agent_env/README.md)
- [Synthetic query generation](synthetic_query_generation/README.md)
- [Translation and audit](scripts/TRANSLATION_PIPELINE.md)
- [Fixed sandbox export](scripts/SANDBOX_EXPORT.md)
- [Post-competition release validation](docs/RELEASE_VALIDATION.md)
- [TPC@AIC 2025](TPC@AIC2025/readme.md)

## Competition Archives

- [TPC@IJCAI 2026](https://chinatravel-competition.github.io/IJCAI2026/)
- [TPC@IJCAI 2025](https://chinatravel-competition.github.io/IJCAI2025/)

## Contact

For questions, contact [Jie-Jing Shao](mailto:shaojj@lamda.nju.edu.cn),
[Bo-Wen Zhang](mailto:221900200@smail.nju.edu.cn), or
[Xiao-Wen Yang](mailto:yangxw@lamda.nju.edu.cn).

## Citation

```bibtex
@inproceedings{shao2026chinatravel,
  title     = {ChinaTravel: An Open-Ended Travel Planning Benchmark with Compositional Constraint Validation for Language Agents},
  author    = {Jie-Jing Shao and Bo-Wen Zhang and Xiao-Wen Yang and Baizhi Chen and Siyu Han and Pang Jinghao and Wen-Da Wei and Guohao Cai and Zhenhua Dong and Lan-Zhe Guo and Yu-Feng Li},
  booktitle = {The Fourteenth International Conference on Learning Representations},
  year      = {2026},
  url       = {https://openreview.net/forum?id=0YRVlxY9BH}
}
```

# Translation and Audit Pipeline

[English](TRANSLATION_PIPELINE.md) | [简体中文](TRANSLATION_PIPELINE.zh-CN.md)

The scripts in this directory preserve the Phase 1 Chinese-to-English data
translation, validation, repair, and human adjudication workflow. API keys are
read only from the environment; do not add them to configuration files.

## Configuration

Copy `translation_api_config.example.json` to
`translation_api_config.json`, then set the environment variable named by
`api.api_key_env`. The configuration supports OpenAI-compatible Chat
Completions endpoints, custom base URLs, headers, model names, concurrency,
token fields, and additional top-level request body fields through
`extra_body`.

```bash
cp translation_api_config.example.json translation_api_config.json
export TRANSLATION_API_KEY="your-key"
```

The local configuration is ignored by Git. It can independently override API
parameters for translation, audit, repair, and thinking-enabled re-audit.

## Workflow

1. Build the DSL dictionary and translated query records:

   ```bash
   python scripts/build_translation_assets.py
   ```

2. Run deterministic checks and the configured LLM audit:

   ```bash
   python scripts/audit_phase1_translations.py
   ```

3. Repair only records selected by the audit and verify the repairs:

   ```bash
   python scripts/repair_phase1_translations.py
   ```

4. Re-audit rejected candidates conservatively, or export them for review:

   ```bash
   python scripts/reaudit_phase1_translations.py
   python scripts/export_phase1_translation_review.py
   ```

5. Apply the reviewed decisions to produce a final data directory:

   ```bash
   python scripts/apply_phase1_human_adjudication.py
   ```

`repair_translated_dsl.py` is a separate deterministic utility for rebuilding
syntax-invalid translated DSL expressions from the canonical Chinese source.
All scripts accept path overrides; run a script with `--help` for details.

## Conservative Change Policy

The pipeline does not rewrite every record flagged by one LLM call. Repair
candidates must match the configured statuses and verification policy. The
two-stage re-audit keeps uncertain cases as `manual_review`, and the human
adjudication step records the final set of changes. This preserves already
correct translations whenever possible.

# prompts

LLM prompt definitions and JSON Schema response contracts. Separated from business logic so prompts can be reviewed, versioned, and iterated independently.

## Structure

### `screening/`

| File | Used by | Defines |
|---|---|---|
| `triage.py` | `screening/filter.py` | Title triage system prompt, response schema, payload builder |
| `enrich.py` | `screening/enrich.py` | JD enrichment system prompt, response schema, payload builder |
| `rank.py` | `screening/rank.py` | Ranking system prompt (3D scoring), response schema, payload builder |

### `application/`

| File | Used by | Defines |
|---|---|---|
| `question_mapping.py` | `application/easy_apply/answers.py`, `application/easy_apply/fill.py` | Question mapping system prompt, response schema, option resolve prompt, context-aware payload builder |

## Convention

Each file follows the same structure:
1. `*_RESPONSE_SCHEMA` — JSON Schema dict for `response_format.json_schema` (strict mode)
2. `*_SYSTEM_PROMPT` — system message string
3. `build_*_user_payload()` — function that formats domain data into the LLM user message

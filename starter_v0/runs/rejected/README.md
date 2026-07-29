# Rejected runs — not part of the version log

Four v0 attempts that failed the lab gate `provider_error_cases == 0`. Kept as
evidence of the provider debugging, excluded from `artifacts/version_log.csv` and
from the analysis CSV.

## 1× `gemini / gemini-3.5-flash` — `provider_error_cases = 10`

The Gemini free tier allows 5 requests per minute. `run_eval` fires 20 cases
back-to-back, so half the suite came back `429 RESOURCE_EXHAUSTED` and dropped out
of `measured_cases`. Adding a 13s client-side throttle plus retry made the run
complete, but a single 20-case run then took ~19 minutes, which is not workable
for six base runs plus the group and extension suites.

## 3× `groq / llama-3.3-70b-versatile` — `provider_error_cases = 1`

Case `M02_carryover_timeframe` failed every time with `400 tool_use_failed`: the
model emitted `<function=lookup,{...}>` pseudo-syntax instead of a real tool call
and Groq's parser rejected it. Bounded retries in
`providers/openai_provider.py` did not clear it — the malformed generation
reproduced on that prompt across attempts.

## Resolution

Switched the Groq default model to `openai/gpt-oss-120b`, which uses native tool
calling. Accepted baseline:
`runs/v0_B_base_groq_20260729T111423811494.json` —
`provider_error_cases = 0`, `measured_cases = 20/20`, `case_accuracy = 0.70`.

All six reported runs (v0–v5) use the same provider and model, so their metrics
are comparable.

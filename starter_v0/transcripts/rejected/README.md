# Rejected transcript

`v6_groq_20260729T115025083572` — a retry of the three live scenarios on
`groq / llama-3.3-70b-versatile` (a different model was chosen because Groq's
token-per-day cap is per model and `openai/gpt-oss-120b` was exhausted).

Turn 1 failed with `400 tool call validation failed: parameters for tool
social_search did not match schema: /limit: expected integer`. llama-3.3-70b
emits a non-integer for `limit`, so this model is not usable for the live demo
either. The run was stopped to preserve the remaining daily quota.

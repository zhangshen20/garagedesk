# Feedback on Nebius Token Factory and NVIDIA tooling

Required by the hackathon submission. Observations so far; the live-test section is filled in after running `backend/scripts/live_smoke.py` against Token Factory.

## Nebius Token Factory

**What worked**
- OpenAI-compatible endpoint meant zero SDK friction: the standard `openai` Python client with `base_url` set, and function calling in the usual shape.
- Having Nano, Super and Ultra behind one key made the "right model per job" design cheap to try.

**What was confusing**
- Exact Nemotron model ids are hard to find in the docs; the marketing page shows one id in a code sample and the rest only in URL-encoded catalogue links, with inconsistent casing (`nvidia/Nemotron-3_5-Lightning` vs `nvidia/nemotron-3-super-120b-a12b`). A single "models and ids" table in the docs would save every team an hour.
- `/models` in the docs site returned an error when fetched programmatically during the build.

**Live-test notes** (to fill): latency per tier, tool-call argument quality, any JSON-mode quirks, `<think>` handling, cost per customer interaction.

## NVIDIA Nemotron

**What worked / what to improve** (to fill after live test): instruction following on the per-channel style rules (phone vs SMS), reliability of multi-step tool chains (find customer → availability → book), quality of the Ultra daily report versus Super.

## Suggestions
- Publish a tool-calling reliability note per model (how often arguments are well-formed JSON, whether parallel tool calls are supported).
- A "small business agent" cookbook recipe: Nano classify → Super act → Ultra summarise is a pattern many apps will want.

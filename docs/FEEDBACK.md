# Feedback on Nebius Token Factory and NVIDIA tooling

Required by the hackathon submission. The live-test findings come from running `backend/scripts/live_smoke.py` against Token Factory on 2026-10-11. Findings from building the owner app (voice, job card photos, approvals) are added as those features land.

## Nebius Token Factory

**What worked**
- OpenAI-compatible endpoint meant zero SDK friction: the standard `openai` Python client with `base_url` set, and function calling in the usual shape.
- Having Nano, Super and Ultra behind one key made the "right model per job" design cheap to try.

**What was confusing**
- Exact Nemotron model ids are hard to find in the docs; the marketing page shows one id in a code sample and the rest only in URL-encoded catalogue links, with inconsistent casing (`nvidia/Nemotron-3_5-Lightning` vs `nvidia/nemotron-3-super-120b-a12b`). A single "models and ids" table in the docs would save every team an hour.
- `/models` in the docs site returned an error when fetched programmatically during the build.
- There is no speech-to-text or text-to-speech model in the catalogue (checked 2026-10-12). Our owner doesn't type, so voice is the main input; we had to use the iPhone's own dictation and Twilio's speech recognition instead. A hosted Whisper-class model next to Nemotron would let a voice-first app keep the whole pipeline on Nebius.
- The catalogue does include vision models (MiniCPM-V 4.5, Gemma 3 27B), which is what makes "photograph the paper job card" possible on the same key.

**Live-test notes** (2026-10-11, `backend/scripts/live_smoke.py`, 8 agent turns plus one daily report)
- All three configured ids (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, `nvidia/nemotron-3-super-120b-a12b`, `nvidia/Nemotron-3-Ultra-550b-a55b`) were listed by `GET /v1/models` and accepted as-is.
- Latency per call: Nano 0.3-0.6 s with thinking off (0.5-1.1 s with it on); Super 0.7-1.5 s per tool step, so a full agent turn of 1-3 tool calls plus the answer took 2-5 s (8 s for the parts order, which includes a Tavily search and a Nano extraction); Ultra 4-5 s for the whole daily report. The full scripted run took about 36 s.
- Reasoning tokens count against `max_tokens`, and it is easy to miss. Our first run lost two things to it: Nano's JSON-mode classifier came back as truncated JSON at `max_tokens=60`, and Nano returned `content=None` with `finish_reason=length` when extracting prices from search results at 600 tokens. Ultra spent about 1,200 reasoning tokens before writing, so the daily report was cut off mid-sentence at 900. Fixes: pass `chat_template_kwargs: {"enable_thinking": false}` for the Nano one-shot jobs (7 output tokens instead of 50-70, and roughly half the latency) and give Ultra a 3,000 token budget. A doc note saying that reasoning shares the completion budget, and how to turn it off per request, would have saved us a debugging round.
- Reasoning comes back in a separate `reasoning_content` field and never as `<think>` tags in `content`, so our tag stripping was never needed. `usage.completion_tokens_details.reasoning_tokens` is reported for Super and Ultra but not for Nano.
- JSON mode on Nano pads its output with newlines and indentation, which is another reason to keep a little headroom over the expected size.

## NVIDIA Nemotron

**What worked**
- Every multi-step tool chain completed on the first try with well-formed arguments: find customer, then availability, then book (with the slot chosen on the customer's next message); job status by rego; lookup price, then order parts, then a pending owner approval; get job, then mark done, then issue the GST invoice. Super picked the right ids from earlier tool results and never invented a booking reference.
- Super followed the per-channel style rules: one or two short spoken sentences on the phone channel, a short plain-text answer over SMS, and a friendlier multi-line answer in the web chat.
- Ultra's daily report was the standout. From a raw JSON snapshot it named the overdue debtor and amount, tied the pending parts order to the waiting job, flagged low stock, listed tomorrow's drop-offs by bay, and ended with a specific suggestion (approve the pads order today and ring the one overdue customer, whose $682 covers most of the day's cash out). It stayed under the word limit and in the requested Markdown shape.

**What to improve**
- Super echoed raw cents ("6900 c") in owner replies until the system prompt explicitly said to write dollars. Worth knowing when tool results use integer cents.
- Super sometimes uses Markdown tables and emoji even in plain-text channels; we keep the channel instruction short and explicit.
- Ultra occasionally adds a detail that is a plausible inference rather than a fact in the snapshot (for example, which services the completed jobs were). For an owner-facing report that is acceptable, but it is the one place we saw anything like invention.

## Building the owner app (2026-10-12 onwards)

*Pending: findings from the Talk-to-Invoice, job card photo and approval work are added here as those features land.*

## Suggestions
- Add a speech-to-text model to Token Factory. Voice-first apps for people who don't type are a natural fit for Nemotron, and today they need a second provider.
- Publish a tool-calling reliability note per model (how often arguments are well-formed JSON, whether parallel tool calls are supported).
- A "small business agent" cookbook recipe: Nano classify → Super act → Ultra summarise is a pattern many apps will want.

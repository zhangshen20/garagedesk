# Feedback on Nebius Token Factory and NVIDIA tooling

Required by the hackathon submission. The live-test findings come from running `backend/scripts/live_smoke.py` against Token Factory on 2026-10-11. Findings from building the owner app (voice, receipt photos, approvals) are added as those features land.

## Nebius Token Factory

**What worked**
- OpenAI-compatible endpoint meant zero SDK friction: the standard `openai` Python client with `base_url` set, and function calling in the usual shape.
- Having Nano, Super and Ultra behind one key made the "right model per job" design cheap to try.

**What was confusing**
- Exact Nemotron model ids are hard to find in the docs; the marketing page shows one id in a code sample and the rest only in URL-encoded catalogue links, with inconsistent casing (`nvidia/Nemotron-3_5-Lightning` vs `nvidia/nemotron-3-super-120b-a12b`). A single "models and ids" table in the docs would save every team an hour.
- `/models` in the docs site returned an error when fetched programmatically during the build.
- There is no speech-to-text or text-to-speech model in the catalogue (checked 2026-10-12). Our owner doesn't type, so voice is the main input. Browser speech recognition only works in Safari on an iPhone (Chrome on iOS blocks it), so we ended up running speech models ourselves on the Nebius VM: NVIDIA Parakeet for speech-to-text and Kokoro for the voice. A hosted Whisper-class model and a TTS voice next to Nemotron would let a voice-first app keep the whole pipeline on one key.
- The catalogue does include vision models (MiniCPM-V 4.5, Gemma 3 27B), which is what makes "photograph the supplier receipt" possible on the same key.

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

- The vision model and Nemotron share one key and one OpenAI-compatible API, so "photo, then Nemotron Super extracts line items" was a few lines on top of the existing client. In a live run MiniCPM-V 4.5 transcribed a handwritten note in about 6 seconds, and spoken or photographed jobs became correct invoice drafts in 2-8 seconds end to end.
- Splitting the owner pipeline into Nano (route: is this a finished job, a status update or a payment?) and Super (extract line items as JSON) kept the common path fast and let us keep pricing in plain code. Nemotron extracts what was done and the figures the owner said; it never makes up a price, and code fills anything he left out from the shop's rates.
- Because Token Factory has no speech model, the first owner app used Safari's Web Speech API. It needs HTTPS (which pushed a certificate onto our VM early: an sslip.io name with Caddy and Let's Encrypt) and it doesn't work at all in Chrome on an iPhone, which is what the first real tester used. We replaced it with recording on the phone and transcribing on the VM: faster-whisper base.en, int8 on a 2-vCPU `cpu-d3` instance, primed with the cars and regos in the shop that day so plates come out right. Whisper heard "labour" as "label" often enough that we correct it in code. Our owner is not a native English speaker and base.en missed or garbled a lot of what he said, so we moved to NVIDIA Parakeet TDT 0.6B v2: twice as fast as base.en on the same CPU and far better with accents. small.en took 4 s and large-v3-turbo 14 s a recording on that VM. On 144 synthetic accented clips (non-native English voices reading shop lines), word error rate on mildly accented speech went from 18.9% with base.en to 12.0% with Parakeet, at about 0.6 s a recording, and to 8.4% with the shop-word fixes below. Parakeet takes no prompt, so plates and makes it mishears are put back in code from the cars in the shop, along with accent-driven shop words ("taxi and voice" to "tax invoice", "Nissan X-7" to "Nissan X-Trail", EFTPOS, rego, Hilux). For a voice-first app the speech model matters as much as the language model, and a Parakeet endpoint on Token Factory would be the obvious fit.
- On an iPhone, the page had set its audio session to playback-only (for the spoken read-back) right before asking for the microphone, so iOS refused with InvalidStateError and no iPhone recording ever reached the server. Switching to play-and-record while recording and back to playback afterwards fixed it. Our accent test set is made by having Kokoro's non-native English voices read shop lines (`backend/scripts/stt_accent_eval.py`).
- Replies are spoken by Kokoro 82M (int8 ONNX, Apache-2.0) on the same VM: first audio in about 0.6 seconds, cached after that. It sounds far better than the phone's built-in voices, and a short read-back that ends with a question ("Send it to Jenny?") lets the owner answer "yep" instead of tapping.
- Job extraction on Nemotron 3 Super took 4-7 seconds with reasoning on. It is a one-shot JSON task, so we turned reasoning off for it and it now takes about 1 second, and the 47-utterance set below still passes.
- Nemotron 3 Nano is good at pulling slots out of messy speech. "Find yesterday's jobs and prepare invoice", "do the X-Trail from Friday", "Dan's one" and "what's waiting to be invoiced" all come back as a day, car, customer or status, and plain code finds the job. We keep 47 real owner utterances with expected outcomes; all 47 pass on live Nemotron (three runs), and the same set runs on every pull request against the mock models.
- Memory across turns needs care with an extractor. If the last read-back is in its context, our own amounts can come back as if the owner had said them, so Super's extractor sees the conversation without our figures, and the back-office prompt forbids pricing a job line itself. With that, 12 multi-turn conversations (43 checks: corrections such as "make it 380 all up", "add oil and a filter to that", pronouns, "same as last time", "remember Jack always pays cash") passed 42 of 43 on live Nemotron; the one miss (front pads dropped from a draft) was fixed and the re-run was clean.

*More findings from the owner app are added as they come in.*

## Suggestions
- Add speech-to-text and text-to-speech models to Token Factory. Voice-first apps for people who don't type are a natural fit for Nemotron, and today they have to host their own speech models or use a second provider.
- Publish a tool-calling reliability note per model (how often arguments are well-formed JSON, whether parallel tool calls are supported).
- A "small business agent" cookbook recipe: Nano classify → Super act → Ultra summarise is a pattern many apps will want.

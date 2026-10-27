# Devpost submission

Paste-ready text for the Devpost form. Each heading below is one field or one section of the "About the project" field.

**Project name:** GarageDesk

**Elevator pitch (200 characters max):** A mechanic who can't type holds one button and says what he'd have told his wife. Nemotron on Nebius makes the GST tax invoice, and she approves it with one tap.

**Track:** Best Apps and Agents
**Side prize:** Best Use of Tavily (live supplier price search at runtime, `backend/app/agent/parts_lookup.py`)

## Inspiration
We built GarageDesk with a real workshop in Sunshine North, Melbourne. The owner is a very good mechanic. He doesn't type, he isn't comfortable with computers, and English is his second language. His day is spent under cars, telling his staff what to do, answering customers who walk in to ask if their car is ready, and ringing suppliers for parts. He has no job cards and no software: when a car is done he works out the charge on a calculator, and his customers pay on EFTPOS.

His wife used to do the admin, including every GST tax invoice. Then she took a part-time job elsewhere. Now, whenever a car is finished, he phones her and tells her what was done, the parts, and how much to charge, and she makes the tax invoice. When she can't answer, the customer waits.

Every invoicing app assumes someone sitting at a desk. He will never be that person. So we set ourselves one goal: **replace the phone call to his wife.**

## What it does
The owner opens GarageDesk on his iPhone, holds one big button, says what he wants, and lets go. The phone answers out loud. He never types.

- **Talk-to-Invoice.** *"Corolla ABC123, front pads, hour and a half, 350 all up."* GarageDesk finds the car and the customer, and his figures are the charge, whether he gives a price per item, a labour amount or a total. Only what he didn't price comes from the shop's list. It reads it back in one breath, *"Maria's Corolla. Front brake pads and an hour and a half labour. Three hundred and fifty dollars all up. Send it to Jenny?"*, and "yep" sends it.
- **It finds the job for him.** *"Find yesterday's jobs and prepare the tax invoice"* brings up Dan's Nissan X-Trail with the invoice ready at $240.90. Day, rego, customer, car or status all work, with no dates or job numbers.
- **It remembers, like his wife would.** "Actually make it 380 all up" changes only the total. "Add oil and a filter to that" adds to the job he was just on. *"Liam's Ranger, did the battery again, same as last time"* comes back at last visit's real figures, $366.00. "Remember Jack always pays cash" is kept. When it has to ask ("Which car?", "What do you charge for it?"), a one-word answer like "the Corolla" or "25" carries on the request.
- **It knows the trade.** Common jobs, typical labour times, parts, shop slang, and car names however the speech comes out ("high lux" is a Hilux). It never invents a price.
- **It runs his day by voice.** "What have I got on today?" reads the board: *"5 cars today: 8am Maria's Corolla…"*. "How much GST this quarter?", "what did we take yesterday?". "The CX-5 is waiting on parts till Thursday" texts that customer. *"Order front pads for the Kia Cerato"* finds the part and a price (shop catalogue plus Tavily live search), reads the order back, and "yes" sends it to the supplier.
- **Parts from a receipt photo.** Instead of reading out a list of parts, he photographs the supplier's receipt. A vision model reads it, the parts go on the job at cost, and the receipt is booked as an expense with its GST.
- **His wife approves from anywhere.** She gets a text with a link, checks the invoice with GST shown, and taps Approve, or Fix with a note that goes back to him. His phone tells him out loud when she has approved.
- **The customer and the money.** After approval the customer gets "your car is ready" with an Australian GST tax invoice PDF. When they pay on the EFTPOS terminal he says "yes" and the receipt goes out. The shop has no accounting software; GarageDesk is the books.
- **The rest of the front desk:** an agent answering phone calls, SMS and web chat (hours, bookings into a free bay, "is my car ready?", messages for the owner), bookings from the shop's own website prefilling jobs, reminder texts, and an end-of-day report. Phone and SMS run through Twilio when its keys are set; the public demo has none, so every text it sends shows on the dashboard's Sent page instead of reaching a real phone.

## How we built it
FastAPI and SQLModel on the backend, a React and Tailwind phone web app for the owner (added to his home screen, no app store) and a dashboard for his wife and the accountant, all in one Docker image on a Nebius AI Cloud VM. Every language model call goes to **Nebius Token Factory** through its OpenAI-compatible API with native function calling, and each **NVIDIA Nemotron 3** tier does the job it is best at:

- **Nemotron 3 Nano** routes every message (a finished job, a correction, a question, an order, a payment?) and pulls the day, car, customer, rego or status out of how he talks. Fast and called constantly.
- **Nemotron 3 Super** turns a mechanic's loose speech ("pads", "5W-30", "hour and a half") into exact invoice lines, and runs the tool-calling front desk and back office agents.
- **Nemotron 3 Ultra** writes the end-of-day report, the one place where reasoning over the whole day is worth the bigger model.
- **MiniCPM-V 4.5** on Token Factory reads supplier receipt photos, and Super turns what it read into parts lines.
- **Tavily** searches live supplier prices for parts the shop doesn't stock, and Nano turns the results into structured prices.

Token Factory has no speech models, so two small open models run on the same Nebius VM's CPU. **NVIDIA Parakeet TDT 0.6B v2** (int8 ONNX, about 0.6 s a recording) transcribes the phone's recording, so it works in Chrome, Safari or any browser, and a misheard make, model or plate is put back from the cars in the shop that day. **Kokoro 82M** speaks the replies.

The agent has memory and know-how built in: recent turns, the job he's on, and the shop's records for any car he names (bookings, past visits and what they cost, his notes, facts he asked it to remember) go into each call, along with a mechanic's knowledge base of common jobs, typical times and misheard car names. The model never sets a price: Nemotron extracts what he said, his amounts become the charge, and plain code fills any gaps from the labour rate and parts list, exact to the cent. Approve links are HMAC-signed so his wife needs no account. A deterministic mock drives the same tools, so CI and a keyless demo exercise the real agent loop.

## Challenges we ran into
- **Designing for someone who will never open a dashboard.** Our first version was a capable AI back office with a dashboard and a chat box, exactly the interface the owner couldn't use. Rebuilding around his voice and one button was the real work. We even got his habits wrong at first: we assumed paper job cards, but he has none. So the app now copies the phone call to his wife, his words and his numbers.
- **Hearing an accent.** The small Whisper we started with got 18.9% of words wrong on mildly accented shop talk. NVIDIA Parakeet on the same CPU brought that to 12.0%, and shop-word fixes for what accents still bend ("taxi and voice" is a tax invoice; EFTPOS, rego, Hilux, Cerato) brought it to 8.4%, on 144 clips of non-native English voices reading real shop lines.
- **Voice in every phone browser.** Browser speech recognition doesn't work in Chrome on an iPhone, which is what our first tester used, and iOS refused the microphone because the page had set its audio session to playback for the read-back. Recording on the phone, transcribing on the server, and switching the audio session around the recording fixed both.
- **Making an agent safe for real money.** Nothing leaves the shop without a person: he hears every total read back, his wife approves every invoice, and parts orders are read back before "yes" sends them. Stated totals are exact to the cent.
- **Remembering without making things up.** A model that sees the last read-back can mistake our numbers for his. The extractor sees the conversation without our amounts, and a follow-up answer only puts work on a car he named.

## Accomplishments that we're proud of
- A complete product built around one real person: bookings, jobs, GST tax invoice PDFs, approvals, payments, parts orders, an outbox, reminders and a daily report, with a front end a mechanic who doesn't type can actually use. Live on Nebius, on live Nemotron.
- A whole workshop day works end to end by voice: 13 flows over the phone's endpoints from a cold start on live Nemotron, 47 of 47 real owner phrasings for finding jobs, 12 multi-turn memory conversations, and 155 automated tests on every pull request.
- Speech that copes with accented English: word error rate from 18.9% to 8.4%.

## What we learned
Splitting the work across three Nemotron tiers paid off. Nano with thinking turned off routes a message in under half a second; Super with reasoning off extracts a job in about a second; Ultra writes the end-of-day report in about 5 seconds. Every tool chain we tested (find customer, check availability, book; price lookup, parts order; job done, GST invoice) completed with clean arguments.

The surprise was reasoning tokens: they count against `max_tokens`, so our first live run returned truncated JSON from Nano and a report from Ultra that stopped mid-sentence. Small models now answer directly and the big model gets room to think.

The bigger lesson was about the user. The most useful thing an AI agent can do for this owner isn't a smarter answer; it's removing the screen. For a voice-first app the speech model matters as much as the language model.

## What's next
- Put it in the owner's hands with his real price list and measure the number that matters: admin calls to his wife per day, from several to none.
- Read bookings from the shop's live website once it exposes its read endpoint (the demo uses a mock week of bookings).
- Real SMS through Twilio, a CSV for the accountant, and WhatsApp voice notes as another way in.
- A second shop.

## Built with
python, fastapi, sqlmodel, react, typescript, tailwind, docker, caddy, nebius-token-factory, nebius-ai-cloud, nvidia-nemotron, nvidia-parakeet, onnx, minicpm-v, kokoro-tts, tavily, twilio

## Try it out
- Owner app (open on a phone, any browser): https://66-201-4-40.sslip.io/owner
- Dashboard: https://66-201-4-40.sslip.io/
- Customer chat: https://66-201-4-40.sslip.io/chat
- Code (MIT): https://github.com/zhangshen20/garagedesk

## Video
https://youtu.be/0Q1z12hNR8k (2:51)

## Feedback on Nebius and NVIDIA tools
The full write-up is [FEEDBACK.md](FEEDBACK.md). Short version for the form:

Token Factory's OpenAI-compatible API meant zero SDK friction: the standard `openai` client with `base_url` set, function calling in the usual shape, and Nano, Super, Ultra and a vision model behind one key, which made "the right model for each job" cheap to build. Nemotron 3 Super completed every multi-step tool chain we tested with well-formed arguments, Nano is excellent at pulling slots out of messy speech, and Ultra's daily report was the standout, tying a waiting job to a pending parts order and naming the overdue customer.

What cost us time: exact Nemotron model ids are hard to find in the docs (one id in a code sample, the rest in URL-encoded catalogue links with inconsistent casing), and reasoning tokens silently share the `max_tokens` budget, which gave us truncated JSON and a cut-off report until we turned thinking off per request (`chat_template_kwargs: {"enable_thinking": false}`). A docs note on both would save every team an hour.

The biggest gap for us: Token Factory has no speech-to-text or text-to-speech model. Our user doesn't type, so we host NVIDIA Parakeet and Kokoro ourselves on a Nebius VM. Parakeet was a big win for accented English (word errors 18.9% to 8.4%), and a hosted Parakeet endpoint next to Nemotron would let a voice-first app keep the whole pipeline on one key.

## Was this project started before the hackathon?
No. GarageDesk was started on 11 October 2026, during the hackathon, in a new public repository.

# Devpost submission draft

**Project name:** GarageDesk
**Tagline:** Replace the phone call to his wife: a mechanic says what he'd have told her, Nemotron makes the GST tax invoice, and she approves it with one tap.
**Category:** Best Apps and Agents
**Side prize:** Best Use of Tavily (live supplier price lookup)

## Inspiration
We built GarageDesk with a real three-bay workshop in Sunshine North, Melbourne. The owner is a very good mechanic. He doesn't type, he isn't comfortable with computers, and English is his second language. His day is spent under cars, telling his staff what to do, answering customers who walk in to ask if their car is ready, and ringing suppliers for parts. He has no job cards and no software: when a car is done he works out the charge on a calculator. His customers pay on EFTPOS.

His wife used to do the admin, including every GST tax invoice. Then she took a part-time job elsewhere. Now, whenever a car is finished, he phones her and tells her what was done, the parts, and how much to charge, and she makes the tax invoice. When she can't answer, the customer waits.

Every invoicing app assumes someone sitting at a desk. He will never be that person. The shop already has a website with online booking, and it didn't take a single minute of admin off him. So we set ourselves one goal: **replace the phone call to his wife.**

## What it does
The owner never types. He says what he would have said to his wife on the phone, and the phone answers out loud.

- **Talk-to-Invoice.** He holds one big button on his phone, says exactly what he'd have told his wife, and lets go: *"Corolla ABC123, front pads, hour and a half, 350 all up."* It works in any phone browser, Chrome or Safari, because the phone records and our server transcribes. GarageDesk finds the car and customer and uses his figures as the charge, whether he gives a price per item, a labour amount or a total. Only what he didn't price comes from the shop's list. A natural voice reads it back in one breath: *"Maria's Corolla. Front brake pads and an hour and a half labour. Three hundred and fifty dollars all up. Send it to Jenny?"* He says "yep" and it's sent. "Hear every line" reads each line and the GST.
- **It finds the job for him.** *"Find yesterday's jobs and prepare invoice"* brings up Dan's Nissan X-Trail, finished yesterday, with the invoice ready at $240.90. He can find a job by day, rego, customer, car or status ("what's waiting to be invoiced?"), with no dates or job numbers.
- **It remembers, like his wife would.** It keeps the thread of the conversation: "actually make it 380 all up" changes only the total, "add oil and a filter to that" adds to the job he was just on, and "what's he driving?" knows who "he" is. It remembers every customer and car, with past visits, what they cost and his notes, so *"Liam's Ranger, did the battery again, same as last time"* comes back at last visit's real figures, $366.00. Tell it *"remember Jack always pays cash"* and it does. When it needs to ask ("Which car?", "Which one?", "What do you charge for it?"), a one-word answer like "the Corolla", "the first one" or "25" carries on what he asked for, and it never puts work on a car he didn't name.
- **It knows the trade.** Common jobs, typical labour times, parts, what to check while a car is in, shop slang, and car names however the speech comes out ("high lux" is a Hilux). It still never invents a price: anything he didn't price comes from the shop's list or the last visit, or it asks.
- **Add parts from a receipt photo.** Instead of reading out a list of parts, he photographs the supplier's receipt. A vision model reads it, the parts go onto the job at cost, and the receipt is booked as an expense with its GST.
- **His wife approves from anywhere.** Instead of a phone call she gets a text with a link, checks the invoice with GST shown, and taps Approve, or Fix with a note that goes back to him. His phone tells him out loud when she has approved. She stays in control of the books without being in the shop.
- **"Your car is ready."** Once she approves, the customer gets a text with the GST tax invoice PDF. *"The CX-5 is waiting on parts till Thursday"* becomes a text to that customer too, so fewer people walk in to ask.
- **Paid on EFTPOS, one word.** After the approval his phone asks him to say yes when the customer has paid; "yes" (or one tap on Paid EFTPOS) marks it paid and texts the receipt. The shop has no accounting software; GarageDesk is the books.
- **It knows the shop.** Bookings from the shop's own website flow onto the board and open as prefilled jobs, so customer, car, rego and service are already there and he only says what's different. GarageDesk only reads from the site.
- **The rest of the desk, already live:** an agent that answers phone calls, SMS and web chat (hours, bookings into a free bay, "is my car ready?", reschedules, messages for the owner); parts lookup with Tavily live search and purchase orders that wait for approval; reminder texts to tomorrow's customers; and an end-of-day report from Nemotron 3 Ultra.

## How we built it
FastAPI + SQLModel backend, a React/Tailwind dashboard for the wife and accountant, a phone web app for the owner that he adds to his iPhone home screen (no app store), all in one Docker image on a Nebius AI Cloud VM. Every model call goes to Nebius Token Factory's OpenAI-compatible API with native function calling, and each NVIDIA Nemotron 3 tier does the job it is best at:
- **Nemotron 3 Nano** classifies every inbound message and turns web search results into structured prices. Cheap, fast, called constantly.
- **Nemotron 3 Super** turns a mechanic's loose speech ("pads", "5W-30", "hour and a half") into exact invoice lines with tool calls against the shop's catalogue, jobs and customers, and runs the front desk and back office tool-calling agents.
- **Nemotron 3 Ultra** writes the end-of-day report, the one place where reasoning over the whole day is worth the bigger model.
- A **vision model on Token Factory** (MiniCPM-V 4.5) reads photos of supplier receipts, and Nemotron Super turns what it read into parts lines.

The owner agent has memory and know-how built in. Recent turns, the job he's on, and the shop's records for any car he names or just mentioned (bookings, past visits with their amounts, his notes, facts he asked it to remember) go into each Nemotron call, along with a mechanic's knowledge base: common jobs, typical times, parts, checks and misheard car names. Recall and "remember this" are tools the Super agent calls.

The model never invents a price. Nemotron extracts what he said, his amounts become the charge, and plain code fills any gaps from the shop's labour rate and parts list. Saying a job again replaces its lines, so a correction is just saying it right.

Token Factory has no speech models, so we run two small open models on the same Nebius VM. The phone records his voice in any browser and NVIDIA Parakeet TDT 0.6B v2 (int8 on the CPU, about 0.6 s a recording) transcribes it. It hears owners whose first language isn't English far better than the small Whisper we started with, and a misheard make, model or plate is put back from the cars in the shop today ("Master CX5" becomes "Mazda CX-5"). Replies are spoken by Kokoro, an 82M-parameter Apache-2.0 neural voice, first audio in about 0.6 seconds and cached after that. Phone calls use Twilio's speech recognition. Approve links are HMAC-signed, so his wife needs no account or password. A deterministic mock drives the same tools, so tests, CI and a keyless demo exercise the real agent loop.

The design follows five rules written for this owner: speak, snap or tap, never type; works with dirty hands; read it back before it leaves; his wife stays in control from anywhere; it already knows the shop.

## Challenges
- **Designing for someone who will never open a dashboard.** Our first version was a capable AI back office with a dashboard and a chat box, which was exactly the interface the owner couldn't use. Rebuilding around his voice and one button was the real work. We even got his habits wrong at first: we assumed paper job cards, but he has none. He does the sums on a calculator and phones his wife. So the app now copies that phone call exactly, his words and his numbers.
- **Making an agent safe for real money.** Nothing that leaves the shop goes without a person: the owner hears every total read back, his wife approves every invoice, and supplier orders wait for a tap. The agent never invents a price.
- **Hearing an accent.** Like many tradespeople, the owner is not a native English speaker, and the small Whisper model we started with got 18.9% of words wrong on mildly accented shop talk. NVIDIA Parakeet, running on the same VM CPU in about 0.6 seconds a recording, brought that to 12.0%, and shop-word fixes for what accents still bend ("taxi and voice" is a tax invoice; EFTPOS, rego, Hilux, Cerato, Mazda) brought it to 8.4%, measured on 144 clips of non-native English voices reading real shop lines.
- **Remembering without making things up.** A model that remembers the last read-back can mistake our numbers for his. The extractor sees the conversation without our read-back amounts, questions and "waiting on parts" never turn into invoices, and a correction keeps everything he said before. We test 12 multi-turn conversations (43 checks) against live Nemotron: 42 of 43 passed on the full run, and the one miss (pads dropped from a draft) was fixed and re-run clean.
- **Finding the job from how he talks.** "Yesterday's jobs", "Dan's X-Trail", "the one waiting on parts": Nemotron Nano pulls out the day, car, customer, rego or status, and plain code finds the job, so lookups are exact and fast. We test 47 real owner utterances against live Nemotron (47 of 47 pass) and run them on every pull request.
- **Shop talk with numbers in it.** "Front pads, hour and a half, 350 all up" has to become exact parts, quantities and labour lines, with his figures as the charge and nothing made up for what he didn't say.
- **Reasoning tokens and output budgets** on Token Factory, described under "What we learned".

## Accomplishments
A complete product built around one real person: bookings, bays, jobs, GST tax invoice PDFs, payments, parts orders, approvals, an outbox, reminders and a daily report, with a front end that a mechanic who doesn't type can actually use. Live on Nebius, on live Nemotron.

## What we learned
Splitting the work across three Nemotron tiers paid off. Nano with thinking turned off classifies a message in under half a second, Super drives each agent turn in 2-5 seconds including its tool calls (turning reasoning off for Super's one-shot job extraction cut the owner's model step from 4-7 seconds to about 1), and Ultra writes the whole end-of-day report in about 5 seconds. In live testing every tool chain (find customer, check availability, book; price lookup, parts order, approval; job done, GST invoice) completed first time with clean arguments.

The surprise was reasoning tokens. They count against `max_tokens`, so our first live run returned truncated JSON from Nano and a daily report from Ultra that stopped mid-sentence. Turning thinking off for the one-shot Nano jobs and giving Ultra room to think fixed both. That lesson now shapes how we budget every call: small models answer directly, and the big model gets space to reason.

The bigger lesson was about the user. The most useful thing an AI agent can do for this owner isn't a smarter answer; it's removing the screen.

## What's next
- Put it in the owner's hands with his real labour rate and price list, and measure the number that matters: admin calls to his wife per day.
- Switch the booking link from demo bookings to the live website once it exposes its read endpoint.
- A quarterly GST summary for the BAS and a CSV for the accountant.
- A spoken 30-second end-of-day summary instead of a written report, in the same voice.
- WhatsApp voice notes as another way to talk to it, then a second shop.

## Built with
python, fastapi, sqlmodel, react, typescript, tailwind, docker, nebius-token-factory, nebius-ai-cloud, nvidia-nemotron, nvidia-parakeet, faster-whisper, kokoro-tts, tavily, twilio

## Links
- Repo: https://github.com/zhangshen20/garagedesk (MIT)
- Demo URL: https://66-201-4-40.sslip.io/owner (owner app, open it on a phone in any browser), https://66-201-4-40.sslip.io/ (dashboard), https://66-201-4-40.sslip.io/chat (customer chat)
- Video: (to fill)

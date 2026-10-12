# Devpost submission draft

**Project name:** GarageDesk
**Tagline:** A back office the mechanic never types into: he talks or snaps his job card, Nemotron makes the GST invoice, his wife approves from her phone.
**Category:** Best Apps and Agents
**Side prize:** Best Use of Tavily (live supplier price lookup)

## Inspiration
Sunshine North Mechanic is a real workshop in Melbourne's west. The owner knows cars, not computers, and can't type quickly. His wife did the tax invoices, but she now works part-time elsewhere, so whenever a car is finished he phones her at her other job to make the invoice. He told us what he wanted: to make a tax invoice himself, and to get the small daily admin off his hands so he can stay under the cars. GarageDesk is built around that one person, and the thousands of shop owners like him.

## What it does
- **Talk-to-Invoice.** The owner holds one big button on his iPhone and says the job in workshop slang ("Corolla ABC123 done, front pads, machined the rotors, hour and a half"). GarageDesk finds the car, prices the parts from the shop's catalogue and the labour from his rate, reads the total back out loud, and he taps Send.
- **Photo of the paper job card.** He already writes job cards by hand, so a photo works too: a vision model reads the handwriting and the same pipeline builds the invoice.
- **His wife approves from anywhere.** She gets a text with a link, checks the invoice with GST shown, and taps Approve, or sends it back with a note. Then the customer gets "your car is ready" with the tax invoice PDF.
- **Paid on EFTPOS, one tap.** The invoice is marked paid and the receipt is texted.
- **Status by voice.** "The CX-5 is waiting on parts till Thursday" texts the customer, so fewer people walk in to ask.
- **Runs the rest of the desk:** answers the phone, SMS and web chat (bookings into a free bay, "is my car ready?"), drafts supplier parts orders with live price comparison that wait for approval, and writes the end-of-day report.

## How we built it
FastAPI + SQLModel backend, React/Tailwind dashboard, one Docker image. All model calls go to Nebius Token Factory's OpenAI-compatible API with native function calling, using three NVIDIA Nemotron 3 tiers deliberately:
- **Nemotron 3 Nano** routes everything the owner says and classifies every inbound customer message, and structures web-search results into prices (cheap, fast, called constantly).
- **Nemotron 3 Super** turns the owner's spoken or handwritten notes into structured line items, and runs the two tool-calling agents (front desk and back office) over 22 tools.
- **Nemotron 3 Ultra** writes the daily report, the one place reasoning across the whole day is worth the bigger model.
A vision model on Token Factory (MiniCPM-V 4.5) transcribes photos of handwritten job cards; Nemotron does the reasoning. Speech-to-text is the iPhone's own recognition in the browser, so the owner app needs no app store install. Prices always come from code (catalogue and labour rate), never from the model.
A deterministic mock drives the same tools so tests, CI and a keyless demo exercise the real loop. Twilio voice uses built-in speech recognition and Polly TTS so a phone line needs no other services.

## Challenges
- Making an agent safe for real money: we moved from "the agent sends the order" to "the agent drafts, the owner taps approve", and logged every outbound message.
- Phone-call turns need a different style from SMS or web; the system prompt adapts per channel (one or two spoken sentences, confirm details back).
- Keeping Nemotron reasoning (`<think>` blocks) out of customer-facing text.

## Accomplishments
A complete product, not a demo: bookings, bays, job cards, GST invoices with PDFs, payments and receipts, purchase orders, approvals, outbox, daily report, reminders, and a dashboard the owner would actually use.

## What we learned
Splitting the work across three Nemotron tiers paid off. Nano with thinking turned off classifies a message in under half a second, Super drives each agent turn in 2-5 seconds including its tool calls, and Ultra writes the whole end-of-day report in about 5 seconds. In live testing every tool chain (find customer, availability, book; price lookup, parts order, owner approval; job done, GST invoice) completed first time with clean arguments.

The surprise was reasoning tokens. They count against `max_tokens`, so our first live run returned truncated JSON from Nano and a daily report from Ultra that stopped mid-sentence. Turning thinking off for the one-shot Nano jobs and giving Ultra room to think fixed both. That lesson now shapes how we budget every call: small models answer directly, and the big model gets space to reason.

## What's next
Pull bookings straight from the shop's own website so every job starts pre-filled, photo-to-expense for supplier receipts, a quarterly GST summary for the BAS, a real Twilio number, WhatsApp voice notes, and a second shop.

## Built with
python, fastapi, sqlmodel, react, typescript, tailwind, docker, nebius-token-factory, nvidia-nemotron, tavily, twilio

## Links
- Repo: https://github.com/zhangshen20/garagedesk (MIT)
- Demo URL: https://66-201-4-40.sslip.io/owner (owner app, best on an iPhone), https://66-201-4-40.sslip.io/ (dashboard), https://66-201-4-40.sslip.io/chat (customer chat)
- Video: (to fill)

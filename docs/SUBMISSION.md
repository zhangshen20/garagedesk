# Devpost submission draft

**Project name:** GarageDesk
**Tagline:** The AI front desk and back office for a one-owner mechanic shop, on NVIDIA Nemotron and Nebius Token Factory.
**Category:** Best Apps and Agents
**Side prize:** Best Use of Tavily (live supplier price lookup)

## Inspiration
Sunshine Auto Care is a real three-bay workshop in Sunshine North, Melbourne. The owner is a good mechanic who spends half of every day on the phone, typing invoices, chasing parts prices and remembering who owes money. The business doesn't need a chatbot; it needs the admin to disappear. GarageDesk is built for that one owner, and for the thousands of shops like it.

## What it does
- Answers the phone, SMS and web chat: hours, bookings into a free bay, "is my car ready?", reschedules and cancellations, and takes a message for anything it shouldn't decide.
- Runs the back office from a chat: job cards, GST tax invoices and receipts as PDFs texted to the customer, payments, expenses, and supplier purchase orders with live price comparison.
- Keeps the owner in control: every supplier order waits on a one-tap approval, every outbound message is logged, and the agent never invents a price.
- Writes the end-of-day report: cash in and out, GST, overdue invoices, tomorrow's board and one concrete suggestion.
- Sends reminder texts to tomorrow's customers automatically.

## How we built it
FastAPI + SQLModel backend, React/Tailwind dashboard, one Docker image. All model calls go to Nebius Token Factory's OpenAI-compatible API with native function calling, using three NVIDIA Nemotron 3 tiers deliberately:
- **Nemotron 3 Nano** classifies every inbound message and structures web-search results into prices (cheap, fast, called constantly).
- **Nemotron 3 Super** runs the two tool-calling agents (front desk and back office) over 20 tools.
- **Nemotron 3 Ultra** writes the daily report, the one place reasoning across the whole day is worth the bigger model.
A deterministic mock drives the same tools so tests, CI and a keyless demo exercise the real loop. Twilio voice uses built-in speech recognition and Polly TTS so a phone line needs no other services.

## Challenges
- Making an agent safe for real money: we moved from "the agent sends the order" to "the agent drafts, the owner taps approve", and logged every outbound message.
- Phone-call turns need a different style from SMS or web; the system prompt adapts per channel (one or two spoken sentences, confirm details back).
- Keeping Nemotron reasoning (`<think>` blocks) out of customer-facing text.

## Accomplishments
A complete product, not a demo: bookings, bays, job cards, GST invoices with PDFs, payments and receipts, purchase orders, approvals, outbox, daily report, reminders, and a dashboard the owner would actually use.

## What we learned
(filled in after live testing: latency and tool-calling reliability per Nemotron tier, cost per customer interaction)

## What's next
Xero/MYOB sync for the bookkeeper, real Twilio number for Sunshine Auto Care, photo-to-expense from the parts counter, and a second shop.

## Built with
python, fastapi, sqlmodel, react, typescript, tailwind, docker, nebius-token-factory, nvidia-nemotron, tavily, twilio

## Links
- Repo: https://github.com/zhangshen20/garagedesk (MIT)
- Demo URL: (to fill)
- Video: (to fill)

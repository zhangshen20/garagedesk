# GarageDesk

**A back office the mechanic never types into. He talks, or photographs his paper job card; NVIDIA Nemotron on Nebius Token Factory turns it into a GST tax invoice; his wife approves it from her phone.**

Built for the Nebius x NVIDIA Global AI Hackathon (track: Best Apps & Agents) around a real workshop, Sunshine Auto Care in Sunshine North, Victoria.

The owner of the real shop behind this can't use a computer and can't type quickly. His wife did the invoices, but she works part-time elsewhere now, so when a car is finished he rings her at her other job to make the tax invoice. GarageDesk's goal is to replace that phone call.

More broadly, a one-owner mechanic shop loses its day to a hundred small interruptions: the phone, "is my car ready?", booking changes, chasing a brake-pad price from three suppliers, typing up tax invoices, remembering who still owes money, and working out at 6pm whether the day actually made money. GarageDesk takes all of that. The owner fixes cars; the agents run the desk.

> **Live demo:** owner app at https://66-201-4-40.sslip.io/owner (open it on an iPhone), dashboard at https://66-201-4-40.sslip.io/ and customer chat at https://66-201-4-40.sslip.io/chat, running on a Nebius AI Cloud VM with live Nemotron models.
>
> Demo mode works with **no API keys at all**. Add a Nebius key and the same code runs on live Nemotron models.

## The owner app: speak, snap, tap

`/owner` is a phone web app (add it to the iPhone home screen; no app store) with one huge hold-to-talk button.

1. **Say the job.** "Corolla ABC123 done, front pads, machined the rotors, hour and a half." Nemotron 3 Nano routes it (job card or something else) in under a second; Nemotron 3 Super pulls out the car and line items as JSON; code finds the job, prices parts from the shop's catalogue and labour from its hourly rate. The model never sets a price. The draft is read back out loud: "Invoice for Maria's Toyota Corolla: 1.5 hours labour and brake pads front. 328.90 dollars including GST. Send it?"
2. **Or photograph the paper job card.** A vision model on Token Factory (`openbmb/MiniCPM-V-4_5`) transcribes the handwriting, and the same pipeline takes over.
3. **Tap Send.** Whoever does the books gets an SMS with a signed link (`/approve/:id`). She checks the invoice with GST split out and taps Approve, or Fix with a note that goes back to the owner. Small invoices can skip this once she trusts it (`AUTO_APPROVE_INVOICE_UNDER_CENTS`).
4. **The customer** gets "your car is ready" and the tax invoice PDF. When they pay on EFTPOS, one tap marks it paid and texts the receipt.
5. **Anything else by voice.** "The CX-5 is waiting on parts till Thursday" texts the customer; "Corolla paid on EFTPOS" records the payment; "need front pads for the Mazda" drafts a parts order for approval.

Speech recognition is the phone's own (Safari's Web Speech API, which needs HTTPS); where it isn't available the page falls back to a text box for the keyboard's dictation button.

## What it does

| Who | Channel | What the agent does |
|---|---|---|
| Customers | Phone call (Twilio voice), SMS, web chat | Answers hours and location, books cars into a free bay, checks "is my car ready?", reschedules and cancels, takes messages for anything it shouldn't decide (quotes, complaints) |
| Owner | Dashboard chat ("Ask the desk"), SMS | Job cards, GST tax invoices and receipts as PDFs (texted to the customer), payments, supplier parts orders with live price lookup, expenses, cash and GST summaries |
| Owner | Automatic | 4pm reminder texts to tomorrow's customers; 5:45pm end-of-day report written by Nemotron 3 Ultra; every supplier order waits on a one-tap approval |

### Three Nemotron tiers, each where it earns its keep

| Tier | Model (Nebius Token Factory id) | Used for |
|---|---|---|
| fast | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | Intent classification on every inbound message; extracting prices from web search results |
| main | `nvidia/nemotron-3-super-120b-a12b` | The two tool-calling agents (front desk and back office), up to 8 tool steps per turn |
| deep | `nvidia/Nemotron-3-Ultra-550b-a55b` | The end-of-day owner report: reasons over cash, jobs, parts, overdue invoices and tomorrow's board in one pass |

All three are called through Token Factory's OpenAI-compatible endpoint (`https://api.tokenfactory.nebius.com/v1/`) with native function calling. Swap any tier with `MODEL_FAST`, `MODEL_MAIN`, `MODEL_DEEP`.

### Safety rails that make it usable for a real business

- **Approvals, not autonomy, for money leaving the shop.** The agent drafts supplier purchase orders; nothing is sent until the owner taps Approve on the dashboard (or replies to the SMS).
- **Every outbound message is logged** in an outbox. Without Twilio credentials the outbox *is* the delivery, so the whole product is demoable offline.
- **The agent never invents a price.** Quotes are the owner's job; the front desk takes a message.
- **Transcripts persist per phone number**, so a customer texting back an hour later continues the same conversation.

## Quick start

```bash
git clone https://github.com/zhangshen20/garagedesk && cd garagedesk
cp .env.example .env            # add NEBIUS_API_KEY for live Nemotron; leave blank for demo mode
docker compose up --build
# open http://localhost:8000   (owner dashboard)   http://localhost:8000/chat   (customer chat)
```

Local development:

```bash
# backend
cd backend && python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/uvicorn app.main:app --reload --port 8000
# frontend (separate shell)
cd frontend && npm install && npm run dev        # http://localhost:5173, proxies /api to :8000
# tests (mock LLM, no network)
cd backend && .venv/bin/pytest -q
# live smoke test against Token Factory
cd backend && NEBIUS_API_KEY=... .venv/bin/python scripts/live_smoke.py
```

Phone calls and SMS: point a Twilio number's voice webhook at `POST /twilio/voice` and SMS webhook at `POST /twilio/sms`. Voice uses Twilio's built-in speech recognition and Polly voice, so no other services are needed. Set `TAVILY_API_KEY` to enable live supplier price search (Nemotron Nano structures the results).

## Architecture

```
customer ──phone/SMS──▶ Twilio webhooks ─┐
customer ──web chat────▶ /api/chat/customer ─┤      ┌─ Nemotron Nano  (classify, extract)
owner ────dashboard────▶ /api/chat/owner ────┼─▶ agent runner ──▶ Nemotron Super (tool-calling loop)
scheduler ─4pm/5:45pm──▶ reminders / report ─┘      └─ Nemotron Ultra (daily report)
                                              │
                               tools: bookings, jobs, invoices (PDF), payments, parts lookup
                                      (Tavily + catalogue), purchase orders → approvals, outbox
                                              │
                                   SQLite/Postgres via SQLModel · FastAPI · React dashboard
```

- `backend/app/llm.py`: Token Factory client plus a deterministic mock that drives the same tools, so tests and the keyless demo exercise the real loop.
- `backend/app/agent/tools.py`: 20 tools with schema and implementation side by side.
- `backend/app/agent/frontdesk.py`, `backoffice.py`, `report.py`: the three agents and their prompts.
- `backend/app/services.py`: bookings, bays, GST, invoices, purchase orders, approvals. No LLM calls.
- `frontend/`: Vite + React + Tailwind dashboard, built into `backend/static` and served by FastAPI.

## How Nebius and NVIDIA tools were used

- **Nebius Token Factory** serves every model call through its OpenAI-compatible API with function calling. The product is designed around the three Nemotron price/capability tiers it exposes: cheap Nano calls on every message, Super for the agents, Ultra once a day.
- **NVIDIA Nemotron 3** (Nano, Super, Ultra) do all the language work: routing and classification, turning the owner's words into line items, the tool-calling agents, and the daily report. Reasoning output in `<think>` tags is stripped before display.
- **A vision model on Token Factory** (MiniCPM-V 4.5) reads photos of handwritten job cards; Nemotron Super reasons over the transcription.
- **Nebius AI Cloud** hosts the demo: one `cpu-d3` VM in eu-west1 runs the Docker image (API + built dashboard + SQLite volume) behind Caddy; see `deploy/nebius/`.

## Status

See the hackathon write-up in `docs/` for the demo script, judging notes and feedback on the Nebius and NVIDIA tooling.

## Licence

MIT. See [LICENSE](LICENSE).

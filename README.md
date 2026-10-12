# GarageDesk

**Replace the phone call to his wife.** A no-typing back office for a one-owner mechanic shop: he talks or photographs his paper job card, NVIDIA Nemotron on Nebius Token Factory builds the GST tax invoice, his wife approves it with one tap from wherever she is, and the customer gets a "your car is ready" text.

Built for the Nebius x NVIDIA Global AI Hackathon (track: Best Apps & Agents) with a real workshop in Sunshine North, Melbourne. In the app the shop appears as **Sunshine Auto Care**.

> **Live demo:** http://66.201.4.40/ (wife's and accountant's dashboard) and http://66.201.4.40/chat (customer chat), on a Nebius AI Cloud VM calling live Nemotron models.
>
> Demo mode works with **no API keys at all**. Add a Nebius key and the same code runs on live Nemotron models.

## The owner this is for

The owner is a good mechanic. He is not comfortable with computers and doesn't type. His day is spent under cars, directing his staff, answering customers who walk in to ask "is it ready?", and ringing suppliers for parts. Job cards are written on paper. Customers pay on EFTPOS. There is no accounting software.

His wife used to do the admin, including the GST tax invoices. She now works part-time somewhere else, so when a car is finished he phones her and she makes the invoice over the phone. If she can't answer, the customer waits.

Invoicing software assumes someone sitting at a desk. He will never be that person. So GarageDesk is built around five rules:

1. **Speak, snap or tap. Never type.** His voice, his phone camera, or one big button.
2. **Works with dirty hands.** One press-and-hold button you can hit with a knuckle. No login mid-job.
3. **Read it back before it leaves.** Anything that goes to a customer or costs money is read to him in one sentence, and he says yes or no.
4. **His wife stays in control, from anywhere.** She approves every invoice with one tap on her phone.
5. **It knows the shop already.** Customer, car, rego and booked service come from the booking, so he only says what is different.

Success is one number: admin calls to his wife per day, from several to none.

## What it does

### For the owner (iPhone web app, added to his home screen)

| He does | GarageDesk does |
|---|---|
| Holds the button: *"Corolla ABC123 done. Full service plus front pads, hour and a half."* | Matches the rego to today's job, prices parts and labour, builds an Australian GST tax invoice, and reads the total back. He says "send". |
| Photographs his paper job card | A vision model reads the handwriting, Nemotron turns it into the same invoice draft |
| Says *"Mazda's waiting on parts till Thursday"* or *"Hilux is done"* | Texts that customer and updates the status board, so fewer people walk in to ask |
| Says *"paid on EFTPOS"* | Marks the invoice paid with the method. GarageDesk is the books |
| Says *"need front pads for the Corolla"* | Finds the price (shop catalogue plus Tavily live search), reads back the best option, and drafts the order |

### For his wife (a link in a text message)

*"Invoice #1042, Mrs Nguyen, $412.50 incl. GST. Approve / Fix."* One tap on her break and it goes to the customer. Supplier orders wait for the same tap. The dashboard is hers and the accountant's: jobs, invoices, money, a quarterly GST summary for the BAS and a CSV export.

### For customers

A text when the car is ready, with the invoice PDF. The phone line, SMS and web chat answer hours, book cars into a free bay, check "is my car ready?", reschedule, and take a message for anything the shop should decide (quotes, complaints).

### Build status

The back office (bookings, bays, job cards, GST invoice PDFs, payments, parts lookup, purchase orders, approvals, outbox, daily report, phone and SMS agents) is built and live. The owner-facing pieces are being built now and this README is updated as each lands:

| Feature | Status |
|---|---|
| Owner iPhone app with hold-to-talk button and read-back | Building |
| Talk-to-Invoice (speech to GST invoice draft) | Building |
| Job card photo to invoice draft (vision model on Token Factory) | Building |
| Wife approves invoices from a text link | Building |
| "Car is ready" and status texts | Building |
| "Paid on EFTPOS" and quarterly GST summary | Building |
| Prefill jobs from the shop's booking website | Building |
| Supplier receipt photos to expenses | Planned |

### Nemotron tiers, each where it earns its keep

| Tier | Model (Nebius Token Factory id) | Used for |
|---|---|---|
| fast | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | Intent classification on every message; extracting prices from web search results |
| main | `nvidia/nemotron-3-super-120b-a12b` | Turning a mechanic's loose words ("pads", "5W-30", "hour and a half") into exact invoice lines; the tool-calling front desk and back office agents |
| deep | `nvidia/Nemotron-3-Ultra-550b-a55b` | The end-of-day report: reasons over cash, jobs, parts, overdue invoices and tomorrow's board in one pass |

All model calls go through Token Factory's OpenAI-compatible endpoint (`https://api.tokenfactory.nebius.com/v1/`) with native function calling. Swap any tier with `MODEL_FAST`, `MODEL_MAIN`, `MODEL_DEEP`. Token Factory has no speech model, so speech-to-text is the iPhone's own dictation (and Twilio speech recognition on phone calls); photos are read by a vision model on Token Factory and Nemotron does the reasoning.

### Safety rails that make it usable for a real business

- **A person approves anything that leaves the shop.** Invoices wait for his wife's tap; supplier orders wait for an approval. The owner hears every total read back first.
- **The agent never invents a price.** Prices come from the shop's catalogue and labour rate, or from a live supplier search; quotes for new work are the owner's call.
- **Every outbound message is logged** in an outbox. Without Twilio credentials the outbox *is* the delivery, so the whole product demos offline.
- **Transcripts persist per phone number**, so a customer texting back an hour later continues the same conversation.

## Quick start

```bash
git clone https://github.com/zhangshen20/garagedesk && cd garagedesk
cp .env.example .env            # add NEBIUS_API_KEY for live Nemotron; leave blank for demo mode
docker compose up --build
# open http://localhost:8000   (dashboard)   http://localhost:8000/chat   (customer chat)
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
owner ──iPhone: voice / job card photo──▶ owner app ──┐
wife ───text link: Approve / Fix────────▶ approvals ──┤      ┌─ Nemotron Nano  (classify, extract)
customer ─phone/SMS/web chat────────────▶ front desk ─┼─▶ agent runner ──▶ Nemotron Super (invoice lines, tool calls)
scheduler ─4pm / 5:45pm─────────────────▶ reminders ──┘      ├─ Nemotron Ultra (daily report)
                                                 │           └─ vision model   (read job card photos)
                         tools: bookings, jobs, GST invoices (PDF), payments, parts lookup
                                (Tavily + catalogue), purchase orders, approvals, outbox
                                                 │
                              SQLite/Postgres via SQLModel · FastAPI · React
```

- `backend/app/llm.py`: Token Factory client plus a deterministic mock that drives the same tools, so tests and the keyless demo exercise the real loop.
- `backend/app/agent/tools.py`: the agent tools, schema and implementation side by side.
- `backend/app/agent/frontdesk.py`, `backoffice.py`, `report.py`: the agents and their prompts.
- `backend/app/services.py`: bookings, bays, GST, invoices, purchase orders, approvals. No LLM calls.
- `frontend/`: Vite + React + Tailwind, built into `backend/static` and served by FastAPI.

## How Nebius and NVIDIA tools were used

- **Nebius Token Factory** serves every model call through its OpenAI-compatible API with function calling. The design leans on having several Nemotron price/capability tiers behind one key: cheap Nano calls on every message, Super for the agents and invoice building, Ultra once a day, and a vision model for photos.
- **NVIDIA Nemotron 3** (Nano, Super, Ultra) do all the language reasoning.
- **Nebius AI Cloud** hosts the demo: one `cpu-d3` VM in eu-west1 runs the Docker image (API, built frontend, SQLite volume) behind Caddy; see `deploy/nebius/`.
- **Tavily** searches live supplier prices for parts the shop doesn't stock; Nemotron Nano turns the results into structured prices.

Feedback on the tools is in [docs/FEEDBACK.md](docs/FEEDBACK.md). The demo video script is [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) and the Devpost text is [docs/SUBMISSION.md](docs/SUBMISSION.md).

## Licence

MIT. See [LICENSE](LICENSE).

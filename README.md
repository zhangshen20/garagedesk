# GarageDesk

**Replace the phone call to his wife.** A no-typing back office for a one-owner mechanic shop: he says what he would have told his wife on the phone, NVIDIA Nemotron on Nebius Token Factory turns it into a GST tax invoice, his wife approves it with one tap from wherever she is, and the customer gets a "your car is ready" text.

Built for the Nebius x NVIDIA Global AI Hackathon (track: Best Apps & Agents) with a real workshop in Sunshine North, Melbourne. In the app the shop appears as **Sunshine Auto Care**.

> **Live demo:** owner app at https://66-201-4-40.sslip.io/owner (open it on an iPhone), dashboard at https://66-201-4-40.sslip.io/ and customer chat at https://66-201-4-40.sslip.io/chat, on a Nebius AI Cloud VM calling live Nemotron models. Use the HTTPS address on an iPhone: Safari only allows speech recognition on secure pages.
>
> Demo mode works with **no API keys at all**. Add a Nebius key and the same code runs on live Nemotron models.

## The owner this is for

The owner is a good mechanic. He is not comfortable with computers and doesn't type. His day is spent under cars, directing his staff, answering customers who walk in to ask "is it ready?", and ringing suppliers for parts. There are no job cards and no software: when a car is done he works out the charge on a calculator. Customers pay on EFTPOS.

His wife used to do the admin, including the GST tax invoices. She now works part-time somewhere else, so when a car is finished he phones her and tells her what work was done, the parts, and how much to charge, and she makes the tax invoice. If she can't answer, the customer waits.

GarageDesk takes that exact phone call. He says the same words to his phone instead of to his wife, and gets the same tax invoice.

Invoicing software assumes someone sitting at a desk. He will never be that person. So GarageDesk is built around five rules:

1. **Say it the way he'd say it on the phone. Never type.** His own words and his own figures, one big button.
2. **Works with dirty hands.** One press-and-hold button you can hit with a knuckle. No login mid-job.
3. **His numbers, read back before it leaves.** The amounts he says are the charge. The invoice is read to him in one sentence, and he says yes or no.
4. **His wife stays in control, from anywhere.** She approves every invoice with one tap on her phone.
5. **It knows the shop already.** Customer, car, rego and booked service come from the booking, so he only says what is different.

Success is one number: admin calls to his wife per day, from several to none.

## What it does

### For the owner: `/owner`, a phone web app on his home screen

One huge hold-to-talk button. No login, no forms, no app store.

| He does | GarageDesk does |
|---|---|
| Holds the button and says what he'd tell his wife: *"Corolla ABC123 is done. Front pads and machined the rotors. Pads 89, hour and a half labour."* | Nemotron 3 Nano routes it in under a second; Nemotron 3 Super turns it into line items as JSON; code finds the job, uses his figures as the charge, and fills only what he didn't say (labour at the shop's $120 an hour plus GST). The draft is read back out loud: *"Invoice for Maria's Toyota Corolla: brake pads front 89 dollars, 1.5 hours labour. 287 dollars including GST. Send it?"* He taps Send. |
| Takes a photo of a supplier receipt | A vision model on Token Factory (MiniCPM-V 4.5) reads it and adds the parts to the job, so he doesn't have to read them out |
| Says *"The CX-5 is waiting on parts till Thursday"* | Texts that customer, so fewer people walk in to ask |
| Taps Paid EFTPOS, or says *"Corolla paid on EFTPOS"* | Marks the invoice paid with the method and texts the receipt |
| Says *"need front pads for the Mazda"* | Finds the price (shop catalogue plus Tavily live search) and drafts a parts order that waits for approval |

The model never invents a price. The amounts he says are the charge; anything he leaves out comes from the shop's labour rate and parts list, and the read-back lets him correct it by just saying it again.

### For his wife: a link in a text

When he taps Send she gets a text with a signed link (`/approve/:id`). She sees the invoice with GST split out and taps **Approve and send**, or **Fix** with a note that goes back to him. Once she trusts it, small invoices can skip approval (`AUTO_APPROVE_INVOICE_UNDER_CENTS`). The dashboard is hers and the accountant's: jobs, invoices, payments, parts and approvals.

### Bookings from the shop's own website

Bookings made on the shop's website flow onto the board, and a job opens prefilled with customer, phone, car, rego and booked service, so he only says what was different. Marking a booking completed on the site starts an invoice draft, which still goes through his wife's approval. GarageDesk only reads from the site. See [docs/BOOKING_SITE_LINK.md](docs/BOOKING_SITE_LINK.md); the demo uses a mock week of bookings until the site exposes its read endpoint.

### For customers

"Your car is ready" with the GST tax invoice PDF, and a receipt when they pay. The phone line, SMS and web chat answer hours, book cars into a free bay, check "is my car ready?", reschedule, and take a message for anything the shop should decide (quotes, complaints).

### Build status

| Feature | Status |
|---|---|
| Owner iPhone app, hold-to-talk, read-back | Built |
| Talk-to-Invoice | Built |
| Photo of a supplier receipt adds parts to the job | Built |
| Wife approves or fixes from a text link | Built |
| "Car is ready" and status texts | Built |
| Paid on EFTPOS with receipt text | Built |
| Prefill jobs from the shop's booking website | Built (mock bookings until the site exposes its read endpoint) |
| Phone, SMS and web chat front desk; parts lookup and orders; daily report | Built |
| Quarterly GST summary for the BAS, CSV export | Next |
| Supplier receipt photos to expenses | Next |

### Nemotron tiers, each where it earns its keep

| Tier | Model (Nebius Token Factory id) | Used for |
|---|---|---|
| fast | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | Intent classification on every message; extracting prices from web search results |
| main | `nvidia/nemotron-3-super-120b-a12b` | Turning a mechanic's loose words ("pads", "5W-30", "hour and a half") into exact invoice lines; the tool-calling front desk and back office agents |
| deep | `nvidia/Nemotron-3-Ultra-550b-a55b` | The end-of-day report: reasons over cash, jobs, parts, overdue invoices and tomorrow's board in one pass |

All model calls go through Token Factory's OpenAI-compatible endpoint (`https://api.tokenfactory.nebius.com/v1/`) with native function calling. Swap any tier with `MODEL_FAST`, `MODEL_MAIN`, `MODEL_DEEP`. Token Factory has no speech model, so speech-to-text is the iPhone's own recognition through Safari's Web Speech API (which needs HTTPS; without it the page falls back to the keyboard's dictation button), and Twilio speech recognition on phone calls. Photos are read by a vision model on Token Factory and Nemotron does the reasoning.

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
owner ──iPhone: voice / receipt photo────▶ owner app ──┐
wife ───text link: Approve / Fix────────▶ approvals ──┤      ┌─ Nemotron Nano  (classify, extract)
customer ─phone/SMS/web chat────────────▶ front desk ─┼─▶ agent runner ──▶ Nemotron Super (invoice lines, tool calls)
scheduler ─4pm / 5:45pm─────────────────▶ reminders ──┘      ├─ Nemotron Ultra (daily report)
                                                 │           └─ vision model   (read receipt photos)  
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
- **Nebius AI Cloud** hosts the demo: one `cpu-d3` VM in eu-west1 runs the Docker image (API, built frontend, SQLite volume) behind Caddy with a Let's Encrypt certificate for the sslip.io name; see `deploy/nebius/`.
- **Tavily** searches live supplier prices for parts the shop doesn't stock; Nemotron Nano turns the results into structured prices.

Feedback on the tools is in [docs/FEEDBACK.md](docs/FEEDBACK.md). The demo video script is [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) and the Devpost text is [docs/SUBMISSION.md](docs/SUBMISSION.md).

## Licence

MIT. See [LICENSE](LICENSE).

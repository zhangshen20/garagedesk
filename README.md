# GarageDesk

**Replace the phone call to his wife.** A no-typing back office for a one-owner mechanic shop: he says what he would have told his wife on the phone, NVIDIA Nemotron on Nebius Token Factory turns it into a GST tax invoice, his wife approves it with one tap from wherever she is, and the customer gets a "your car is ready" text.

Built for the Nebius x NVIDIA Global AI Hackathon (track: Best Apps & Agents) with a real workshop in Sunshine North, Melbourne. In the app the shop appears as **Sunshine Auto Care**.

> **Live demo:** owner app at https://66-201-4-40.sslip.io/owner (open it on a phone, in any browser), dashboard at https://66-201-4-40.sslip.io/ and customer chat at https://66-201-4-40.sslip.io/chat, on a Nebius AI Cloud VM calling live Nemotron models.
>
> Demo mode works with **no API keys at all**. Add a Nebius key and the same code runs on live Nemotron models.

## The owner this is for

The owner is a good mechanic. He is not comfortable with computers and doesn't type. His day is spent under cars, directing his staff, answering customers who walk in to ask "is it ready?", and ringing suppliers for parts. There are no job cards and no software: when a car is done he works out the charge on a calculator. Customers pay on EFTPOS.

His wife used to do the admin, including the GST tax invoices. She now works part-time somewhere else, so when a car is finished he phones her and tells her what work was done, the parts, and how much to charge, and she makes the tax invoice. If she can't answer, the customer waits.

GarageDesk takes that exact phone call. He says the same words to his phone instead of to his wife, and gets the same tax invoice.

Invoicing software assumes someone sitting at a desk. He will never be that person. So GarageDesk is built around five rules:

1. **Say it the way he'd say it on the phone. Never type.** His own words and his own figures, one big button.
2. **Works with dirty hands.** One big button: hold it and talk, let go to send (or tap to start and tap to stop). No login mid-job.
3. **His numbers, read back before it leaves.** The amounts he says are the charge. The invoice is read to him in one short breath, and he says yep or says it again.
4. **His wife stays in control, from anywhere.** She approves every invoice with one tap on her phone.
5. **It knows the shop already.** Customer, car, rego and booked service come from the booking, so he only says what is different.

Success is one number: admin calls to his wife per day, from several to none.

## What it does

### For the owner: `/owner`, a phone web app on his home screen

One huge talk button: hold it and talk, let go to send (a tap to start and a tap to stop works too). The phone records his voice and the server turns it into text, so it works in Chrome, Safari or any phone browser. Replies come back in a natural voice, short by default, and end with the next question so a "yep" does it. No login, no forms, no app store.

| He does | GarageDesk does |
|---|---|
| Holds the button and says what he'd tell his wife, then lets go: *"Corolla ABC123, front pads, hour and a half, 350 all up."* | Nemotron 3 Nano routes it in under a second; Nemotron 3 Super turns it into line items as JSON; code finds the job and uses his figures as the charge: a price per item, a labour amount, or a total ("350 all up" puts the balance after parts on the labour line). Only prices he didn't say come from the shop's parts list, and labour from $120 an hour plus GST. The draft is read back out loud: *"Maria's Corolla. Front brake pads and an hour and a half labour. Three hundred and fifty dollars all up. Send it to Jenny?"* He says "yep" and it goes to his wife. "Hear every line" reads each line and the GST. |
| Says *"Liam's Ranger, did the battery again, same as last time"* | Looks up the Ranger's last visit and drafts the same battery and labour at last visit's figures: $366.00 all up |
| Corrects or adds: *"actually make it 380 all up"*, *"add oil and a filter to that"* | Changes only what he changed, on the job he was just talking about |
| Asks *"when was Maria's Corolla last in?"*, *"what's he driving?"*, or says *"remember Jack always pays cash"* | Answers from the shop's records and remembers facts he gives it |
| Says *"Find yesterday's jobs and prepare invoice"* | Nemotron Nano pulls out the day, rego, customer, car or status; code finds the job (Dan's X-Trail, finished yesterday) and the invoice draft is read back: $240.90 all up |
| Taps "Add parts from a receipt photo" on the draft and photographs the supplier's receipt | A vision model on Token Factory (MiniCPM-V 4.5) reads it, adds each part to the job at cost, books the receipt as a parts expense with its GST, and reads back the new total |
| Says *"The CX-5 is waiting on parts till Thursday"* | Texts that customer, so fewer people walk in to ask |
| Hears *"Jenny approved Maria's Corolla… Say yes when they've paid on EFTPOS"* and says "yes", taps Paid EFTPOS, or says *"Corolla paid on EFTPOS"* | Marks the invoice paid with the method and texts the receipt |
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
| Owner phone app, hold to talk in any browser, spoken read-back | Built |
| Find jobs by day, rego, customer, car or status | Built |
| Remembers the conversation, each customer and car, past visits and his notes; mechanic know-how | Built |
| Talk-to-Invoice | Built |
| Supplier receipt photo adds parts and books the expense | Built |
| Wife approves or fixes from a text link | Built |
| "Car is ready" and status texts | Built |
| Paid on EFTPOS with receipt text | Built |
| Prefill jobs from the shop's booking website | Built (mock bookings until the site exposes its read endpoint) |
| Phone, SMS and web chat front desk; parts lookup and orders; daily report | Built |
| Quarterly GST summary for the BAS, CSV export | Next |

### Nemotron tiers, each where it earns its keep

| Tier | Model (Nebius Token Factory id) | Used for |
|---|---|---|
| fast | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | Intent classification on every message; pulling the day, car, customer, rego or status out of the owner's words; extracting prices from web search results |
| main | `nvidia/nemotron-3-super-120b-a12b` | Turning a mechanic's loose words ("pads", "5W-30", "hour and a half") into exact invoice lines; the tool-calling front desk and back office agents |
| deep | `nvidia/Nemotron-3-Ultra-550b-a55b` | The end-of-day report: reasons over cash, jobs, parts, overdue invoices and tomorrow's board in one pass |

All model calls go through Token Factory's OpenAI-compatible endpoint (`https://api.tokenfactory.nebius.com/v1/`) with native function calling. Swap any tier with `MODEL_FAST`, `MODEL_MAIN`, `MODEL_DEEP`. Token Factory has no speech models, so two small open models run on the same Nebius VM: NVIDIA Parakeet TDT 0.6B v2 (int8 ONNX, about 0.6 s per recording on 2 vCPUs, and much better than a small Whisper with accented English) transcribes the owner's recordings (`POST /api/owner/audio`), and misheard makes, models and plates are put back from the cars in the shop; faster-whisper is the fallback (`STT_ENGINE=whisper`), and Kokoro 82M (Apache-2.0) speaks the replies (`GET /api/tts`). Safari's own speech recognition and the browser's voice are fallbacks. Twilio speech recognition handles phone calls. Photos are read by a vision model on Token Factory and Nemotron does the reasoning.

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
- `backend/app/agent/joblookup.py`: finds jobs by day, rego, customer, car or status. `backend/tests/owner_utterances.py` holds 47 real owner phrasings run on every PR; `backend/scripts/owner_eval_live.py` runs them on live Nemotron.
- `backend/app/agent/memory.py`, `memory_tools.py`, `knowhow.py`: the owner agent's memory (recent turns, past visits, facts he asked it to keep) and its mechanic knowledge (common jobs, typical times, misheard car names). `backend/scripts/memory_live_eval.py` runs 12 multi-turn conversations on live Nemotron.
- `backend/app/voice/`: the short spoken read-back and the "yep" that answers the last question; `backend/app/agent/stt.py` and `backend/app/voice/tts.py` for speech.
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

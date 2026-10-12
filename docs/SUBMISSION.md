# Devpost submission draft

**Project name:** GarageDesk
**Tagline:** A back office the mechanic never types into: he talks or snaps his job card, Nemotron makes the GST invoice, his wife approves from her phone.
**Category:** Best Apps and Agents
**Side prize:** Best Use of Tavily (live supplier price lookup)

## Inspiration
We built GarageDesk with a real three-bay workshop in Sunshine North, Melbourne. The owner is a very good mechanic. He doesn't type and he isn't comfortable with computers. His day is spent under cars, telling his staff what to do, answering customers who walk in to ask if their car is ready, and ringing suppliers for parts. His job cards are on paper, his customers pay on EFTPOS, and he has no accounting software.

His wife used to do the admin, including every GST tax invoice. Then she took a part-time job elsewhere. Now, whenever a car is finished, he phones her and she makes the invoice over the phone. When she can't answer, the customer waits.

Every invoicing app assumes someone sitting at a desk. He will never be that person. The shop already has a website with online booking, and it didn't take a single minute of admin off him. So we set ourselves one goal: **replace the phone call to his wife.**

## What it does
The owner never types. He speaks, takes a photo, or taps once.

- **Talk-to-Invoice.** He holds one big button on his iPhone and says the job in workshop slang: *"Corolla ABC123 done, front pads, machined the rotors, hour and a half."* GarageDesk finds the car, prices the parts from the shop's catalogue and the labour from his rate, and reads it back: *"Invoice for Maria's Toyota Corolla: 1.5 hours labour and brake pads front. 328.90 dollars including GST. Send it?"* He taps Send.
- **Photograph the job card.** He already writes job cards on paper, so a photo works too. A vision model reads his handwriting and the same pipeline builds the invoice.
- **His wife approves from anywhere.** Instead of a phone call she gets a text with a link, checks the invoice with GST shown, and taps Approve, or Fix with a note that goes back to him. She stays in control of the books without being in the shop.
- **"Your car is ready."** Once she approves, the customer gets a text with the GST tax invoice PDF. *"The CX-5 is waiting on parts till Thursday"* becomes a text to that customer too, so fewer people walk in to ask.
- **Paid on EFTPOS, one tap.** The invoice is marked paid with the method and the receipt is texted. The shop has no accounting software; GarageDesk is the books.
- **It knows the shop.** Bookings from the shop's own website flow onto the board and open as prefilled job cards, so customer, car, rego and service are already there and he only says what's different. GarageDesk only reads from the site.
- **The rest of the desk, already live:** an agent that answers phone calls, SMS and web chat (hours, bookings into a free bay, "is my car ready?", reschedules, messages for the owner); parts lookup with Tavily live search and purchase orders that wait for approval; reminder texts to tomorrow's customers; and an end-of-day report from Nemotron 3 Ultra.

## How we built it
FastAPI + SQLModel backend, a React/Tailwind dashboard for the wife and accountant, a phone web app for the owner that he adds to his iPhone home screen (no app store), all in one Docker image on a Nebius AI Cloud VM. Every model call goes to Nebius Token Factory's OpenAI-compatible API with native function calling, and each NVIDIA Nemotron 3 tier does the job it is best at:
- **Nemotron 3 Nano** classifies every inbound message and turns web search results into structured prices. Cheap, fast, called constantly.
- **Nemotron 3 Super** turns a mechanic's loose speech ("pads", "5W-30", "hour and a half") into exact invoice lines with tool calls against the shop's catalogue, jobs and customers, and runs the front desk and back office tool-calling agents.
- **Nemotron 3 Ultra** writes the end-of-day report, the one place where reasoning over the whole day is worth the bigger model.
- A **vision model on Token Factory** (MiniCPM-V 4.5) transcribes photos of handwritten job cards, and Nemotron Super reasons over what it read.

The model never sets a price: Nemotron extracts *what* was done, and plain code prices it from the shop's catalogue and labour rate. Saying a job again replaces its lines, so a correction is just saying it right.

Token Factory has no speech-to-text model, so the owner app uses the iPhone's own speech recognition through Safari's Web Speech API (which is why the demo is served over HTTPS), and phone calls use Twilio's speech recognition. Approve links are HMAC-signed, so his wife needs no account or password. A deterministic mock drives the same tools, so tests, CI and a keyless demo exercise the real agent loop.

The design follows five rules written for this owner: speak, snap or tap, never type; works with dirty hands; read it back before it leaves; his wife stays in control from anywhere; it already knows the shop.

## Challenges
- **Designing for someone who will never open a dashboard.** Our first version was a capable AI back office with a dashboard and a chat box, which was exactly the interface the owner couldn't use. Rebuilding around his voice, his camera and one button was the real work.
- **Making an agent safe for real money.** Nothing that leaves the shop goes without a person: the owner hears every total read back, his wife approves every invoice, and supplier orders wait for a tap. The agent never invents a price.
- **Shop slang.** "Pads", "a full service", "hour and a half" have to become exact parts, quantities and labour lines priced from the shop's list.
- **Reasoning tokens and output budgets** on Token Factory, described under "What we learned".

## Accomplishments
A complete product built around one real person: bookings, bays, job cards, GST tax invoice PDFs, payments, parts orders, approvals, an outbox, reminders and a daily report, with a front end that a mechanic who doesn't type can actually use. Live on Nebius, on live Nemotron.

## What we learned
Splitting the work across three Nemotron tiers paid off. Nano with thinking turned off classifies a message in under half a second, Super drives each agent turn in 2-5 seconds including its tool calls, and Ultra writes the whole end-of-day report in about 5 seconds. In live testing every tool chain (find customer, check availability, book; price lookup, parts order, approval; job done, GST invoice) completed first time with clean arguments.

The surprise was reasoning tokens. They count against `max_tokens`, so our first live run returned truncated JSON from Nano and a daily report from Ultra that stopped mid-sentence. Turning thinking off for the one-shot Nano jobs and giving Ultra room to think fixed both. That lesson now shapes how we budget every call: small models answer directly, and the big model gets space to reason.

The bigger lesson was about the user. The most useful thing an AI agent can do for this owner isn't a smarter answer; it's removing the screen.

## What's next
- Put it in the owner's hands with his real labour rate and price list, and measure the number that matters: admin calls to his wife per day.
- Switch the booking link from demo bookings to the live website once it exposes its read endpoint.
- A quarterly GST summary for the BAS and a CSV for the accountant.
- Supplier receipt photos recorded as expenses with GST.
- A spoken 30-second end-of-day summary instead of a written report.
- WhatsApp voice notes as another way to talk to it, then a second shop.

## Built with
python, fastapi, sqlmodel, react, typescript, tailwind, docker, nebius-token-factory, nebius-ai-cloud, nvidia-nemotron, tavily, twilio

## Links
- Repo: https://github.com/zhangshen20/garagedesk (MIT)
- Demo URL *(HTTPS goes live with the next redeploy; check before submitting, fallback http://66.201.4.40/)*: https://66-201-4-40.sslip.io/owner (owner app, best on an iPhone), https://66-201-4-40.sslip.io/ (dashboard), https://66-201-4-40.sslip.io/chat (customer chat)
- Video: (to fill)

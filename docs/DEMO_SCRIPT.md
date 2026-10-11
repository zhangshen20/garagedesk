# Demo video script (target 2:45, max 3:00)

Record at 1080p, dashboard in a browser on the left two-thirds, phone-sized window on the right for the customer side. Voice-over in plain speech; the on-screen action carries it.

## 0:00–0:20  The problem
*On screen: the Today board with six cars and the Agent activity feed scrolling.*
"This is Sunshine Auto Care, a three-bay mechanic in Melbourne's west. One owner, one apprentice. The phone rings forty times a day, and every call is a booking, a 'is my car ready', or a parts price. GarageDesk is an AI front desk and back office that takes that work off the owner, running NVIDIA Nemotron on Nebius Token Factory."

## 0:20–1:00  A customer calls
*On screen: Inbox → Simulate → Phone call. Type: "Hi, it's Ben Hall, Toyota Camry rego BHX442, due for a logbook service, anything tomorrow morning?"*
"A customer calls. Nemotron Nano classifies the intent in a few hundred milliseconds, then Nemotron Super runs the conversation with tools: it finds or creates the customer, checks bay availability, and books the car."
*Show the reply with reference SAC-00xx, then expand the tool steps in the transcript. Flip to the Today board: the new card appears in tomorrow's list.*
"Everything it did is on the record: the tool calls, the arguments, the results."

## 1:00–1:30  Text message: is my car ready?
*Simulate → SMS from +61 411 000 001: "is my corolla ready yet?"*
"Maria texts. The agent knows her by number, finds her job card, and answers: waiting on a part. No one in the workshop had to stop."

## 1:30–2:10  The owner clears the desk
*Open "Ask the desk". Type: "order front brake pads for the corolla on job 3 from whoever is cheapest".*
"The owner talks to the back-office agent like a colleague. It looks up prices across suppliers, with Tavily web search structured by Nemotron Nano, drafts the purchase order, and stops."
*Go to Approvals. Show the pending order with price. Tap Approve. Go to Outbox: the email to Burson is there.*
"Money leaving the shop always waits for a tap. That's the rule that makes this safe for a real business."
*Back to Ask the desk: "job 4 is finished, invoice it". Open the PDF.*
"Job done, GST tax invoice generated, texted to the customer. Twenty seconds instead of ten minutes."

## 2:10–2:40  End of day
*Report page → Generate.*
"At 5:45 every day Nemotron 3 Ultra reads the whole day, cash in and out, GST, overdue invoices, tomorrow's board, and writes the owner a report with one concrete suggestion. This is the one call where the biggest model earns its price."
*Scroll the report slowly.*

## 2:40–2:55  Close
*Cut to the architecture diagram from the README.*
"Three Nemotron tiers, each where it earns its keep, all served by Nebius Token Factory's OpenAI-compatible API. Open source, MIT, one Docker image. GarageDesk."

## Shots checklist
- [ ] Today board with cards and KPIs
- [ ] Simulated call with tool steps expanded
- [ ] SMS status reply
- [ ] Owner chat → approval → outbox email
- [ ] Invoice PDF open
- [ ] Daily report
- [ ] README architecture diagram

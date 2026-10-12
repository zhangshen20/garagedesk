# Demo video script (target 2:45, max 3:00)

**Story:** one real moment. A car is finished, the owner is under another one, and today he would have to ring his wife to make the invoice. In the video he doesn't.

> **Status: draft.** Scenes marked **[BUILDING]** depend on features other threads are building now (owner app, Talk-to-Invoice, job card photo, wife approval, status texts, EFTPOS paid, booking prefill). Screen names and taps in those scenes are placeholders until the features land; this script and the shot list get finalised then. Scenes marked **[LIVE]** can be recorded today.

## Setup

- **Three screens.** Owner: an iPhone (or Safari's iPhone view) with the owner app added to the home screen. Wife: a second phone, or a phone-sized browser window, showing her text messages / the outbox. Customer: a third phone-sized window showing their texts. Desktop dashboard at http://66.201.4.40/ for the money shots.
- **Live models.** The demo site runs real Nemotron calls, so a turn takes 2-5 seconds. Talk over the pause instead of cutting; the wait is honest and short.
- **Before recording:** make sure a booking for a Toyota Corolla, rego ABC123, is on today's board (from the booking site prefill, or seeded), press Generate once on the Report page so the Ultra report is ready, and leave the Approvals page empty.
- **Voice input:** use iPhone dictation (the microphone key) in the owner app. If dictation is unreliable on the day, type the same sentence and say so in the voice-over; don't fake it.
- **Real footage helps.** A few seconds of a real workshop (hands on a car, a paper job card on the bench) for the opening and close beats any screen recording. No faces or plates needed.

## 0:00–0:20  The problem  **[LIVE]**
*On screen: workshop footage, then a paper job card on the bench, then a phone showing "Calling: Wife".*

"This is a real three-bay workshop in Sunshine North, Melbourne. The owner fixes cars. He doesn't type and he doesn't use computers. His wife used to do the tax invoices, but she works part-time somewhere else now. So every time a car is finished, he rings her, and she makes the invoice over the phone. If she can't pick up, the customer waits."

## 0:20–1:05  Talk-to-Invoice  **[BUILDING]**
*On screen: the owner app on the iPhone. One huge button. Press and hold. Say:*
*"Corolla ABC123 done. Full service, oil and filter, plus front pads. Hour and a half labour."*

"GarageDesk replaces that phone call. He holds one button and says what he did, in his own words."

*The draft invoice appears: customer name pulled from the booking, line items, labour, GST, total. The app reads it back aloud: "Invoice for Maria Lopez, 412 dollars 50 including GST. Send it?"*

"Nemotron 3 Super on Nebius Token Factory turns shop talk, 'pads', 'hour and a half', into exact invoice lines. Prices come from the shop's own list, never made up. The customer and car were already known from the booking on the shop's website, so he only said what was different. Everything is read back before it goes anywhere."

*He taps Send (or says "send").*

## 1:05–1:25  Or just photograph the job card  **[BUILDING]**
*On screen: owner app, camera button, photo of a handwritten job card. A draft invoice appears with the same layout.*

"He already writes job cards on paper. So he can also just take a photo. A vision model on Token Factory reads his handwriting, and Nemotron builds the same invoice. No new habit."

## 1:25–1:50  His wife approves with one tap  **[BUILDING]**
*Cut to the wife's phone: a text "Invoice #1042, Maria Lopez, $412.50 incl. GST. Approve / Fix". Tap the link, tap Approve.*

"Instead of a phone call, his wife gets a text. She checks it on her break and taps Approve. She stays in control of the books without being in the shop. A five-minute interruption for two people becomes a three-second tap for one."

## 1:50–2:10  The customer gets a text  **[BUILDING]**
*Cut to the customer's phone: "Your Corolla is ready at Sunshine Auto Care. Invoice attached, $412.50." Open the PDF: an Australian tax invoice with ABN and GST.*
*Back to the owner app. Hold the button: "Mazda's waiting on parts till Thursday." Show that customer's text arriving.*

"The customer knows the car is ready before they walk in. And the same button sends quick updates, so nobody needs to come in and ask."

## 2:10–2:25  Paid on EFTPOS  **[BUILDING]**
*Customer pays at the counter. Owner holds the button: "Corolla paid on EFTPOS." On the dashboard, the invoice turns Paid. Scroll to the GST summary for the quarter.*

"The shop has no accounting software. Now it doesn't need any. Each payment is recorded by voice, and his wife or the accountant gets the quarter's GST summary ready for the BAS."

## 2:25–2:40  The rest of the desk  **[LIVE]**
*Fast montage, 3-4 seconds each: customer chat booking a service at http://66.201.4.40/chat; owner saying "need front pads for the Corolla" and an order waiting on Approvals with a Tavily-sourced price; the Nemotron 3 Ultra end-of-day report.*

"Behind that button is a whole back office: an agent that answers customers and books cars, parts prices searched live with Tavily, and an end-of-day report from Nemotron 3 Ultra."

## 2:40–2:55  Close  **[LIVE]**
*On screen: the owner back under a car. Text overlay: "Admin calls to his wife: several a day → none." Then the GarageDesk name and repo URL.*

"Nemotron Nano, Super and Ultra, each where it earns its keep, on Nebius Token Factory. Open source under MIT. GarageDesk: he fixes cars, it does the paperwork."

## Shot list

| # | Shot | Status |
|---|---|---|
| 1 | Workshop footage, paper job card, "Calling: Wife" phone screen | Can record now |
| 2 | Owner app: hold to talk, draft invoice, read-back, send | Waiting on owner app and Talk-to-Invoice |
| 3 | Owner app: photo of a paper job card to invoice draft | Waiting on job card photo feature |
| 4 | Wife's phone: text with Approve link, tap Approve | Waiting on wife approval |
| 5 | Customer's phone: "car is ready" text, invoice PDF open | Waiting on status texts (PDF exists today) |
| 6 | Owner: "waiting on parts" update, customer text | Waiting on status texts |
| 7 | "Paid on EFTPOS", invoice turns Paid, GST summary | Waiting on EFTPOS paid and GST summary |
| 8 | Customer chat booking at /chat | Can record now |
| 9 | Parts order with Tavily price waiting on Approvals | Can record now |
| 10 | Ultra daily report | Can record now |
| 11 | Close: owner under a car, the calls-to-wife number, repo URL | Can record now |

## After recording
1. Upload to YouTube as Public or Unlisted (Devpost accepts both), title "GarageDesk: no-typing tax invoices for a mechanic shop (Nebius x NVIDIA hackathon)".
2. Paste the YouTube link into docs/SUBMISSION.md "Links" and into the Devpost form.
3. Devpost form fields come straight from docs/SUBMISSION.md: tagline, category (Best Apps and Agents), description sections, "Built with", repo link, demo URL, video link, and the feedback text from docs/FEEDBACK.md.
4. Submit by Oct 28 to leave two days of buffer before the Oct 30, 10:00am PDT deadline.

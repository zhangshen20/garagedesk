# Demo video script (target 2:45, max 3:00)

**Story:** one real moment. A car is finished, and today the owner would put down his calculator and ring his wife at her other job: "Corolla's done, front pads and machined the rotors, pads 89, hour and a half labour." She would make the tax invoice. In the video he says exactly the same words, to his phone instead, and never touches a keyboard.

Every scene below runs on the live demo at https://66-201-4-40.sslip.io.

## Setup

- **Owner:** a real iPhone with https://66-201-4-40.sslip.io/owner added to the home screen (Safari, Share, Add to Home Screen). Record it with the iPhone's screen recording, plus a hand-held shot of someone in the workshop holding the button.
- **Wife:** a second phone. The approve link arrives on the Outbox page of the dashboard (or by SMS once Twilio is on); open it on this phone.
- **Customer:** the customer's texts are also on the Outbox page. A phone-sized browser window on that page works as "the customer's phone".
- **Dashboard:** https://66-201-4-40.sslip.io/ on a laptop for the closing shots.
- **Before each take:** tap **Reset demo data** at the bottom of the dashboard's sidebar, so the Corolla (ABC123) and the CX-5 are in the workshop and nothing is waiting for approval. Press Generate once on the Report page so the Ultra report is ready. Say the line once on a test run so the first live Nemotron call is warm, then reset again.
- **Live models:** each spoken job takes 2-5 seconds and a receipt photo about 6 seconds. Keep the camera on the phone and talk over the pause instead of cutting; the wait is honest and short.
- **Props:** a calculator on the bench, and a supplier's parts receipt for the photo scene. No faces or real number plates are needed anywhere.

## 0:00–0:20  The problem
*On screen: the owner wiping his hands, tapping numbers into a calculator on the bench, then picking up his phone: "Calling: Wife".*

"This is a real workshop in Sunshine North, Melbourne. The owner is a great mechanic who doesn't use computers and doesn't type. When a car is done, he works out the price on a calculator and rings his wife, and tells her what he did and how much to charge. She makes the tax invoice. But she works part-time somewhere else now, and if she can't pick up, the customer waits. GarageDesk replaces that phone call."

## 0:20–1:15  He says what he'd have told her
*Owner app on the iPhone. Hold the big round button and say, the way he'd say it to his wife: "Corolla ABC123 is done. Front pads and machined the rotors. Pads 89, hour and a half labour."*

"Same words, same numbers, but he says them to his phone. Nemotron 3 Nano works out what he's asking for in under a second, and Nemotron 3 Super turns it into invoice lines. His figures are the charge. Anything he doesn't say, like the labour rate, comes from the shop's own settings, never from the AI's imagination. And Maria and her Corolla were already on the board from her online booking, so he didn't have to say who it was for."

*The phone reads back: "Invoice for Maria's Toyota Corolla: brake pads front 89 dollars, 1.5 hours labour. 287 dollars including GST. Send it?" Tap Send.*

"It reads his numbers back, the way his wife would have. If something's off, he just says it again."

## 1:15–1:25  A parts receipt instead of a list
*Tap the photo button and shoot the supplier's receipt. The parts appear on the job.*

"If there's a long list of parts, he doesn't read it out. He photographs the supplier's receipt, and a vision model on Nebius puts the parts on the job."

## 1:25–1:55  His wife approves from her other job
*Second phone: the text arrives. Tap the link, show the invoice with GST split out, tap "Approve and send".*

"Instead of a phone call, his wife gets a text. She checks the invoice on her break and taps once. She stays in control of the books without being in the shop. If something's wrong she taps Fix, writes a note, and it goes back to him. A five-minute interruption for two people becomes a three-second tap for one."

## 1:55–2:15  The customer, and getting paid
*Customer's phone (Outbox): "Hi Maria, your Toyota Corolla is ready to collect. Tax invoice INV-… for $287.00 inc GST". Open the PDF: an Australian tax invoice with ABN and GST. Back on the owner app, tap Paid EFTPOS on the Corolla; the receipt text appears.*

"Maria knows her car is ready before she walks in, and she gets a proper Australian tax invoice. She pays on the EFTPOS terminal, he taps Paid, and the receipt goes out. The shop has no accounting software, and now it doesn't need any."

## 2:15–2:35  The rest of his day
*Hold the button: "The CX-5 is waiting on parts till Thursday." Show that customer's text. Then a fast montage, 3 seconds each: a customer booking a service in the web chat; "need front pads for the Mazda" turning into a parts order with a Tavily-found price waiting on Approvals; the Nemotron 3 Ultra end-of-day report.*

"Status updates text the customer, so nobody needs to come in and ask. And behind that one button is a whole back office: a front desk that answers customers and books cars, parts prices searched live with Tavily, and an end-of-day report written by Nemotron 3 Ultra."

## 2:35–2:50  Close
*Back to the owner under a car. Text overlay: "Admin calls to his wife: several a day → none." Then the GarageDesk name and the repo URL.*

"No keyboard, no job cards, no new habits. Nemotron Nano, Super and Ultra plus a vision model, all on Nebius Token Factory. Open source under MIT. GarageDesk: he fixes cars, it does the paperwork."

## Shot list

| # | Shot | Where |
|---|---|---|
| 1 | Owner with a calculator, then "Calling: Wife" on his phone | Workshop footage |
| 2 | Hold-to-talk with his own figures, read-back audible, tap Send | Owner app on the iPhone |
| 3 | Photo of a supplier receipt, parts land on the job | Owner app on the iPhone |
| 4 | Text arrives, approve page with GST, tap "Approve and send" | Second phone |
| 5 | "Your car is ready" text and the invoice PDF | Outbox, phone-sized window |
| 6 | Paid EFTPOS tap and receipt text | Owner app, then Outbox |
| 7 | "CX-5 waiting on parts" by voice, customer text | Owner app, then Outbox |
| 8 | Customer booking in the web chat | /chat |
| 9 | Parts order with a Tavily price waiting on Approvals | Dashboard |
| 10 | Ultra end-of-day report | Dashboard, Report page |
| 11 | Close: owner under a car, the calls-to-wife number, repo URL | Workshop footage plus overlay |

## After recording
1. Upload to YouTube as Public or Unlisted (Devpost accepts both), title "GarageDesk: a back office the mechanic never types into (Nebius x NVIDIA hackathon)".
2. Paste the YouTube link into docs/SUBMISSION.md "Links" and into the Devpost form.
3. Devpost form fields come straight from docs/SUBMISSION.md: tagline, category (Best Apps and Agents), description sections, "Built with", repo link, demo URL, video link, and the feedback text from docs/FEEDBACK.md.
4. Submit by Oct 28 to leave two days of buffer before the Oct 30, 10:00am PDT deadline.

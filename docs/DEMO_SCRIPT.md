# Demo video script (target 2:45, max 3:00)

**Story:** one real moment. A car is finished, the owner is under another one, and today he would have to ring his wife at her other job to make the invoice. In the video he never touches a keyboard.

Every scene below runs on the live demo today. The one prerequisite is the HTTPS address, which the iPhone needs for speech recognition: check that https://66-201-4-40.sslip.io/owner opens before recording.

## Setup

- **Owner:** a real iPhone with https://66-201-4-40.sslip.io/owner added to the home screen. Record it with the iPhone's screen recording, plus a hand-held shot of someone in the workshop holding the button.
- **Wife:** a second phone. The approve link arrives on the Outbox page of the dashboard (or by SMS once Twilio is on); open it on this phone.
- **Customer:** the customer's texts are also on the Outbox page. A phone-sized browser window on that page works as "the customer's phone".
- **Dashboard:** https://66-201-4-40.sslip.io/ on a laptop for the closing shots.
- **Before recording:** reset the demo data so the Corolla (ABC123) is in the workshop and nothing is waiting for approval. Press Generate once on the Report page so the Ultra report is ready. Say each line once on a test run so the first live Nemotron call is warm.
- **Live models:** each spoken job takes 2-5 seconds and a photo about 6 seconds. Keep the camera on the phone and talk over the pause instead of cutting; the wait is honest and short.
- **Have a handwritten job card ready**, written the way the owner writes them. No faces or real number plates are needed anywhere.

## 0:00–0:20  The problem
*On screen: the owner under a car, a paper job card on the bench, a phone buzzing next to it showing "Calling: Wife".*

"This is a real workshop in Sunshine North, Melbourne. The owner is a great mechanic who doesn't use computers and doesn't type. His wife did the tax invoices, but she works part-time somewhere else now. So when a car is finished, he rings her at her other job to make the invoice. If she can't pick up, the customer waits. GarageDesk replaces that phone call."

## 0:20–1:05  He says the job
*Owner app on the iPhone. Hold the big round button and say: "Corolla ABC123 done. New front pads, machined the rotors, hour and a half."*

"He holds one button and says what he did, the way he'd say it to an apprentice. Nemotron 3 Nano works out what he's asking for in under a second. Nemotron 3 Super turns the slang into invoice lines. Then plain code prices the parts from the shop's own list and the labour from his hourly rate. The model never invents a price. And the customer and car were already on the board from her online booking, so he only said what was different."

*The phone reads back: "Invoice for Maria's Toyota Corolla: 1.5 hours labour and brake pads front. 328.90 dollars including GST. Send it?" Tap Send.*

## 1:05–1:25  Or he photographs the paper card
*Tap "Photo of job card" and shoot the handwritten card. The same read-back appears.*

"He already writes job cards on paper, so a photo works too. A vision model on Nebius reads his handwriting, and Nemotron does the rest. No new habit."

## 1:25–1:55  His wife approves from her other job
*Second phone: the text arrives. Tap the link, show the invoice with GST split out, tap "Approve and send".*

"Instead of a phone call, his wife gets a text. She checks the invoice on her break and taps once. She stays in control of the books without being in the shop. If something's wrong she taps Fix, writes a note, and it goes back to him. A five-minute interruption for two people becomes a three-second tap for one."

## 1:55–2:15  The customer, and getting paid
*Customer's phone (Outbox): "Hi Maria, your Toyota Corolla is ready to collect. Tax invoice INV-… for $328.90 inc GST". Open the PDF: an Australian tax invoice with ABN and GST. Back on the owner app, tap Paid EFTPOS on the Corolla; the receipt text appears.*

"Maria knows her car is ready before she walks in, and she gets a proper Australian tax invoice. She pays on the EFTPOS terminal, he taps Paid, and the receipt goes out. The shop has no accounting software, and now it doesn't need any."

## 2:15–2:35  The rest of his day
*Hold the button: "The CX-5 is waiting on parts till Thursday." Show that customer's text. Then a fast montage, 3 seconds each: a customer booking a service in the web chat; "need front pads for the Mazda" turning into a parts order with a Tavily-found price waiting on Approvals; the Nemotron 3 Ultra end-of-day report.*

"Status updates text the customer, so nobody needs to come in and ask. And behind that one button is a whole back office: a front desk that answers customers and books cars, parts prices searched live with Tavily, and an end-of-day report written by Nemotron 3 Ultra."

## 2:35–2:50  Close
*Back to the owner under a car. Text overlay: "Admin calls to his wife: several a day → none." Then the GarageDesk name and the repo URL.*

"Speak, snap, tap. Nemotron Nano, Super and Ultra plus a vision model, all on Nebius Token Factory. Open source under MIT. GarageDesk: he fixes cars, it does the paperwork."

## Shot list

| # | Shot | Where |
|---|---|---|
| 1 | Owner under a car, paper job card, "Calling: Wife" on a phone | Workshop footage |
| 2 | Hold-to-talk with the read-back audible, tap Send | Owner app on the iPhone |
| 3 | Photo of a handwritten job card, same read-back | Owner app on the iPhone |
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

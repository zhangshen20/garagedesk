# Demo video script (target 2:45, max 3:00)

The story is one real moment: the owner finishes a car and never touches a keyboard. Shoot the owner app on a real iPhone (screen recording plus a hand-held shot of someone in the workshop holding the button), the approve page on a second phone, and the dashboard on a laptop for the closing shots.

- Owner app: https://66-201-4-40.sslip.io/owner (HTTPS is needed for the iPhone's speech recognition; add it to the home screen first)
- Dashboard: https://66-201-4-40.sslip.io/
- The approve link arrives in the Outbox page (or by SMS once Twilio is on). Open it on the second phone.

Before recording: reset the demo data so the Corolla (ABC123) is in the workshop and nothing is waiting for approval. Say each line once on a test run so the first live Nemotron call is warm. Each spoken job takes 2-5 seconds; keep the camera on the phone through the pause.

## 0:00–0:20  The problem
*On screen: the owner under a car, phone buzzing on the bench.*
"This is Sunshine North Mechanic in Melbourne's west. The owner is a great mechanic who doesn't use computers. His wife does the invoices, but she works part-time now, so when a car is finished he rings her at her other job to make the tax invoice. GarageDesk replaces that phone call."

## 0:20–1:05  He says the job
*Owner app on the iPhone. Hold the big orange button and say: "Corolla ABC123 done. New front pads, machined the rotors, hour and a half."*
"He holds one button and says what he did, the way he'd say it to an apprentice. Nemotron Nano routes it in under a second, Nemotron Super turns the slang into line items, and the code prices the parts from the shop's own catalogue and the labour from his rate. The model never invents a price."
*The phone reads back: "Invoice for Maria's Toyota Corolla: 1.5 hours labour and brake pads front. 328.90 dollars including GST. Send it?" Tap Send.*

## 1:05–1:30  Or he photographs the paper card
*Tap "Photo of job card" and shoot a handwritten card.*
"He already writes job cards on paper, so a photo works too. A vision model on Nebius reads the handwriting; Nemotron Super does the rest."

## 1:30–2:00  His wife approves from her other job
*Second phone: the text arrives, tap the link, show the invoice with GST split, tap "Approve and send".*
"His wife gets a text, checks the invoice on her break, and taps once. She stays in control of the books without being in the shop. If something's wrong she taps Fix, types a note, and it goes back to him."

## 2:00–2:20  The customer, and getting paid
*Outbox (or the customer's phone): "Hi Maria, your Toyota Corolla is ready to collect. Tax invoice INV-… for $328.90 inc GST". Back on the owner app, the car shows "Paid EFTPOS"; tap it.*
"Maria gets her car-ready text and a proper Australian tax invoice. She pays on the EFTPOS terminal, he taps Paid, and the receipt goes out."

## 2:20–2:40  The rest of his day
*Hold the button: "The CX-5 is waiting on parts till Thursday." Then cut to the dashboard: Today board, Approvals, the end-of-day report.*
"Status updates text the customer so they stop walking in to ask. The phone line, bookings, parts orders and the 5:45 report written by Nemotron 3 Ultra run in the background."

## 2:40–2:55  Close
*Cut to the architecture diagram from the README.*
"Speak, snap, tap. Nemotron Nano, Super and Ultra plus a vision model, all on Nebius Token Factory. Calls to his wife for invoices: from several a day to none. GarageDesk."

## Shots checklist
- [ ] Owner under a car / phone on the bench
- [ ] Hold-to-talk with the read-back audible
- [ ] Photo of a handwritten job card
- [ ] Approve page on a second phone
- [ ] Customer text with the invoice
- [ ] Paid EFTPOS tap
- [ ] Status update by voice
- [ ] Dashboard and daily report
- [ ] README architecture diagram

## After recording
1. Upload to YouTube as Public or Unlisted (Devpost accepts both), title "GarageDesk: a back office the mechanic never types into (Nebius x NVIDIA hackathon)".
2. Paste the YouTube link into docs/SUBMISSION.md "Links" and into the Devpost form.
3. Devpost form fields come straight from docs/SUBMISSION.md: tagline, category (Best Apps and Agents), description sections, "Built with", repo link, demo URL, video link, and the feedback text from docs/FEEDBACK.md.
4. Submit by Oct 28 to leave two days of buffer before the Oct 30, 10:00am PDT deadline.

# Demo video script (target 2:40, hard limit 3:00)

**Story:** one real moment. A car is finished, and today the owner would put down his calculator and ring his wife at her other job: "Corolla's done, front pads, hour and a half, 350 all up." She would make the tax invoice. In the video he says exactly the same words to his phone instead, and never touches a keyboard.

Every scene runs on the live demo at https://66-201-4-40.sslip.io. Every line below was run against live Nemotron on 2026-10-26 and gave the read-back shown.

## Setup (10 minutes, once)

- **Owner phone:** an iPhone with https://66-201-4-40.sslip.io/owner open (Chrome or Safari). Allow the microphone the first time. Ringer volume up so the read-back is heard. Record with the iPhone's screen recording (Control Centre, with the microphone on so his voice and the read-back are in the recording).
- **Wife's phone:** any second phone, or a laptop window at phone size. The approve link appears on the dashboard's **Outbox** page (it is a text once Twilio is on); open it from there.
- **Customer's phone:** the same Outbox page shows the customer's texts.
- **Before each take:** on a laptop open https://66-201-4-40.sslip.io/, press **Reset demo data** at the bottom of the sidebar, then press **Generate** on the Report page. Say the first line once as a warm-up, then reset again.
- **Pauses:** after he lets go, the reply comes back in 2-4 seconds. Keep the camera on the phone and talk over it; don't cut.
- **No faces or real number plates** are needed. A calculator on the bench helps the first shot.

## Shooting list

| # | Time | Shot | Say into the phone (hold the button, let go) | You hear back | Voice-over |
|---|---|---|---|---|---|
| 1 | 0:00-0:20 | Hands on a calculator, then a phone showing "Calling: Wife" | | | "This is a real workshop in Sunshine North, Melbourne. The owner is a great mechanic who doesn't use computers and doesn't type. When a car is done he works out the price on a calculator and rings his wife, who makes the tax invoice. But she works somewhere else now, and if she can't pick up, the customer waits. GarageDesk replaces that phone call." |
| 2 | 0:20-0:55 | Owner app screen recording | "Corolla ABC123, front pads, hour and a half, 350 all up." | "Maria's Corolla. Front brake pads and an hour and a half labour. Three hundred and fifty dollars all up. Send it to Jenny?" | "Same words, same numbers, said to his phone. Nemotron Nano works out what he wants, Nemotron Super turns it into invoice lines, and his 350 is the charge: the pads come from the shop's price list and the rest goes on labour. The AI never makes up a price." |
| 3 | 0:55-1:02 | Same screen | "Yep." | "Sent to Jenny." | "He says yep, and it's on its way to his wife." |
| 4 | 1:02-1:17 | Same screen | "Find yesterday's jobs and prepare the tax invoice." | "Dan's X-Trail. Rear brake pads and an hour labour. Two hundred and forty dollars ninety all up. Send it to Jenny?" | "No dates, no job numbers. Yesterday, a rego, a name or the car: it finds the job." |
| 5 | 1:17-1:30 | Same screen | "Liam's Ranger, did the battery again, same as last time." | "Liam's Ranger. Battery and half an hour labour. Three hundred and sixty-six dollars all up. Send it to Jenny?" | "It remembers every car that's been in. Same as last time means last time's real figures." |
| 6 | 1:30-1:50 | Wife's phone: open the approve link from Outbox, show the GST lines, tap **Approve and send** | | | "His wife gets a text, checks the invoice on her break, and taps once. If something's wrong she taps Fix and it goes back to him. A five-minute call for two people becomes a three-second tap for one." |
| 7 | 1:50-2:05 | Outbox: "Hi Maria, your Toyota Corolla is ready to collect…" and open the invoice PDF. Back on the owner app, the phone says Jenny approved; he says "yes" when paid | "Yes." | The receipt text appears in Outbox | "Maria knows her car is ready before she walks in and gets a proper Australian tax invoice. When she pays on EFTPOS he says yes, and the receipt goes out." |
| 8 | 2:05-2:25 | Owner app, three quick lines | "Order front pads for the Kia Cerato." then "Yes." | "Front brake pads from …, … plus GST. Send the order?" then "Order sent." | "Parts too: it finds the part and a price, live with Tavily, reads the order back, and yes sends it." |
| 9 | | | "What have I got on today?" | "5 cars today: 8am Maria's Corolla…" | "And it runs his day: the diary, the money, the GST." |
| 10 | 2:25-2:40 | Owner under a car. Overlay: "Admin calls to his wife: several a day → none." Then GarageDesk and the repo URL | | | "No keyboard and no new habits. Nemotron Nano, Super and Ultra on Nebius Token Factory, with NVIDIA Parakeet hearing his accent on a Nebius VM. Open source under MIT. GarageDesk: he fixes cars, it does the paperwork." |

If a take runs long, drop shot 9 first, then shot 5.

**Optional extras** if there's time left (each about 5 seconds): "The CX-5 is waiting on parts till Thursday" and the customer's text in Outbox; "Remember Jack always pays cash", then "How does Jack usually pay?"; tap **Add parts from a receipt photo** on a draft and photograph a supplier receipt; the Nemotron 3 Ultra report on the dashboard's Report page.

**If a word comes out wrong** on screen, just say the line again; the new version replaces the old one. "Make it 380 all up" changes only the total.

## After recording
1. Trim to under 3:00 and upload to YouTube as **Public** (Unlisted also works), title "GarageDesk: replace the phone call to his wife (Nebius x NVIDIA hackathon)".
2. Paste the YouTube link into the Devpost "Video demo link" field.
3. Everything else for the form is in [SUBMISSION.md](SUBMISSION.md).
4. Submit by Oct 28, two days before the Oct 30, 10:00am PDT deadline.

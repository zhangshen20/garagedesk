# Job card photo to job draft

> **Optional.** The real owner turned out not to use paper job cards, so the owner app no
> longer links to this; his flow is voice plus "Add parts from a receipt photo". The
> endpoints below stay for shops that do write job cards, and for the dashboard.

A shop that writes job cards on paper can photograph a card and GarageDesk turns it into
a job draft that is ready to invoice. Each field
comes with a confidence score, so the app only reads back the parts it isn't sure about.

## Pipeline

1. **Prepare the photo.** Pillow turns it upright using the EXIF rotation, shrinks it to
   at most 1600 px and saves it as JPEG. A copy is kept so the job keeps its card.
2. **Read it twice.** Two vision models on Nebius Token Factory copy the handwriting
   in parallel, exactly as written: `openbmb/MiniCPM-V-4_5` (about 2 s) and
   `Qwen/Qwen3.8-27B` (about 4 s). When they agree, that is the main sign of a good
   reading. When they disagree, the owner gets asked. If one model fails, the other
   still produces a draft. To change the models, set `JOBCARD_VISION_MODELS`.
3. **Tidy with Nemotron.** NVIDIA Nemotron 3 Super (`nvidia/nemotron-3-super-120b-a12b`)
   gets the transcription, never the pixels, because Token Factory has no Nemotron
   vision model. It picks the more plausible reading where the two models disagree. It
   rewrites shorthand as invoice wording ("F + R pads" becomes "Replace front and rear
   brake pads"), converts units ("1 1/2" becomes 1.5 h) and matches parts to the
   catalogue.
4. **Check against the rules and the shop's records.** Code checks the AU phone format,
   the rego shape and that the hours are sensible. It also checks the card against the
   shop's own records: a rego already on file, a phone number that has changed, a rego
   registered to someone else, or a part catalogued for a different car. A Nemotron
   answer that fails the same checks is dropped.
5. **Build the read-back.** Any field under 0.75 confidence becomes a plain-English
   sentence the app can say aloud, for example "Phone: 0412 345 678. New number? On file
   it's 0411 000 001."

6. **Hand it to the owner app.** `JobDraft.to_extract()` gives the same dict that
   Talk-to-Invoice produces, so `apply_to_job` and `readback` from `agent/jobcard.py`
   price the parts and labour and build the reply exactly as they do for a spoken job. The
   job is found by rego only. Loose word matching would put a new customer's Ranger on
   another customer's Ranger job. Doubts about the customer, rego, car, labour or work
   become `warnings`, so the app holds Send until they're fixed. A changed phone number is
   read out but does not hold anything. A part the reader found doesn't fit this car (for
   example Ranger pads when we only stock Corolla pads) is left unpriced, not billed as the
   wrong part.

The schema is in `backend/app/vision/schema.py`.

## API

| Route | What it does |
|---|---|
| `POST /api/jobcards/scan` | `{image_b64, mime}`, same as `/api/owner/photo` -> the same draft response plus `jobcard` (per-field confidence) |
| `POST /api/jobcards/samples/{name}/scan` | the same, for a bundled sample card (demo without a phone) |
| `GET /api/jobcards/samples` | names of the sample cards; `GET /api/jobcards/samples/{name}.jpg` serves one |
| `GET /api/jobcards/photos/{photo_id}.jpg` | the stored photo; its link is also added to the job's notes |

Without `NEBIUS_API_KEY` (mock mode), the sample cards are read from their ground truth
and simple rules do the tidying. Everything else runs the real code, so CI covers the
merging, confidence, record checks, read-back and the hand-off to the job.

## Live results (2026-10-12, Token Factory)

`python backend/scripts/jobcard_live_eval.py` with the four sample cards in
`backend/app/vision/samples/`. They were drawn by `backend/scripts/make_sample_jobcards.py`
and use a slanted font with per-letter jitter, so they imitate handwriting rather than
being real handwriting:

| Card | Time | Every field right | What the owner app says beyond the invoice |
|---|---|---|---|
| neat service (known customer) | 9.6 s | yes | "Phone: 0412 345 678. New number? On file it's 0411 000 001. Send it?" |
| messy brakes (blur, coffee ring) | 8.7 s | yes | walk-in opened for the new Ranger; no price for the Ranger pads or the DOT4 |
| partial battery (new customer) | 6.3 s | yes | "What's the customer's phone number?" |
| dim tyres (dark, shadow, 7° tilt) | 11.7 s | yes | held: "Rego XYZ789 is on file for Priya Patel, but the card says Sione Tupou." |

Next step: run real photos of the shop's own cards through
`jobcard_live_eval.py photo.jpg` and tune the prompt if needed.

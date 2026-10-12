# Link to the Sunshine North Mechanic booking site

The shop's website (Cloudflare Worker + D1, repo `zhangshen20/sunshine-auto-care`) is
where customers book. GarageDesk reads those bookings so the owner never types a
customer's name, phone, car or rego again, and so marking a booking **completed** on
the site starts the invoice.

GarageDesk only reads from the site. It never changes a booking there.

## What GarageDesk does with a booking

| Site event | GarageDesk |
| --- | --- |
| Booking appears (requested / confirmed) | Copied onto the GarageDesk board with customer and car, `source = "web"` |
| Car arrives (`checked_in`, or owner taps "start job") | Job card opened, prefilled from the booking: customer, phone, car, rego, booked service, notes, a suggested labour line |
| Marked `completed` | Job set to done with the booking's details and suggested lines, then sent for invoice approval (`services.request_invoice_approval`), so his wife gets the one-tap approval text. Nothing reaches the customer until she approves. A job with no lines worth invoicing stays at done for the owner to say |
| Declined / cancelled | Local copy cancelled |

Every operation is idempotent: a webhook arriving after a poll, or the same webhook
twice, never creates a second job. Customers are matched by phone; a rego alone
only matches when the name agrees, because cars change hands.

## GarageDesk API (`/api/site-bookings`)

| Route | What it does |
| --- | --- |
| `GET /api/site-bookings?day=today&days=7` | Today's and upcoming site bookings, each with a `draft` (job draft) and `garagedesk` (local booking and job ids, once linked) |
| `POST /api/site-bookings/sync?day=today&days=7` | Mirror bookings onto the board; completed ones start an invoice draft (works with no webhook) |
| `GET /api/site-bookings/{reference}/draft` | The job draft for one booking |
| `POST /api/site-bookings/{reference}/start-job` | Open the prefilled job card |
| `POST /api/site-bookings/webhook` | Signed webhook from the site (below) |
| `POST /api/site-bookings/{reference}/demo-complete` | Mock source only: mark a demo booking completed and run the webhook handler |

Job draft shape:

```json
{
  "source": "booking_site",
  "source_ref": "SNM-7K2Q",
  "customer": {"name": "Priya Nair", "phone": "0412 555 104", "email": "priya.nair@example.com"},
  "vehicle": {"rego": "1XY2ZA", "year": 2017, "make": "Mazda", "model": "CX-5", "description": "2017 Mazda CX-5"},
  "title": "Logbook service",
  "notes": "Due for 60,000 km service. Squeak from rear left when braking.",
  "lines": [{"kind": "labour", "description": "Logbook service labour", "qty": 1.5, "unit_cents": 12000, "suggested": true}],
  "missing": [],
  "booked_for": {"day": "2026-10-12", "start": "08:00", "leave_all_day": true}
}
```

`missing` lists what the owner still has to say: `rego` when the customer left it
blank, `work_done` when the booked service has no typical labour line.

## Configuration (GarageDesk)

| Variable | Meaning |
| --- | --- |
| `SITE_BOOKINGS_URL` | Site base URL, e.g. `https://www.sunshinenthmechanic.com.au`. Unset means the mock source |
| `SITE_BOOKINGS_TOKEN` | Bearer token for the read endpoint |
| `SITE_WEBHOOK_SECRET` | Shared secret for webhook signatures. Unset means the webhook answers 503 |
| `SITE_BOOKINGS_MODE` | `auto` (default), `http` or `mock` |

Without `SITE_BOOKINGS_URL`, GarageDesk uses a built-in week of believable Sunshine
North bookings, so tests and the demo run with no network.

## What the website needs to expose

The site already has every field GarageDesk needs (`WorkshopBooking` in
`src/lib/booking-contract.ts`). Its existing `/admin/api/dashboard` returns them, but it
sits behind Cloudflare Access with a Google-login email allowlist, which a server
cannot pass. Two small additions to `src/lib/booking-api.ts` give GarageDesk a
machine route. Both reuse code that is already there (`mapBooking`, `DATE_PATTERN`,
`addDays`, `secretsMatch`).

### 1. Read endpoint (required)

`GET /integrations/garagedesk/bookings?from=YYYY-MM-DD&to=YYYY-MM-DD`, authorised by
`Authorization: Bearer <GARAGEDESK_API_TOKEN>`, returning `{"bookings": WorkshopBooking[]}`.
The path must stay outside `/admin*` so Cloudflare Access does not intercept it.

```ts
// BookingEnvironment: add
//   GARAGEDESK_API_TOKEN?: string;
//   GARAGEDESK_WEBHOOK_URL?: string;
//   GARAGEDESK_WEBHOOK_SECRET?: string;

async function garageDeskBookings(request: Request, env: BookingEnvironment): Promise<Response> {
  const token = env.GARAGEDESK_API_TOKEN;
  const given = (request.headers.get("authorization") ?? "").replace(/^Bearer\s+/i, "");
  if (!token || !given || !(await secretsMatch(given, token))) {
    return json({ error: "Unauthorised." }, 401);
  }
  const db = database(env);
  if (db instanceof Response) return db;
  const url = new URL(request.url);
  const from = url.searchParams.get("from") ?? todayInMelbourne();
  const to = url.searchParams.get("to") ?? from;
  if (!DATE_PATTERN.test(from) || !DATE_PATTERN.test(to) || to < from || to > addDays(from, 90)) {
    return json({ error: "Invalid date range." }, 400);
  }
  const result = await db
    .prepare(
      `SELECT b.*, s.slot_date, s.start_time
       FROM bookings b JOIN booking_slots s ON s.id = b.slot_id
       WHERE s.slot_date BETWEEN ? AND ?
       ORDER BY s.slot_date, s.start_time, b.created_at`,
    )
    .bind(from, to)
    .all<BookingRow>();
  return json({ bookings: (result.results ?? []).map(mapBooking) });
}

// in handleBookingApi, before the /admin/api/ checks:
if (path === "/integrations/garagedesk/bookings" && request.method === "GET") {
  return garageDeskBookings(request, env);
}
```

`manage_token_hash` is not part of `WorkshopBooking`, so the customer's private
management link never leaves the site.

With only this endpoint, GarageDesk sees completed bookings on its next sync
(`POST /api/site-bookings/sync`, run when the owner opens the app).

### 2. Webhook on status change (optional, makes "completed" instant)

At the end of `updateBookingByAdmin`, after the status update and event insert succeed,
send the updated booking to GarageDesk. It must not block or fail the admin's change.

```ts
async function notifyGarageDesk(env: BookingEnvironment, booking: WorkshopBooking): Promise<void> {
  if (!env.GARAGEDESK_WEBHOOK_URL || !env.GARAGEDESK_WEBHOOK_SECRET) return;
  const body = JSON.stringify({ event: "booking.updated", booking });
  const timestamp = String(Math.floor(Date.now() / 1000));
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(env.GARAGEDESK_WEBHOOK_SECRET),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  const mac = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(`${timestamp}.${body}`));
  const signature = [...new Uint8Array(mac)].map((b) => b.toString(16).padStart(2, "0")).join("");
  try {
    await fetch(env.GARAGEDESK_WEBHOOK_URL, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-garagedesk-timestamp": timestamp,
        "x-garagedesk-signature": `sha256=${signature}`,
      },
      body,
    });
  } catch (error) {
    console.error("GarageDesk webhook failed", error);
  }
}

// in updateBookingByAdmin, after the event insert:
const updated = await db
  .prepare(`SELECT b.*, s.slot_date, s.start_time FROM bookings b
            JOIN booking_slots s ON s.id = b.slot_id WHERE b.id = ?`)
  .bind(bookingId)
  .first<BookingRow>();
if (updated) ctx.waitUntil(notifyGarageDesk(env, mapBooking(updated)));
```

`handleBookingApi` does not receive the Worker `ctx` today; pass it through from
`src/server.ts`, or `await notifyGarageDesk(...)` directly (it swallows its own errors).

GarageDesk checks the signature (HMAC-SHA256 of `"{timestamp}.{raw body}"`) and refuses
requests older than five minutes.

### Secrets to set

On the site (`wrangler secret put`): `GARAGEDESK_API_TOKEN`, and for the webhook
`GARAGEDESK_WEBHOOK_URL` (`https://<garagedesk host>/api/site-bookings/webhook`) and
`GARAGEDESK_WEBHOOK_SECRET`. On GarageDesk: `SITE_BOOKINGS_URL`, `SITE_BOOKINGS_TOKEN`
(same value as `GARAGEDESK_API_TOKEN`) and `SITE_WEBHOOK_SECRET` (same value as
`GARAGEDESK_WEBHOOK_SECRET`). Generate each with `openssl rand -hex 32`.

### Alternative: shared database read

D1 can also be queried over the Cloudflare REST API
(`POST /accounts/{account}/d1/database/{db}/query`) with an API token scoped to D1 read.
It needs no site code change but gives GarageDesk a Cloudflare account token and
couples it to the table layout, so the endpoint above is the recommended route.

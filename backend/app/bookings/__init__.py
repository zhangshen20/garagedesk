"""Read-only link to the shop's own website booking system (the demo shop, Sunshine North Mechanic).

The website (Cloudflare Worker + D1) is the
source of truth for customer bookings. GarageDesk only reads from it:

* ``source``  pulls bookings from the site (or a mock for tests and the demo)
* ``drafts``  turns a site booking into a job draft, so nobody types the
  customer, phone, car or rego again
* ``link``    keeps local copies in step and starts an invoice draft when the
  site marks a booking "completed" (by webhook or by polling)
* ``router``  the HTTP API under /api/site-bookings

See docs/BOOKING_SITE_LINK.md for what the site needs to expose.
"""

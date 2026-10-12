"""Demo data for Sunshine Auto Care: a believable week in a three-bay workshop."""

from __future__ import annotations

from datetime import datetime, time, timedelta

from sqlmodel import Session, select

from . import services as svc
from .models import (
    Booking,
    BookingStatus,
    Customer,
    Expense,
    Job,
    JobLine,
    JobStatus,
    LineKind,
    Part,
    Supplier,
    Vehicle,
)
from .seed_history import seed_history


def seed_if_empty(s: Session) -> bool:
    if s.exec(select(Customer)).first():
        return False
    seed(s)
    s.commit()
    return True


def seed(s: Session) -> None:
    today = svc.today()

    burson = Supplier(name="Burson Auto Parts", contact_name="Dave", email="orders@burson.example", phone="+61390000001", order_channel="email")
    repco = Supplier(name="Repco Trade", contact_name="Priya", email="trade@repco.example", phone="+61390000002", order_channel="email")
    tyrepower = Supplier(name="Sunshine Tyre Wholesale", contact_name="Tony", phone="+61400000003", order_channel="sms")
    s.add_all([burson, repco, tyrepower])
    s.flush()

    parts = [
        Part(sku="BP-COR-F", name="Brake pads front - Toyota Corolla", supplier_id=burson.id, cost_cents=6900, sell_cents=11900, stock_qty=1, reorder_level=2),
        Part(sku="BP-COR-F-R", name="Brake pads front - Toyota Corolla", supplier_id=repco.id, cost_cents=7400, sell_cents=11900, stock_qty=0, reorder_level=0),
        Part(sku="OF-TOY", name="Oil filter - Toyota", supplier_id=burson.id, cost_cents=1200, sell_cents=2500, stock_qty=6, reorder_level=4),
        Part(sku="OIL-5W30", name="Engine oil 5W-30 (5L)", supplier_id=repco.id, cost_cents=3900, sell_cents=7500, stock_qty=3, reorder_level=4),
        Part(sku="BAT-DIN55", name="Battery DIN55 (Century)", supplier_id=repco.id, cost_cents=14500, sell_cents=22900, stock_qty=2, reorder_level=1),
        Part(sku="TY-205-55-16", name="Tyre 205/55R16 (mid-range)", supplier_id=tyrepower.id, cost_cents=9800, sell_cents=16500, stock_qty=4, reorder_level=4),
        Part(sku="WB-CX5", name="Wiper blades - Mazda CX-5 pair", supplier_id=burson.id, cost_cents=2200, sell_cents=4500, stock_qty=2, reorder_level=1),
        Part(sku="CAB-FILT", name="Cabin filter - universal", supplier_id=burson.id, cost_cents=1500, sell_cents=3500, stock_qty=5, reorder_level=2),
    ]
    s.add_all(parts)

    people = [
        ("Maria Nguyen", "+61411000001", "maria.n@example.com", "ABC123", "Toyota", "Corolla", 2016, 98000),
        ("Jack Thompson", "+61411000002", None, "1KR9ZZ", "Mazda", "CX-5", 2019, 61000),
        ("Priya Patel", "+61411000003", "priya@example.com", "XYZ789", "Hyundai", "i30", 2014, 143000),
        ("Liam O'Connor", "+61411000004", None, "LOC777", "Ford", "Ranger", 2018, 120500),
        ("Sofia Rossi", "+61411000005", "sofia.r@example.com", "SR2020", "Kia", "Cerato", 2020, 44000),
        ("Ahmed Hassan", "+61411000006", None, "AH5566", "Honda", "Civic", 2012, 188000),
        ("Grace Chen", "+61411000007", "grace.c@example.com", "GC8899", "Subaru", "Forester", 2017, 90000),
        ("Tom Baker", "+61411000008", None, "TB1234", "Holden", "Commodore", 2013, 165000),
        ("Dan Walker", "+61411000009", None, "DW4521", "Nissan", "X-Trail", 2015, 132000),
    ]
    customers: dict[str, Customer] = {}
    vehicles: dict[str, Vehicle] = {}
    for name, phone, email, rego, make, model, year, km in people:
        c = Customer(name=name, phone=phone, email=email)
        s.add(c)
        s.flush()
        v = Vehicle(customer_id=c.id, rego=rego, make=make, model=model, year=year, odometer_km=km)
        s.add(v)
        s.flush()
        customers[rego], vehicles[rego] = c, v

    def ago(days: int) -> datetime:
        """Mid-afternoon, shop time, `days` ago, stored as naive UTC like every timestamp."""
        lo, _ = svc.utc_bounds(today - timedelta(days=days), today - timedelta(days=days))
        return lo + timedelta(hours=15)

    def book(rego: str, day_offset: int, hhmm: str, service: str, status: BookingStatus = BookingStatus.confirmed, source: str = "phone") -> Booking:
        c, v = customers[rego], vehicles[rego]
        d = today + timedelta(days=day_offset)
        t = time(*map(int, hhmm.split(":")))
        b = svc.create_booking(s, customer=c, vehicle=v, day=d, start=t, service=service, source=source)
        b.status = status
        return b

    # Yesterday: finished and paid / finished and invoiced
    b1 = book("XYZ789", -1, "08:00", "Logbook service", BookingStatus.completed)
    j1 = Job(booking_id=b1.id, customer_id=customers["XYZ789"].id, vehicle_id=vehicles["XYZ789"].id, title="Logbook service", status=JobStatus.done, mechanic_notes="Rear pads 40%, mention next time.", created_at=ago(1), updated_at=ago(1))
    s.add(j1)
    s.flush()
    s.add_all([
        JobLine(job_id=j1.id, kind=LineKind.labour, description="Logbook service labour", qty=1.5, unit_cents=12000),
        JobLine(job_id=j1.id, kind=LineKind.part, description="Engine oil 5W-30 (5L)", qty=1, unit_cents=7500),
        JobLine(job_id=j1.id, kind=LineKind.part, description="Oil filter - Toyota", qty=1, unit_cents=2500),
        JobLine(job_id=j1.id, kind=LineKind.fee, description="Workshop consumables", qty=1, unit_cents=1500),
    ])
    s.flush()
    inv1 = svc.issue_invoice(s, j1)
    inv1.issued_at = ago(1)
    pay1 = svc.record_payment(s, inv1, inv1.total_cents, "eftpos", "EFT-7781")
    pay1.paid_at = ago(1)

    b2 = book("TB1234", -3, "09:00", "Brake pads and rotors", BookingStatus.completed)
    j2 = Job(booking_id=b2.id, customer_id=customers["TB1234"].id, vehicle_id=vehicles["TB1234"].id, title="Brake pads and rotors", status=JobStatus.done, created_at=ago(3), updated_at=ago(3))
    s.add(j2)
    s.flush()
    s.add_all([
        JobLine(job_id=j2.id, kind=LineKind.labour, description="Brake labour", qty=2, unit_cents=12000),
        JobLine(job_id=j2.id, kind=LineKind.part, description="Front pads and rotors - Commodore", qty=1, unit_cents=38000),
    ])
    s.flush()
    inv2 = svc.issue_invoice(s, j2)
    inv2.issued_at = ago(3)
    inv2.due_at = today - timedelta(days=1)  # overdue, for the report to chase

    # Yesterday: finished but nobody has done the invoice yet ("do yesterday's invoice")
    b5 = book("DW4521", -1, "10:00", "Rear brakes squealing", BookingStatus.completed)
    j5 = Job(booking_id=b5.id, customer_id=customers["DW4521"].id, vehicle_id=vehicles["DW4521"].id, title="Rear brake pads - X-Trail", status=JobStatus.done, mechanic_notes="Rear pads replaced, rotors within spec.", created_at=ago(1), updated_at=ago(1))
    s.add(j5)
    s.flush()
    s.add_all([
        JobLine(job_id=j5.id, kind=LineKind.labour, description="Replace rear brake pads", qty=1, unit_cents=12000),
        JobLine(job_id=j5.id, kind=LineKind.part, description="Brake pads rear - Nissan X-Trail", qty=1, unit_cents=9900),
    ])

    # Today's board
    b3 = book("ABC123", 0, "08:00", "Front brakes grinding", BookingStatus.checked_in)
    j3 = Job(booking_id=b3.id, customer_id=customers["ABC123"].id, vehicle_id=vehicles["ABC123"].id, title="Front brake pads - Corolla", status=JobStatus.in_progress, mechanic_notes="Pads metal on metal. Rotors OK to machine.")
    s.add(j3)
    s.flush()
    s.add_all([
        JobLine(job_id=j3.id, kind=LineKind.labour, description="Replace front pads, machine rotors", qty=1.5, unit_cents=12000),
        JobLine(job_id=j3.id, kind=LineKind.part, description="Brake pads front - Toyota Corolla", qty=1, unit_cents=11900),
    ])
    b4 = book("1KR9ZZ", 0, "09:00", "Roadworthy inspection", BookingStatus.checked_in)
    j4 = Job(booking_id=b4.id, customer_id=customers["1KR9ZZ"].id, vehicle_id=vehicles["1KR9ZZ"].id, title="Roadworthy inspection - CX-5", status=JobStatus.in_progress)
    s.add(j4)
    s.flush()
    s.add(JobLine(job_id=j4.id, kind=LineKind.labour, description="RWC inspection", qty=1, unit_cents=18000))
    book("LOC777", 0, "10:00", "Battery flat, won't start", BookingStatus.confirmed)
    book("SR2020", 0, "13:00", "Logbook service", BookingStatus.confirmed, source="web")
    book("AH5566", 0, "14:00", "Check engine light", BookingStatus.confirmed, source="sms")

    # Tomorrow and later
    book("GC8899", 1, "08:00", "Logbook service + tyres", BookingStatus.confirmed, source="web")
    book("TB1234", 2, "09:00", "Follow-up brake check", BookingStatus.confirmed)

    # Expenses
    s.add_all([
        Expense(day=today, description="Workshop rent (weekly)", amount_cents=85000, gst_cents=7727, category="rent"),
        Expense(day=today, description="Brake cleaner and rags", amount_cents=6400, gst_cents=582, category="consumables", supplier_id=burson.id),
        Expense(day=today - timedelta(days=1), description="Fuel - parts run", amount_cents=4800, gst_cents=436, category="vehicle"),
    ])
    s.flush()
    seed_history(s)  # the regulars' past visits, for the agent's memory (added last so ids above stay put)
    svc.log_event(s, "system", "seeded", "Demo data for Sunshine Auto Care")

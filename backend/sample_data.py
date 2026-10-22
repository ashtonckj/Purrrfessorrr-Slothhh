"""A deterministic sample CSV (cafe sales) with realistic mess baked in:
missing values, duplicate rows, outliers and a few badly typed cells.
No personal data: just orders.
"""

from __future__ import annotations

import csv
import io
import random
from datetime import date, timedelta
from functools import lru_cache

ROWS = 12_000

MENU = {
    "coffee": [("espresso", 2.8), ("latte", 4.2), ("cappuccino", 4.0), ("cold brew", 4.5)],
    "tea": [("matcha latte", 4.8), ("chai", 3.9), ("green tea", 3.0)],
    "pastry": [("croissant", 3.2), ("cinnamon roll", 3.8), ("banana bread", 3.5)],
    "food": [("toastie", 6.5), ("salad bowl", 8.9), ("soup", 5.9)],
}
STORES = ["Riverside", "Old Town", "Campus", "Harbour", "Station"]
PAYMENTS = ["card", "cash", "mobile"]


@lru_cache(maxsize=1)
def sample_csv() -> bytes:
    rng = random.Random(42)
    start = date(2025, 1, 1)
    rows = []
    for i in range(ROWS):
        category = rng.choices(list(MENU), weights=[5, 2, 3, 2])[0]
        item, price = rng.choice(MENU[category])
        qty = rng.choices([1, 2, 3, 4], weights=[60, 25, 10, 5])[0]
        day = start + timedelta(days=int(rng.triangular(0, 364, 300)))
        age = int(rng.gauss(32, 10))
        rating = rng.choices([1, 2, 3, 4, 5], weights=[2, 4, 12, 40, 42])[0]
        row = {
            "order_id": 100_000 + i,
            "date": day.isoformat(),
            "store": rng.choice(STORES),
            "category": category,
            "item": item,
            "quantity": qty,
            "unit_price": f"{price:.2f}",
            "total": f"{price * qty:.2f}",
            "customer_age": max(16, age),
            "rating": rating,
            "payment": rng.choice(PAYMENTS),
            "loyalty_member": rng.choice(["yes", "no", "no"]),
        }
        # --- the mess ---
        if rng.random() < 0.04:
            row["customer_age"] = ""
        if rng.random() < 0.07:
            row["rating"] = ""
        if rng.random() < 0.01:
            row["payment"] = ""
        if rng.random() < 0.003:
            row["quantity"] = rng.choice([99, 120, 250])  # fat-finger outliers
            row["total"] = f"{price * row['quantity']:.2f}"
        if rng.random() < 0.004:
            row["unit_price"] = rng.choice(["N/A", f"${price:.2f}", "?"])
        if rng.random() < 0.003:
            row["date"] = day.strftime("%d/%m/%Y")  # mixed date format
        if rng.random() < 0.01:
            row["store"] = row["store"].upper() + " "  # inconsistent casing
        rows.append(row)
        if rng.random() < 0.006:
            rows.append(dict(row))  # duplicate

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")

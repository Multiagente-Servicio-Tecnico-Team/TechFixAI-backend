"""Proyecciones puras para diario, mayor y balance de comprobación."""
from collections import defaultdict
from datetime import date
from decimal import Decimal


def _money(value):
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def build_report(report_type, rows, *, from_date, to_date, limit=50, offset=0):
    rows = sorted(rows, key=lambda r: (r["operation_date"], r["entry_number"], r["line_number"]))
    if report_type == "journal":
        items = [{**r, "operation_date": r["operation_date"].isoformat(),
                  "debit": f'{_money(r["debit"]):.2f}', "credit": f'{_money(r["credit"]):.2f}',
                  "legacy_unlinked": r["account_id"] is None} for r in rows]
        return {"report": report_type, "from_date": from_date.isoformat(), "to_date": to_date.isoformat(),
                "items": items[offset:offset + limit], "total": len(items),
                "totals": {"debit": f'{sum((_money(r["debit"]) for r in rows), Decimal("0.00")):.2f}',
                           "credit": f'{sum((_money(r["credit"]) for r in rows), Decimal("0.00")):.2f}'},
                "limit": limit, "offset": offset}
    if report_type == "ledger":
        raise ValueError("El mayor requiere que persistencia seleccione una cuenta.")
    grouped = defaultdict(lambda: {"_opening_debit": Decimal("0.00"), "_opening_credit": Decimal("0.00"),
                                   "opening_debit": Decimal("0.00"), "opening_credit": Decimal("0.00"),
                                   "debit": Decimal("0.00"), "credit": Decimal("0.00"),
                                   "normal_balance": None, "account_id": None,
                                   "account_code": "", "account_name": "", "legacy_unlinked": False})
    for row in rows:
        key = (row["account_id"], row["account_code"], row["account_name"])
        bucket = grouped[key]
        bucket.update({"account_id": row["account_id"], "account_code": row["account_code"],
                       "account_name": row["account_name"], "normal_balance": row["normal_balance"],
                       "legacy_unlinked": row["account_id"] is None})
        if row["operation_date"] < from_date:
            bucket["_opening_debit"] += _money(row["debit"])
            bucket["_opening_credit"] += _money(row["credit"])
        else:
            bucket["debit"] += _money(row["debit"])
            bucket["credit"] += _money(row["credit"])
    items = []
    for row in grouped.values():
        opening_signed = row["_opening_debit"] - row["_opening_credit"]
        row["opening_debit"] = max(opening_signed, Decimal("0.00"))
        row["opening_credit"] = max(-opening_signed, Decimal("0.00"))
        signed = opening_signed + row["debit"] - row["credit"]
        row["closing_signed"] = signed
        row["closing_debit"] = max(signed, Decimal("0.00"))
        row["closing_credit"] = max(-signed, Decimal("0.00"))
        for key in ("debit", "credit", "closing_signed", "closing_debit", "closing_credit",
                    "opening_debit", "opening_credit"):
            row[key] = f'{row[key]:.2f}'
        del row["_opening_debit"]
        del row["_opening_credit"]
        items.append(row)
    items.sort(key=lambda r: (r["account_code"], r["account_name"]))
    totals = {key: f'{sum((Decimal(row[key]) for row in items), Decimal("0.00")):.2f}'
              for key in ("opening_debit", "opening_credit", "debit", "credit", "closing_debit", "closing_credit")}
    return {"report": "trial_balance", "from_date": from_date.isoformat(), "to_date": to_date.isoformat(),
            "items": items[offset:offset + limit], "total": len(items), "totals": totals,
            "limit": limit, "offset": offset}


def build_ledger(rows, *, from_date: date, to_date: date, limit=50, offset=0):
    rows = sorted(rows, key=lambda r: (r["operation_date"], r["entry_number"], r["line_number"]))
    nature = rows[0]["normal_balance"] if rows else None
    prior = [r for r in rows if r["operation_date"] < from_date]
    movements = [r for r in rows if from_date <= r["operation_date"] <= to_date]
    signed = lambda r: (_money(r["debit"]) - _money(r["credit"])) * (-1 if nature == "CREDIT" else 1)
    balance = sum((signed(r) for r in prior), Decimal("0.00"))
    opening = balance
    items = []
    for r in movements:
        balance += signed(r)
        items.append({**r, "operation_date": r["operation_date"].isoformat(),
                      "debit": f'{_money(r["debit"]):.2f}', "credit": f'{_money(r["credit"]):.2f}',
                      "running_balance": f"{balance:.2f}", "normal_balance_unknown": nature is None})
    return {"report": "ledger", "from_date": from_date.isoformat(), "to_date": to_date.isoformat(),
            "opening_balance": f"{opening:.2f}", "closing_balance": f"{balance:.2f}",
            "items": items[offset:offset + limit], "total": len(items),
            "totals": {"debit": f'{sum((_money(r["debit"]) for r in movements), Decimal("0.00")):.2f}',
                       "credit": f'{sum((_money(r["credit"]) for r in movements), Decimal("0.00")):.2f}'},
            "limit": limit, "offset": offset}

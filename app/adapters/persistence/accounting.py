"""Adaptador SQLAlchemy para los asientos internos de PostgreSQL."""
import logging
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.application.errors import (
    AccountingConflict,
    AccountingNotFound,
    AccountingStorageUnavailable,
)
from app.domain.accounting import ValidatedEntry

logger = logging.getLogger(__name__)


def money_string(value: Any) -> str:
    return format(Decimal(str(value or 0)).quantize(Decimal("0.01")), ".2f")


def _default_session_factory():
    from app.database.connection import SessionLocal, get_engine

    get_engine()
    return SessionLocal


class AccountingRepositoryAdapter:
    def __init__(self, session_factory=None):
        self._session_factory = session_factory or _default_session_factory()

    @staticmethod
    def _storage_error(exc: Exception):
        logger.error("Accounting persistence failed: %s", type(exc).__name__)
        return AccountingStorageUnavailable()

    @staticmethod
    def _summary_from_row(row) -> dict[str, object]:
        return {
            "id": int(row["id"]),
            "entry_number": str(row["entry_number"]),
            "operation_date": row["operation_date"].isoformat(),
            "concept": row["concept"],
            "category": {"id": int(row["category_id"]), "code": row["category_code"], "name": row["category_name"], "description": row["category_description"]},
            "currency": row["currency"].strip(),
            "debit_total": money_string(row["debit_total"]),
            "credit_total": money_string(row["credit_total"]),
            "amount": money_string(row["debit_total"]),
            "status": row["status"],
            "responsible": {"user_id": int(row["responsible_user_id"]), "display_name": row["responsible_name"].strip()},
            "created_at": row["created_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat(),
            "reversed_at": row["reversed_at"].isoformat() if row["reversed_at"] else None,
            "reversal_of_entry_id": int(row["reversal_of_entry_id"]) if row["reversal_of_entry_id"] else None,
            "reversal_entry_id": int(row["reversal_entry_id"]) if row["reversal_entry_id"] else None,
            "plan_id": int(row["accounting_plan_id"]) if row["accounting_plan_id"] else None,
            "accounting_plan": ({"id": int(row["accounting_plan_id"]), "code": row["plan_code"],
                                 "name": row["plan_name"], "edition": row["plan_edition"]}
                                if row["accounting_plan_id"] else None),
        }

    @staticmethod
    def _summary(session, entry_id: int) -> dict[str, object] | None:
        row = session.execute(
            text(
                """
                SELECT e.id, e.entry_number, e.operation_date, e.concept, e.category_id,
                       c.code AS category_code, c.name AS category_name,
                       c.description AS category_description, e.currency,
                       e.debit_total, e.credit_total, e.status, e.responsible_user_id,
                       trim(u.name || ' ' || coalesce(u.last_name, '')) AS responsible_name,
                       e.created_at, e.updated_at, e.reversed_at, e.reversal_of_entry_id,
                       e.accounting_plan_id, p.code AS plan_code, p.name AS plan_name, p.edition AS plan_edition,
                       (SELECT r.id FROM accounting_entries r
                        WHERE r.reversal_of_entry_id = e.id) AS reversal_entry_id
                FROM accounting_entries e
                JOIN accounting_categories c ON c.id = e.category_id
                JOIN users u ON u.id = e.responsible_user_id
                LEFT JOIN accounting_plans p ON p.id = e.accounting_plan_id
                WHERE e.id = :entry_id
                """
            ),
            {"entry_id": entry_id},
        ).mappings().first()
        if row is None:
            return None
        return AccountingRepositoryAdapter._summary_from_row(row)

    @classmethod
    def _detail(cls, session, entry_id: int) -> dict[str, object] | None:
        summary = cls._summary(session, entry_id)
        if summary is None:
            return None
        header = session.execute(
            text("SELECT detail FROM accounting_entries WHERE id = :id"), {"id": entry_id}
        ).mappings().one()
        lines = session.execute(
            text("""SELECT line_number, account_id, account_code, account_name, description, debit, credit
                      FROM accounting_entry_lines WHERE entry_id = :id ORDER BY line_number"""),
            {"id": entry_id},
        ).mappings().all()
        events = session.execute(
            text("""SELECT a.event_type, a.actor_user_id,
                             trim(u.name || ' ' || coalesce(u.last_name, '')) AS display_name,
                             a.related_entry_id, a.reason, a.created_at
                      FROM accounting_audit_events a JOIN users u ON u.id = a.actor_user_id
                      WHERE a.entry_id = :id ORDER BY a.created_at, a.id"""),
            {"id": entry_id},
        ).mappings().all()
        summary.update({
            "detail": header["detail"],
            "lines": [{"line_number": int(line["line_number"]),
                       "account_id": int(line["account_id"]) if line["account_id"] else None,
                       "legacy_unlinked": line["account_id"] is None,
                       "account_code": line["account_code"],
                       "account_name": line["account_name"], "description": line["description"],
                       "debit": money_string(line["debit"]), "credit": money_string(line["credit"])} for line in lines],
            "audit_events": [{"event_type": event["event_type"],
                              "actor": {"user_id": int(event["actor_user_id"]), "display_name": event["display_name"].strip()},
                              "related_entry_id": int(event["related_entry_id"]) if event["related_entry_id"] else None,
                              "reason": event["reason"], "created_at": event["created_at"].isoformat()} for event in events],
        })
        return summary

    def list_categories(self):
        try:
            with self._session_factory() as session:
                rows = session.execute(text("""SELECT id, code, name, description FROM accounting_categories
                                             WHERE active IS TRUE ORDER BY id""")).mappings().all()
            return [{"id": int(row["id"]), "code": row["code"], "name": row["name"], "description": row["description"]} for row in rows]
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    @staticmethod
    def _lock_open_period(session, operation_date: date) -> None:
        year, month = operation_date.year, operation_date.month
        session.execute(text("""INSERT INTO accounting_periods(year, month, status)
            VALUES (:year, :month, 'OPEN') ON CONFLICT (year, month) DO NOTHING"""),
            {"year": year, "month": month})
        row = session.execute(text("""SELECT status FROM accounting_periods
            WHERE year = :year AND month = :month FOR UPDATE"""),
            {"year": year, "month": month}).mappings().one()
        if row["status"] != "OPEN":
            raise AccountingConflict("El periodo contable está cerrado para nuevas operaciones.")

    @staticmethod
    def _resolve_accounts(session, plan_id: int, lines, operation_date: date):
        from app.domain.accounting import AccountingValidationError
        resolved = []
        for number, line in enumerate(lines, 1):
            if line.account_id is not None:
                row = session.execute(text("""SELECT id, code, name FROM accounting_accounts
                    WHERE id = :account_id AND plan_id = :plan_id AND status = 'ACTIVE' AND is_postable
                      AND (effective_from IS NULL OR effective_from <= :operation_date)
                      AND (effective_to IS NULL OR effective_to >= :operation_date) FOR SHARE"""),
                    {"account_id": line.account_id, "plan_id": plan_id,
                     "operation_date": operation_date}).mappings().first()
            else:
                row = session.execute(text("""SELECT id, code, name FROM accounting_accounts
                    WHERE code = :code AND plan_id = :plan_id AND status = 'ACTIVE' AND is_postable
                      AND (effective_from IS NULL OR effective_from <= :operation_date)
                      AND (effective_to IS NULL OR effective_to >= :operation_date) FOR SHARE"""),
                    {"code": line.account_code.strip(), "plan_id": plan_id,
                     "operation_date": operation_date}).mappings().first()
            if row is None:
                raise AccountingValidationError(f"La línea {number} debe usar una cuenta activa e imputable del plan seleccionado.")
            resolved.append((line, row))
        return resolved

    def create_entry(self, actor_id: int, idempotency_key: UUID, request_hash: str, draft: ValidatedEntry):
        try:
            with self._session_factory() as session, session.begin():
                previous = session.execute(
                    text("""SELECT id, request_hash FROM accounting_entries
                              WHERE responsible_user_id = :actor AND idempotency_key = :key"""),
                    {"actor": actor_id, "key": idempotency_key},
                ).mappings().first()
                if previous:
                    if previous["request_hash"] != request_hash:
                        raise AccountingConflict("La clave de idempotencia ya se usó con otros datos.")
                    entry_id = int(previous["id"])
                    replay = True
                else:
                    self._lock_open_period(session, draft.draft.operation_date)
                    plan_id = draft.draft.accounting_plan_id
                    if plan_id is None:
                        plan_id = session.execute(text("""SELECT id FROM accounting_plans
                            WHERE is_default AND status = 'ACTIVE' FOR SHARE""")).scalar_one_or_none()
                    if plan_id is None:
                        from app.domain.accounting import AccountingValidationError
                        raise AccountingValidationError("No hay un plan contable predeterminado activo.")
                    if session.execute(text("SELECT 1 FROM accounting_plans WHERE id = :id AND status = 'ACTIVE' FOR SHARE"),
                                       {"id": plan_id}).first() is None:
                        from app.domain.accounting import AccountingValidationError
                        raise AccountingValidationError("El plan contable no está activo.")
                    resolved_lines = self._resolve_accounts(session, int(plan_id), draft.draft.lines,
                                                            draft.draft.operation_date)
                    category = session.execute(
                        text("SELECT id FROM accounting_categories WHERE id = :id AND active IS TRUE FOR SHARE"),
                        {"id": draft.draft.category_id},
                    ).first()
                    if category is None:
                        from app.domain.accounting import AccountingValidationError
                        raise AccountingValidationError("La categoría no está disponible.")
                    entry_id = session.execute(
                        text("""INSERT INTO accounting_entries
                            (operation_date, concept, detail, category_id, currency, debit_total,
                             credit_total, status, responsible_user_id, idempotency_key, request_hash, accounting_plan_id)
                            VALUES (:operation_date, :concept, :detail, :category_id, 'PEN', :debit,
                                    :credit, 'CONFIRMED', :actor, :key, :hash, :plan) RETURNING id"""),
                        {"operation_date": draft.draft.operation_date, "concept": draft.draft.concept.strip(),
                         "detail": draft.draft.detail.strip(), "category_id": draft.draft.category_id,
                         "debit": draft.debit_total, "credit": draft.credit_total, "actor": actor_id,
                         "key": idempotency_key, "hash": request_hash, "plan": plan_id},
                    ).scalar_one()
                    for number, (line, account) in enumerate(resolved_lines, 1):
                        session.execute(text("""INSERT INTO accounting_entry_lines
                            (entry_id, line_number, account_id, account_code, account_name, description, debit, credit)
                            VALUES (:entry, :number, :account, :code, :name, :description, :debit, :credit)"""),
                            {"entry": entry_id, "number": number, "account": int(account["id"]),
                             "code": account["code"], "name": account["name"], "description": line.description,
                             "debit": line.debit, "credit": line.credit})
                    session.execute(text("""INSERT INTO accounting_audit_events
                        (entry_id, actor_user_id, event_type) VALUES (:entry, :actor, 'ENTRY_CREATED')"""),
                        {"entry": entry_id, "actor": actor_id})
                    replay = False
            if replay:
                with self._session_factory() as session:
                    entry = self._detail(session, entry_id)
                return entry, True
            entry = self.get_entry(entry_id)
            return entry, False
        except (AccountingConflict,):
            raise
        except IntegrityError as exc:
            # La restricción única resuelve carreras del mismo actor y clave.
            with self._session_factory() as session:
                row = session.execute(text("""SELECT id, request_hash FROM accounting_entries
                    WHERE responsible_user_id = :actor AND idempotency_key = :key"""),
                    {"actor": actor_id, "key": idempotency_key}).mappings().first()
                if row:
                    if row["request_hash"] != request_hash:
                        raise AccountingConflict("La clave de idempotencia ya se usó con otros datos.") from exc
                    return self._detail(session, int(row["id"])), True
            raise self._storage_error(exc) from exc
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def list_entries(self, *, from_date: date | None = None, to_date: date | None = None,
                     category_id: int | None = None, status: str | None = None,
                     entry_number: int | None = None, limit: int = 50, offset: int = 0):
        conditions = []
        params: dict[str, object] = {"limit": limit, "offset": offset}
        for key, value, sql_expression in (
            ("from_date", from_date, "e.operation_date >= :from_date"),
            ("to_date", to_date, "e.operation_date <= :to_date"),
            ("category_id", category_id, "e.category_id = :category_id"),
            ("status", status, "e.status = :status"),
            ("entry_number", entry_number, "e.entry_number = :entry_number"),
        ):
            if value is not None:
                conditions.append(sql_expression)
                params[key] = value
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        selection = """SELECT e.id, e.entry_number, e.operation_date, e.concept, e.category_id,
            c.code AS category_code, c.name AS category_name, c.description AS category_description,
            e.currency, e.debit_total, e.credit_total, e.status, e.responsible_user_id,
            trim(u.name || ' ' || coalesce(u.last_name, '')) AS responsible_name,
            e.created_at, e.updated_at, e.reversed_at, e.reversal_of_entry_id,
            e.accounting_plan_id, p.code AS plan_code, p.name AS plan_name, p.edition AS plan_edition,
            (SELECT r.id FROM accounting_entries r WHERE r.reversal_of_entry_id = e.id) AS reversal_entry_id
            FROM accounting_entries e JOIN accounting_categories c ON c.id = e.category_id
            LEFT JOIN accounting_plans p ON p.id = e.accounting_plan_id
            JOIN users u ON u.id = e.responsible_user_id""" + where + " ORDER BY e.operation_date DESC, e.entry_number DESC LIMIT :limit OFFSET :offset"
        count_query = "SELECT count(*) FROM accounting_entries e" + where
        try:
            with self._session_factory() as session:
                total = int(session.execute(text(count_query), params).scalar_one())
                rows = session.execute(text(selection), params).mappings().all()
                items = [self._summary_from_row(row) for row in rows]
            return {"items": items, "total": total, "limit": limit, "offset": offset}
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def get_entry(self, entry_id: int):
        try:
            with self._session_factory() as session:
                return self._detail(session, entry_id)
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def reverse_entry(self, actor_id: int, entry_id: int, operation_date: date, reason: str):
        try:
            with self._session_factory() as session, session.begin():
                original = session.execute(text("""SELECT * FROM accounting_entries
                    WHERE id = :id FOR UPDATE"""), {"id": entry_id}).mappings().first()
                if original is None:
                    raise AccountingNotFound()
                if original["status"] == "REVERSED":
                    reversal = session.execute(text("""SELECT id, operation_date, reversal_reason FROM accounting_entries
                        WHERE reversal_of_entry_id = :id"""), {"id": entry_id}).mappings().first()
                    if reversal and reversal["operation_date"] == operation_date and reversal["reversal_reason"] == reason:
                        reversal_id = int(reversal["id"])
                        replay = True
                    else:
                        raise AccountingConflict("El asiento ya fue revertido con otros datos.")
                else:
                    self._lock_open_period(session, operation_date)
                    original_lines = session.execute(text("""SELECT line_number, account_id, account_code, account_name,
                        description, debit, credit FROM accounting_entry_lines WHERE entry_id = :id ORDER BY line_number"""),
                        {"id": entry_id}).mappings().all()
                    reversal_id = session.execute(text("""INSERT INTO accounting_entries
                        (operation_date, concept, detail, category_id, currency, debit_total, credit_total,
                         status, responsible_user_id, reversal_of_entry_id, reversal_reason, accounting_plan_id)
                        VALUES (:operation_date, :concept, :detail, :category_id, :currency, :debit, :credit,
                                'CONFIRMED', :actor, :original, :reason, :plan) RETURNING id"""),
                        {"operation_date": operation_date, "concept": original["concept"], "detail": original["detail"],
                         "category_id": original["category_id"], "currency": original["currency"],
                         "debit": original["credit_total"], "credit": original["debit_total"],
                         "actor": actor_id, "original": entry_id, "reason": reason,
                         "plan": original["accounting_plan_id"]}).scalar_one()
                    for line in original_lines:
                        session.execute(text("""INSERT INTO accounting_entry_lines
                            (entry_id, line_number, account_id, account_code, account_name, description, debit, credit)
                            VALUES (:entry, :number, :account, :code, :name, :description, :debit, :credit)"""),
                            {"entry": reversal_id, "number": line["line_number"], "account": line["account_id"],
                             "code": line["account_code"],
                             "name": line["account_name"], "description": line["description"],
                             "debit": line["credit"], "credit": line["debit"]})
                    session.execute(text("UPDATE accounting_entries SET status = 'REVERSED', reversed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = :id"), {"id": entry_id})
                    session.execute(text("""INSERT INTO accounting_audit_events
                        (entry_id, actor_user_id, event_type, related_entry_id, reason)
                        VALUES (:entry, :actor, 'ENTRY_REVERSED', :related, :reason)"""),
                        {"entry": entry_id, "actor": actor_id, "related": reversal_id, "reason": reason})
                    session.execute(text("""INSERT INTO accounting_audit_events
                        (entry_id, actor_user_id, event_type, related_entry_id, reason)
                        VALUES (:entry, :actor, 'REVERSAL_CREATED', :related, :reason)"""),
                        {"entry": reversal_id, "actor": actor_id, "related": entry_id, "reason": reason})
                    replay = False
            with self._session_factory() as session:
                original_result = self._summary(session, entry_id)
                reversal_result = self._detail(session, int(reversal_id))
            return {"original": original_result, "reversal": reversal_result}, replay
        except (AccountingConflict, AccountingNotFound):
            raise
        except IntegrityError as exc:
            # Concurrent reversals serialize on the original row; resolve the winner safely.
            with self._session_factory() as session:
                row = session.execute(text("""SELECT id, operation_date, reversal_reason FROM accounting_entries
                    WHERE reversal_of_entry_id = :id"""), {"id": entry_id}).mappings().first()
                if row and row["operation_date"] == operation_date and row["reversal_reason"] == reason:
                    return {"original": self._summary(session, entry_id), "reversal": self._detail(session, int(row["id"]))}, True
                if row:
                    raise AccountingConflict("El asiento ya fue revertido.") from exc
            raise self._storage_error(exc) from exc
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def accounting_report(self, report_type, *, from_date, to_date, plan_id=None, status=None,
                          account_id=None, account_code=None, account_name=None, limit=50, offset=0):
        from app.domain.accounting_reports import build_ledger, build_report
        if from_date > to_date:
            from app.domain.accounting import AccountingValidationError
            raise AccountingValidationError("El rango de fechas no es válido.")
        if report_type == "ledger" and not (account_id or (account_code and account_name)):
            from app.domain.accounting import AccountingValidationError
            raise AccountingValidationError("Indica account_id o el código y nombre histórico de la cuenta.")
        conditions = ["e.operation_date <= :to_date"]
        params = {"to_date": to_date}
        if report_type == "journal":
            conditions.append("e.operation_date >= :from_date")
            params["from_date"] = from_date
        if plan_id is not None:
            conditions.append("e.accounting_plan_id = :plan_id")
            params["plan_id"] = plan_id
        if status is not None:
            conditions.append("e.status = :status")
            params["status"] = status
        if account_id is not None:
            conditions.append("l.account_id = :account_id")
            params["account_id"] = account_id
        elif account_code is not None:
            conditions.append("l.account_id IS NULL AND l.account_code = :account_code AND l.account_name = :account_name")
            params.update({"account_code": account_code, "account_name": account_name})
        sql = """SELECT e.id AS entry_id, e.entry_number, e.operation_date, e.concept,
            e.status, e.reversal_of_entry_id, l.line_number, l.account_id, l.account_code,
            l.account_name, l.description, l.debit, l.credit, a.normal_balance
            FROM accounting_entries e JOIN accounting_entry_lines l ON l.entry_id=e.id
            LEFT JOIN accounting_accounts a ON a.id=l.account_id
            WHERE """ + " AND ".join(conditions) + " ORDER BY e.operation_date, e.entry_number, l.line_number LIMIT 10001"
        try:
            with self._session_factory() as session:
                rows = [dict(row) for row in session.execute(text(sql), params).mappings().all()]
            if len(rows) > 10000:
                return {"too_large": True, "total": len(rows)}
            if report_type == "ledger":
                result = build_ledger(rows, from_date=from_date, to_date=to_date, limit=limit, offset=offset)
            else:
                result = build_report(report_type, rows, from_date=from_date, to_date=to_date, limit=limit, offset=offset)
            result["filters"] = {key: value for key, value in {
                "plan_id": plan_id, "account_id": account_id,
                "account_code": account_code, "account_name": account_name, "status": status,
            }.items() if value is not None}
            return result
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

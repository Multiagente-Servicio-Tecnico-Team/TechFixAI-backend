"""Persistencia del catálogo contable, sus periodos y su auditoría."""
import json
import logging

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.adapters.persistence.accounting import _default_session_factory
from app.application.errors import AccountingConflict, AccountingStorageUnavailable
from app.application.errors import AccountingError

logger = logging.getLogger(__name__)


class AccountingCatalogRepository:
    def __init__(self, session_factory=None):
        self._session_factory = session_factory or _default_session_factory()

    @staticmethod
    def _storage_error(exc):
        logger.error("Accounting catalog persistence failed: %s", type(exc).__name__)
        return AccountingStorageUnavailable()

    @staticmethod
    def _audit(session, entity_type, entity_id, action, actor_id, old=None, new=None, reason=None):
        session.execute(text("""INSERT INTO accounting_configuration_events
            (entity_type, entity_id, action, actor_user_id, previous_state, new_state, reason)
            VALUES (:type, :id, :action, :actor, CAST(:old AS jsonb), CAST(:new AS jsonb), :reason)"""), {
            "type": entity_type, "id": entity_id, "action": action, "actor": actor_id,
            "old": json.dumps(old, ensure_ascii=False, default=str) if old is not None else None,
            "new": json.dumps(new, ensure_ascii=False, default=str) if new is not None else None,
            "reason": reason,
        })

    def list_plans(self):
        try:
            with self._session_factory() as session:
                rows = session.execute(text("""SELECT id, code, edition, name, jurisdiction, source_name,
                    source_url, effective_from, effective_to, status, is_default, created_at, updated_at
                    FROM accounting_plans ORDER BY is_default DESC, name, edition""")).mappings().all()
            return [{**dict(row), "id": int(row["id"]),
                     "effective_from": row["effective_from"].isoformat() if row["effective_from"] else None,
                     "effective_to": row["effective_to"].isoformat() if row["effective_to"] else None,
                     "created_at": row["created_at"].isoformat(), "updated_at": row["updated_at"].isoformat()}
                    for row in rows]
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def create_plan(self, values, actor_id):
        try:
            with self._session_factory() as session, session.begin():
                if values["is_default"]:
                    old = session.execute(text("""UPDATE accounting_plans SET is_default = FALSE,
                        updated_at = CURRENT_TIMESTAMP WHERE is_default IS TRUE AND status = 'ACTIVE'
                        RETURNING id, code, edition""")).mappings().all()
                    for row in old:
                        self._audit(session, "DEFAULT_PLAN", int(row["id"]), "DEFAULT_REMOVED", actor_id,
                                    {"is_default": True}, {"is_default": False})
                row = session.execute(text("""INSERT INTO accounting_plans
                    (code, edition, name, jurisdiction, source_name, source_url, effective_from,
                     effective_to, status, is_default, created_by)
                    VALUES (:code, :edition, :name, :jurisdiction, :source_name, :source_url,
                     :effective_from, :effective_to, :status, :is_default, :actor) RETURNING *"""),
                    {**values, "actor": actor_id}).mappings().one()
                self._audit(session, "PLAN", int(row["id"]), "CREATED", actor_id, None,
                            {"code": row["code"], "edition": row["edition"], "name": row["name"],
                             "status": row["status"], "is_default": row["is_default"]})
            return self.list_plans_item(int(row["id"]))
        except IntegrityError as exc:
            raise AccountingConflict("Ya existe un plan con ese código y edición, o el estado predeterminado entró en conflicto.") from exc
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def list_plans_item(self, plan_id):
        return next((item for item in self.list_plans() if item["id"] == plan_id), None)

    def set_default_plan(self, plan_id, actor_id):
        try:
            with self._session_factory() as session, session.begin():
                target = session.execute(text("SELECT id, status, is_default FROM accounting_plans WHERE id=:id FOR UPDATE"),
                                         {"id": plan_id}).mappings().first()
                if target is None:
                    from app.application.errors import AccountingNotFound
                    raise AccountingNotFound()
                if target["status"] != "ACTIVE":
                    raise AccountingConflict("Un plan inactivo no puede ser predeterminado.")
                old_rows = session.execute(text("""UPDATE accounting_plans SET is_default=FALSE,
                    updated_at=CURRENT_TIMESTAMP WHERE is_default IS TRUE AND id<>:id RETURNING id"""),
                    {"id": plan_id}).mappings().all()
                for row in old_rows:
                    self._audit(session, "DEFAULT_PLAN", int(row["id"]), "DEFAULT_REMOVED", actor_id,
                                {"is_default": True}, {"is_default": False})
                if not target["is_default"]:
                    session.execute(text("UPDATE accounting_plans SET is_default=TRUE, updated_at=CURRENT_TIMESTAMP WHERE id=:id"),
                                    {"id": plan_id})
                    self._audit(session, "DEFAULT_PLAN", plan_id, "DEFAULT_SET", actor_id,
                                {"is_default": False}, {"is_default": True})
            return self.list_plans_item(plan_id)
        except (AccountingConflict,):
            raise
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def list_accounts(self, *, plan_id, q=None, code=None, name=None, parent_account_id=None,
                      is_postable=None, status=None, limit=50, offset=0):
        conditions = ["a.plan_id=:plan_id"]
        params = {"plan_id": plan_id, "limit": limit, "offset": offset}
        if q is not None:
            conditions.append("(a.code ILIKE :q OR a.name ILIKE :q)")
            params["q"] = f"%{q}%"
        for key, value, expr in (("code", code, "a.code=:code"), ("name", name, "a.name ILIKE :name"),
                                 ("parent_account_id", parent_account_id, "a.parent_account_id=:parent_account_id"),
                                 ("is_postable", is_postable, "a.is_postable=:is_postable"),
                                 ("status", status, "a.status=:status")):
            if value is not None:
                conditions.append(expr)
                params[key] = f"%{value}%" if key == "name" else value
        where = " WHERE " + " AND ".join(conditions)
        try:
            with self._session_factory() as session:
                if session.execute(text("SELECT 1 FROM accounting_plans WHERE id=:id"), {"id": plan_id}).first() is None:
                    from app.application.errors import AccountingNotFound
                    raise AccountingNotFound()
                total = int(session.execute(text("SELECT count(*) FROM accounting_accounts a" + where), params).scalar_one())
                rows = session.execute(text("""SELECT a.id, a.plan_id, a.code, a.name, a.parent_account_id,
                    a.account_group, a.normal_balance, a.is_postable, a.status, a.effective_from, a.effective_to,
                    p.name AS parent_name, a.created_at, a.updated_at
                    FROM accounting_accounts a LEFT JOIN accounting_accounts p ON p.id=a.parent_account_id""" + where +
                    " ORDER BY a.code LIMIT :limit OFFSET :offset"), params).mappings().all()
            items = [{**dict(row), "id": int(row["id"]), "plan_id": int(row["plan_id"]),
                      "parent_account_id": int(row["parent_account_id"]) if row["parent_account_id"] else None,
                      "effective_from": row["effective_from"].isoformat() if row["effective_from"] else None,
                      "effective_to": row["effective_to"].isoformat() if row["effective_to"] else None,
                      "created_at": row["created_at"].isoformat(), "updated_at": row["updated_at"].isoformat()}
                     for row in rows]
            return {"items": items, "total": total, "limit": limit, "offset": offset}
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def get_postable_account(self, *, plan_id, operation_date, account_id=None, account_code=None):
        """Resolve an account usable on an entry date before presenting its proposal."""
        if (account_id is None) == (account_code is None):
            return None
        reference = "a.id=:account_id" if account_id is not None else "a.code=:account_code"
        params = {"plan_id": plan_id, "operation_date": operation_date,
                  "account_id": account_id, "account_code": account_code}
        try:
            with self._session_factory() as session:
                row = session.execute(text(f"""SELECT a.id,a.plan_id,a.code,a.name,a.status,a.is_postable,
                        a.effective_from,a.effective_to
                    FROM accounting_accounts a JOIN accounting_plans p ON p.id=a.plan_id
                    WHERE {reference} AND a.plan_id=:plan_id AND p.status='ACTIVE'
                      AND a.status='ACTIVE' AND a.is_postable IS TRUE
                      AND (a.effective_from IS NULL OR a.effective_from<=:operation_date)
                      AND (a.effective_to IS NULL OR a.effective_to>=:operation_date)
                    LIMIT 1"""), params).mappings().first()
            return dict(row) if row else None
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def create_account(self, values, actor_id):
        try:
            with self._session_factory() as session, session.begin():
                plan_status = session.execute(text("SELECT status FROM accounting_plans WHERE id=:id FOR SHARE"),
                                              {"id": values["plan_id"]}).scalar_one_or_none()
                if plan_status is None:
                    from app.application.errors import AccountingNotFound
                    raise AccountingNotFound()
                if plan_status != "ACTIVE":
                    from app.domain.accounting import AccountingValidationError
                    raise AccountingValidationError("No se pueden agregar cuentas a un plan inactivo.")
                row = session.execute(text("""INSERT INTO accounting_accounts
                    (plan_id, code, name, parent_account_id, account_group, normal_balance, is_postable,
                     status, effective_from, effective_to, created_by)
                    VALUES (:plan_id, :code, :name, :parent_account_id, :account_group, :normal_balance,
                     :is_postable, :status, :effective_from, :effective_to, :actor) RETURNING *"""),
                    {**values, "actor": actor_id}).mappings().one()
                self._audit(session, "ACCOUNT", int(row["id"]), "CREATED", actor_id, None,
                            {"plan_id": int(row["plan_id"]), "code": row["code"], "name": row["name"],
                             "normal_balance": row["normal_balance"], "is_postable": row["is_postable"],
                             "status": row["status"]})
            return self.list_accounts(plan_id=int(row["plan_id"]), code=row["code"], limit=1)["items"][0]
        except IntegrityError as exc:
            raise AccountingConflict("Código duplicado o jerarquía de cuenta no válida.") from exc
        except AccountingError:
            raise
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def update_account(self, account_id, changes, actor_id):
        allowed = {key: value for key, value in changes.items() if key in {
            "name", "parent_account_id", "account_group", "normal_balance", "is_postable", "status",
            "effective_from", "effective_to"}}
        if not allowed:
            from app.domain.accounting import AccountingValidationError
            raise AccountingValidationError("No se indicaron cambios permitidos.")
        setters = ", ".join(f"{key}=:{key}" for key in allowed)
        try:
            with self._session_factory() as session, session.begin():
                old = session.execute(text("SELECT * FROM accounting_accounts WHERE id=:id FOR UPDATE"),
                                      {"id": account_id}).mappings().first()
                if old is None:
                    from app.application.errors import AccountingNotFound
                    raise AccountingNotFound()
                old_state = {k: old[k] for k in allowed}
                values = {**allowed, "id": account_id}
                row = session.execute(text(f"UPDATE accounting_accounts SET {setters}, updated_at=CURRENT_TIMESTAMP WHERE id=:id RETURNING *"),
                                      values).mappings().one()
                self._audit(session, "ACCOUNT", account_id, "UPDATED", actor_id, old_state,
                            {k: row[k] for k in allowed})
            return self.list_accounts(plan_id=int(row["plan_id"]), code=row["code"], limit=1)["items"][0]
        except IntegrityError as exc:
            raise AccountingConflict("La actualización contradice la jerarquía o una referencia existente.") from exc
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def list_audit(self, *, entity_type=None, entity_id=None, from_at=None, to_at=None, limit=50, offset=0):
        conditions, params = [], {"limit": limit, "offset": offset}
        for key, value in (("entity_type", entity_type), ("entity_id", entity_id)):
            if value is not None:
                conditions.append(f"{key} = :{key}")
                params[key] = value
        for key, value, operator in (("from_at", from_at, ">="), ("to_at", to_at, "<=")):
            if value is not None:
                conditions.append(f"created_at {operator} CAST(:{key} AS timestamptz)")
                params[key] = value
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        try:
            with self._session_factory() as session:
                total = int(session.execute(text("SELECT count(*) FROM accounting_configuration_events" + where), params).scalar_one())
                rows = session.execute(text("""SELECT id, entity_type, entity_id, action, actor_user_id,
                    previous_state, new_state, reason, created_at FROM accounting_configuration_events""" + where +
                    " ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset"), params).mappings().all()
            return {"items": [{"id": int(r["id"]), "entity_type": r["entity_type"], "entity_id": int(r["entity_id"]),
                                "action": r["action"], "actor_user_id": int(r["actor_user_id"]),
                                "occurred_at": r["created_at"].isoformat(), "prior_state": r["previous_state"],
                                "new_state": r["new_state"], "reason": r["reason"]}
                               for r in rows], "total": total, "limit": limit, "offset": offset}
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def list_periods(self, *, from_period=None, to_period=None, status=None, limit=100, offset=0):
        conditions, params = [], {"limit": limit, "offset": offset}
        for key, value, expr in (("from_period", from_period, "(year::text || '-' || lpad(month::text,2,'0')) >= :from_period"),
                                 ("to_period", to_period, "(year::text || '-' || lpad(month::text,2,'0')) <= :to_period"),
                                 ("status", status, "status=:status")):
            if value is not None:
                conditions.append(expr)
                params[key] = value
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        try:
            with self._session_factory() as session:
                total = int(session.execute(text("SELECT count(*) FROM accounting_periods" + where), params).scalar_one())
                rows = session.execute(text("""SELECT id, year, month, status, closed_at, closed_by,
                    reopened_at, reopened_by, reopen_reason, created_at, updated_at,
                    CASE WHEN status='OPEN' THEN reopened_at ELSE closed_at END AS last_transition_at,
                    CASE WHEN status='OPEN' THEN reopened_by ELSE closed_by END AS last_transition_by,
                    CASE WHEN status='OPEN' THEN reopen_reason ELSE NULL END AS last_reason
                    FROM accounting_periods""" +
                    where + " ORDER BY year DESC, month DESC LIMIT :limit OFFSET :offset"), params).mappings().all()
            return {"items": [{**dict(r), "id": int(r["id"]), "year": int(r["year"]), "month": int(r["month"]),
                                "closed_by": int(r["closed_by"]) if r["closed_by"] else None,
                                "reopened_by": int(r["reopened_by"]) if r["reopened_by"] else None,
                                **{k: r[k].isoformat() if r[k] else None for k in ("closed_at", "reopened_at", "created_at", "updated_at")}}
                               for r in rows], "total": total, "limit": limit, "offset": offset}
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def transition_period(self, year, month, actor_id, *, close, reason=None):
        try:
            with self._session_factory() as session, session.begin():
                session.execute(text("""INSERT INTO accounting_periods(year, month, status)
                    VALUES (:year, :month, 'OPEN') ON CONFLICT (year, month) DO NOTHING"""),
                    {"year": year, "month": month})
                row = session.execute(text("SELECT * FROM accounting_periods WHERE year=:year AND month=:month FOR UPDATE"),
                                      {"year": year, "month": month}).mappings().one()
                desired, action = ("CLOSED", "PERIOD_CLOSED") if close else ("OPEN", "PERIOD_REOPENED")
                if row["status"] == desired:
                    raise AccountingConflict("El periodo ya se encuentra en ese estado.")
                if not close and not reason:
                    from app.domain.accounting import AccountingValidationError
                    raise AccountingValidationError("Indica un motivo para reabrir el periodo.")
                if close:
                    session.execute(text("""UPDATE accounting_periods SET status='CLOSED', closed_at=CURRENT_TIMESTAMP,
                        closed_by=:actor, updated_at=CURRENT_TIMESTAMP WHERE id=:id"""),
                        {"actor": actor_id, "id": row["id"]})
                else:
                    session.execute(text("""UPDATE accounting_periods SET status='OPEN', reopened_at=CURRENT_TIMESTAMP,
                        reopened_by=:actor, reopen_reason=:reason, updated_at=CURRENT_TIMESTAMP WHERE id=:id"""),
                        {"actor": actor_id, "reason": reason.strip(), "id": row["id"]})
                self._audit(session, "PERIOD", int(row["id"]), action, actor_id,
                            {"status": row["status"]}, {"status": desired}, reason)
            return next(item for item in self.list_periods(from_period=f"{year:04d}-{month:02d}",
                         to_period=f"{year:04d}-{month:02d}")["items"] if item["month"] == month)
        except (AccountingConflict,):
            raise
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def period_events(self, year, month, *, limit=100, offset=0):
        try:
            with self._session_factory() as session:
                period_id = session.execute(text("SELECT id FROM accounting_periods WHERE year=:year AND month=:month"),
                                            {"year": year, "month": month}).scalar_one_or_none()
                if period_id is None:
                    from app.application.errors import AccountingNotFound
                    raise AccountingNotFound()
            result = self.list_audit(entity_type="PERIOD", entity_id=int(period_id), limit=limit, offset=offset)
            return {"items": [{"id": row["id"], "entity_type": row["entity_type"], "entity_id": row["entity_id"],
                     "action": row["action"], "actor_user_id": row["actor_user_id"],
                     "occurred_at": row["occurred_at"], "prior_state": row["prior_state"],
                     "new_state": row["new_state"], "reason": row["reason"]} for row in result["items"]],
                    "total": result["total"], "limit": limit, "offset": offset}
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

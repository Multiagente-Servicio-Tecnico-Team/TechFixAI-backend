"""Persistencia v2 aislada. Sin conexión, DDL ni escritura al importar.

customer_id debe provenir de SessionGuard, nunca del modelo/navegador.
PostgreSQL serializa escrituras mediante bloqueos de filas. SQLite se usa sólo
en pruebas secuenciales. No se reserva ni modifica stock al cotizar.
"""
from decimal import Decimal, localcontext

from sqlalchemy import MetaData, Table, insert, select, update
from sqlalchemy.exc import IntegrityError


class RetryConflict(ValueError):
    """La misma operación se reintentó con datos distintos."""


def _id(value):
    if type(value) is not int or not 0 < value <= 9223372036854775807:
        raise ValueError("Identificador inválido")
    return value


def _quantity(value):
    if type(value) is not int or not 0 < value <= 2147483647:
        raise ValueError("Cantidad fuera de INTEGER")
    return value


def _text(value, maximum=None):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Texto obligatorio")
    value = value.strip()
    if maximum is not None and len(value) > maximum:
        raise ValueError("Texto demasiado largo")
    return value


def _money(value):
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("El importe debe ser Decimal finito")
    if value < 0 or value > Decimal("99999999.99"):
        raise ValueError("Importe fuera de NUMERIC(10,2)")
    with localcontext() as context:
        context.prec = 40
        rounded = value.quantize(Decimal("0.01"))
    if value != rounded:
        raise ValueError("Importe fuera de NUMERIC(10,2)")
    return rounded


def _subtotal(price, quantity):
    with localcontext() as context:
        context.prec = 40
        return _money(price * quantity)


def _total(amounts):
    with localcontext() as context:
        context.prec = 40
        return _money(sum(amounts, Decimal("0.00")))


class DecentralizedRepository:
    def get_warranty(self, *, customer_id, warranty_code):
        from sqlalchemy import func
        with self.engine.connect() as connection:
            warranties = self._table(connection, "warranties")
            row = connection.execute(select(warranties, func.current_date().label("as_of")).where(
                warranties.c.customer_id == _id(customer_id), warranties.c.warranty_code == _text(warranty_code, 50)
            )).mappings().first()
            if row is None:
                raise LookupError("Garantía no encontrada")
            status = row["status"]
            if status != "VOIDED" and row["end_date"] < row["as_of"]:
                status = "EXPIRED"
            elif status == "ACTIVE" and row["start_date"] > row["as_of"]:
                status = "NOT_STARTED"  # Presentation only; never a persisted enum.
            return {**row, "effective_status": status}

    def get_warranty_claim(self, *, customer_id, claim_id):
        with self.engine.connect() as connection:
            claims = self._table(connection, "warranty_claims")
            warranties = self._table(connection, "warranties")
            tickets = self._table(connection, "tickets")
            row = connection.execute(select(claims).join(warranties, claims.c.warranty_id == warranties.c.id)
                .join(tickets, claims.c.ticket_id == tickets.c.id).where(claims.c.id == _id(claim_id),
                    warranties.c.customer_id == _id(customer_id), tickets.c.customer_id == customer_id)).mappings().first()
            if row is None:
                raise LookupError("Reclamo no encontrado")
            return dict(row)

    def create_warranty_claim(self, *, customer_id, ticket_id, warranty_code, claim_code, reason):
        from sqlalchemy import func
        values = dict(ticket_id=_id(ticket_id), claim_code=_text(claim_code, 50), reason=_text(reason))
        code = _text(warranty_code, 50)
        with self.engine.begin() as connection:
            self._customer(connection, customer_id)
            tickets, ticket = self._ticket(connection, customer_id, ticket_id, lock=True)
            warranties = self._table(connection, "warranties")
            warranty = connection.execute(select(warranties).where(warranties.c.warranty_code == code,
                warranties.c.customer_id == customer_id).with_for_update()).mappings().first()
            if warranty is None:
                raise LookupError("Garantía no encontrada")
            claims = self._table(connection, "warranty_claims")
            existing = list(connection.execute(select(claims).where(
                (claims.c.claim_code == values["claim_code"]) | (claims.c.ticket_id == ticket_id)
            ).with_for_update()).mappings())
            values["warranty_id"] = warranty["id"]
            if existing:
                if len(existing) != 1 or any(existing[0][key] != value for key, value in values.items()):
                    raise RetryConflict("Reclamo existente incompatible")
                return dict(existing[0])
            today = connection.scalar(select(func.current_date()))
            if (ticket["request_type"] != "WARRANTY_CLAIM" or ticket["status"] != "NEW"
                    or warranty["status"] != "ACTIVE" or not warranty["start_date"] <= today <= warranty["end_date"]):
                raise ValueError("Condiciones de reclamo no satisfechas")
            claim_id = connection.execute(insert(claims).values(**values, status="IN_REVIEW").returning(claims.c.id)).scalar_one()
            result = connection.execute(update(tickets).where(tickets.c.id == ticket_id,
                tickets.c.customer_id == customer_id, tickets.c.status == "NEW").values(status="WARRANTY_IN_REVIEW"))
            if result.rowcount != 1:
                raise RuntimeError("Ticket de reclamo no actualizado")
            return dict(connection.execute(select(claims).where(claims.c.id == claim_id)).mappings().one())

    def create_warranty(self, *, customer_id, ticket_id, quote_id, warranty_code, item_or_service_name, authorization):
        """Caller supplies a trusted server grant, never a user/model assertion.

        The API has no issuer of such grants yet and leaves issuance disabled.
        Locking the customer and ticket serializes different conversations.
        """
        from sqlalchemy import func, cast, Date, literal_column
        from datetime import date
        from calendar import monthrange
        values = dict(customer_id=_id(customer_id), ticket_id=_id(ticket_id), quote_id=_id(quote_id),
            warranty_code=_text(warranty_code, 50), item_or_service_name=_text(item_or_service_name, 200))
        expected = {key: values[key] for key in ("customer_id", "ticket_id", "quote_id", "item_or_service_name")}
        if not isinstance(authorization, dict) or authorization != expected:
            raise ValueError("Falta autorización comercial del servidor")
        with self.engine.begin() as connection:
            self._customer(connection, customer_id)
            _, ticket = self._ticket(connection, customer_id, ticket_id, lock=True)
            quotes = self._table(connection, "quotes")
            quote = connection.execute(select(quotes).where(quotes.c.id == quote_id,
                quotes.c.ticket_id == ticket_id, quotes.c.status == "ACCEPTED").with_for_update()).mappings().first()
            if quote is None or ticket["request_type"] not in {"SALE", "PC_BUILD", "REPAIR", "SUPPORT"} or ticket["status"] == "CANCELLED":
                raise ValueError("Referencias comerciales incompatibles")
            warranties = self._table(connection, "warranties")
            existing = list(connection.execute(select(warranties).where(
                (warranties.c.warranty_code == values["warranty_code"]) | (warranties.c.ticket_id == ticket_id)
            ).with_for_update()).mappings())
            if existing:
                if len(existing) != 1 or any(existing[0][key] != value for key, value in values.items()) or existing[0]["warranty_months"] != 3:
                    raise RetryConflict("Emisión existente incompatible")
                return dict(existing[0])
            if connection.dialect.name == "postgresql":
                expiry = cast(func.current_date() + literal_column("INTERVAL '3 months'"), Date)
            else:
                # Isolated SQLite tests reproduce PostgreSQL's month-end clamp.
                today = connection.scalar(select(func.current_date()))
                month = today.month + 3
                year = today.year + (month - 1) // 12
                month = (month - 1) % 12 + 1
                expiry = date(year, month, min(today.day, monthrange(year, month)[1]))
            warranty_id = connection.execute(insert(warranties).values(**values, warranty_months=3,
                start_date=func.current_date(), end_date=expiry, status="ACTIVE").returning(warranties.c.id)).scalar_one()
            return dict(connection.execute(select(warranties).where(warranties.c.id == warranty_id)).mappings().one())

    def __init__(self, engine=None):
        self._engine = engine

    @property
    def engine(self):
        if self._engine is None:
            from app.database.connection import get_engine

            self._engine = get_engine()
        return self._engine

    @staticmethod
    def _table(connection, name):
        return Table(name, MetaData(), autoload_with=connection)

    def _customer(self, connection, customer_id):
        users = self._table(connection, "users")
        row = connection.execute(select(users.c.id).where(
            users.c.id == _id(customer_id), users.c.active.is_(True),
            users.c.role == "CUSTOMER",
        ).with_for_update()).first()
        if row is None:
            raise LookupError("Cliente no disponible")

    def _ticket(self, connection, customer_id, ticket_id, *, lock=False):
        tickets = self._table(connection, "tickets")
        query = select(tickets).where(tickets.c.id == _id(ticket_id),
                                       tickets.c.customer_id == _id(customer_id))
        if lock:
            query = query.with_for_update()
        row = connection.execute(query).mappings().first()
        if row is None:
            raise LookupError("Ticket no encontrado")
        return tickets, dict(row)

    def create_ticket(self, *, customer_id, code, title, failure_description, request_type):
        """code es una clave estable generada por el sistema ANTES del primer intento.

        UNIQUE(code) y bloqueo del cliente evitan duplicados; reutilizar código
        con distinto contenido falla. Un nuevo código representa otra operación.
        """
        from app.agents.decentralized.state import RequestType
        from typing import get_args

        if request_type not in get_args(RequestType):
            raise ValueError("request_type no admitido por PostgreSQL v2")
        values = dict(customer_id=_id(customer_id), code=_text(code, 20),
                      title=_text(title, 200), failure_description=_text(failure_description),
                      request_type=request_type)
        with self.engine.begin() as connection:
            self._customer(connection, customer_id)
            tickets = self._table(connection, "tickets")
            query = select(tickets).where(tickets.c.code == values["code"])
            row = connection.execute(query).mappings().first()
            if row is None:
                try:
                    with connection.begin_nested():
                        ticket_id = connection.execute(insert(tickets).values(
                            **values, status="NEW", diagnosis_type="NONE",
                            is_remote_service=False,
                        ).returning(tickets.c.id)).scalar_one()
                    return self._ticket(connection, customer_id, ticket_id)[1]
                except IntegrityError:
                    # Colisión concurrente de UNIQUE(code); conservar la transacción.
                    row = connection.execute(query).mappings().first()
                    if row is None:
                        raise
            if any(row[key] != value for key, value in values.items()):
                raise RetryConflict("Código de ticket ya utilizado")
            return dict(row)

    def get_ticket(self, *, customer_id, ticket_id):
        with self.engine.connect() as connection:
            return self._ticket(connection, customer_id, ticket_id)[1]

    def create_pending_payment(self, *, customer_id, ticket_id, quote_id, payment_code):
        """Amount comes from locked SQL quote only. No model-supplied amount.

        Row lock order matches quote creation: customer -> ticket -> quote.
        Another code for a quote with an existing payment requires reconciliation;
        this is an application conflict, not an assumed UNIQUE(quote_id).
        All writers must follow this protocol for cross-thread serialization.
        """
        customer_id, ticket_id, quote_id = _id(customer_id), _id(ticket_id), _id(quote_id)
        payment_code = _text(payment_code, 50)
        with self.engine.begin() as connection:
            self._customer(connection, customer_id)
            tickets, ticket = self._ticket(connection, customer_id, ticket_id, lock=True)
            quotes = self._table(connection, "quotes")
            quote = connection.execute(select(quotes).where(
                quotes.c.id == quote_id, quotes.c.ticket_id == ticket_id,
            ).with_for_update()).mappings().first()
            if quote is None:
                raise LookupError("Cotización no encontrada")
            if quote["status"] != "ACCEPTED":
                raise ValueError("Cotización no aceptada en PostgreSQL")
            amount = _money(quote["total_amount"])
            if amount <= 0:
                raise ValueError("Importe de pago debe ser positivo")
            payments = self._table(connection, "payments")
            values = dict(customer_id=customer_id, ticket_id=ticket_id, quote_id=quote_id,
                          payment_code=payment_code, amount=amount)
            existing = connection.execute(select(payments).where(
                payments.c.payment_code == payment_code)).mappings().first()
            if existing is not None:
                if any(existing[key] != value for key, value in values.items()):
                    raise RetryConflict("Código de pago con contenido incompatible")
                return dict(existing)  # Preserve real payment/ticket status on retries.
            if connection.execute(select(payments.c.id).where(
                    payments.c.quote_id == quote_id)).first() is not None:
                raise RetryConflict("Cotización con pago previo; requiere reconciliación")
            if ticket["status"] != "QUOTED":
                raise ValueError("Ticket no admite registro inicial de pago")
            try:
                row = connection.execute(insert(payments).values(**values, status="PENDING")
                                         .returning(*payments.c)).mappings().one()
            except IntegrityError:
                raise RetryConflict("Conflicto al registrar código de pago") from None
            updated = connection.execute(update(tickets).where(
                tickets.c.id == ticket_id, tickets.c.customer_id == customer_id,
                tickets.c.status == "QUOTED").values(status="PAYMENT_PENDING"))
            if updated.rowcount != 1:
                raise RuntimeError("No se actualizó exactamente el ticket esperado")
            return dict(row)

    def list_tickets(self, *, customer_id):
        with self.engine.connect() as connection:
            tickets = self._table(connection, "tickets")
            return [dict(row) for row in connection.execute(select(tickets).where(
                tickets.c.customer_id == _id(customer_id)
            ).order_by(tickets.c.id)).mappings()]

    def _logistics_preconditions(self, connection, customer_id, ticket_id):
        _, ticket = self._ticket(connection, customer_id, ticket_id, lock=True)
        if ticket["status"] in {"CANCELLED", "DELIVERED"}:
            raise ValueError("Ticket cerrado; requiere revisión")
        kind = ticket["request_type"]
        if kind in {"REPAIR", "SUPPORT"}:
            return ticket
        if kind in {"SALE", "PC_BUILD"}:
            quotes = self._table(connection, "quotes")
            payments = self._table(connection, "payments")
            row = connection.execute(select(payments.c.id).join(quotes, payments.c.quote_id == quotes.c.id).where(
                payments.c.ticket_id == ticket_id, payments.c.customer_id == customer_id,
                quotes.c.ticket_id == ticket_id, quotes.c.status == "ACCEPTED",
                payments.c.status.in_(["PENDING", "COMPLETED"]), payments.c.amount > 0,
                payments.c.amount == quotes.c.total_amount).with_for_update()).first()
            if row is None:
                raise ValueError("Falta cotización aceptada y pago persistido verificable")
            return ticket
        if kind == "WARRANTY_CLAIM":
            claims = self._table(connection, "warranty_claims")
            warranties = self._table(connection, "warranties")
            from sqlalchemy import func
            row = connection.execute(select(claims.c.id).join(warranties, claims.c.warranty_id == warranties.c.id).where(
                claims.c.ticket_id == ticket_id, warranties.c.customer_id == customer_id,
                claims.c.status == "IN_REVIEW", warranties.c.status.in_(["ACTIVE", "CLAIMED"]),
                warranties.c.start_date <= func.current_date(), warranties.c.end_date >= func.current_date()
            ).with_for_update()).first()
            if row is None:
                raise ValueError("Falta póliza vigente y reclamo persistido en revisión")
            return ticket
        raise ValueError("Flujo logístico no admitido")

    def get_logistics_context(self, *, customer_id, ticket_id):
        with self.engine.begin() as connection:
            self._customer(connection, customer_id)
            return self._logistics_preconditions(connection, _id(customer_id), _id(ticket_id))

    def get_payment(self, *, customer_id, payment_id):
        with self.engine.connect() as connection:
            payments = self._table(connection, "payments")
            tickets = self._table(connection, "tickets")
            row = connection.execute(select(payments).join(tickets, payments.c.ticket_id == tickets.c.id).where(
                payments.c.id == _id(payment_id), payments.c.customer_id == _id(customer_id),
                tickets.c.customer_id == customer_id)).mappings().first()
            if row is None:
                raise LookupError("Pago no encontrado")
            return dict(row)

    def create_initial_logistics(self, *, customer_id, ticket_id, mode, courier_company=None,
                                 shipping_address=None, recipient_name=None, recipient_phone=None):
        """One equivalent initial record per ticket via row locks, no UNIQUE assumed.

        Only inserts PENDING_RECEIPT. Does not modify ticket, stock, payment or
        operational evidence. Different content/multiple existing records conflicts.
        """
        from app.agents.decentralized.logistics_operations import logistics_payload
        customer_id, ticket_id = _id(customer_id), _id(ticket_id)
        with self.engine.begin() as connection:
            self._customer(connection, customer_id)
            ticket = self._logistics_preconditions(connection, customer_id, ticket_id)
            payload = logistics_payload(customer_id=customer_id, ticket_id=ticket_id,
                request_type=ticket["request_type"], data=dict(mode=mode, courier_company=courier_company,
                    shipping_address=shipping_address, recipient_name=recipient_name, recipient_phone=recipient_phone))
            values = {key: value for key, value in payload.items() if key != "customer_id"}
            table = self._table(connection, "logistics_records")
            rows = list(connection.execute(select(table).where(table.c.ticket_id == ticket_id)).mappings())
            if rows:
                if len(rows) != 1 or any(rows[0][key] != value for key, value in values.items()):
                    raise RetryConflict("Logística existente incompatible; requiere reconciliación")
                return dict(rows[0])
            return dict(connection.execute(insert(table).values(**values, status="PENDING_RECEIPT")
                        .returning(*table.c)).mappings().one())

    def search_inventory(self, *, term, category=None, limit=20):
        """Código exacto primero; candidatos alternativos requieren selección."""
        term = _text(term)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Límite inválido")
        with self.engine.connect() as connection:
            parts = self._table(connection, "spare_parts")
            query = select(parts).where(parts.c.active.is_(True))
            if category is not None:
                query = query.where(parts.c.category == _text(category, 50))
            exact = connection.execute(query.where(parts.c.code == term)).mappings().first()
            if exact:
                return [dict(exact)]
            pattern = "%" + term.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
            return [dict(row) for row in connection.execute(query.where(
                parts.c.name.ilike(pattern, escape="!")
                | parts.c.description.ilike(pattern, escape="!")
                | parts.c.category.ilike(pattern, escape="!")
            ).order_by(parts.c.code).limit(limit)).mappings()]

    def get_inventory(self, *, spare_part_id, quantity):
        _quantity(quantity)
        with self.engine.connect() as connection:
            parts = self._table(connection, "spare_parts")
            row = connection.execute(select(parts).where(
                parts.c.id == _id(spare_part_id), parts.c.active.is_(True),
            )).mappings().first()
            return {**row, "requested_quantity": quantity,
                    "available": row["current_stock"] >= quantity} if row else None

    def get_quote(self, *, customer_id, quote_id):
        with self.engine.connect() as connection:
            quotes = self._table(connection, "quotes")
            tickets = self._table(connection, "tickets")
            row = connection.execute(select(quotes).join(tickets, quotes.c.ticket_id == tickets.c.id).where(
                quotes.c.id == _id(quote_id), tickets.c.customer_id == _id(customer_id),
            )).mappings().first()
            if row is None:
                raise LookupError("Cotización no encontrada")
            return {**row, "lines": self._lines(connection, row["id"])}

    def list_quotes(self, *, customer_id, ticket_id):
        with self.engine.connect() as connection:
            self._ticket(connection, customer_id, ticket_id)
            quotes = self._table(connection, "quotes")
            return [{**row, "lines": self._lines(connection, row["id"])}
                    for row in connection.execute(select(quotes).where(
                        quotes.c.ticket_id == ticket_id
                    ).order_by(quotes.c.id)).mappings()]

    def _lines(self, connection, quote_id):
        details = self._table(connection, "quote_details")
        return [dict(row) for row in connection.execute(select(details).where(
            details.c.quote_id == quote_id
        ).order_by(details.c.spare_part_id)).mappings()]

    def create_accepted_quote(self, *, customer_id, ticket_id, quote_type,
                              labor_cost, lines, explicitly_accepted, observations=None):
        """Una cotización aceptada por ticket para este adaptador, sin cambiar el DDL.

        Bloquear ticket antes de consultar/insertar serializa reintentos PostgreSQL.
        Una propuesta distinta sobre un ticket ya aceptado requiere reconciliación,
        nunca una inserción silenciosa. Precios externos aún no están soportados.
        explicitly_accepted exige el booleano True; no valida la revisión
        conversacional. El consumidor debe validar la propuesta vigente en state.py
        antes de llamar. Este adaptador sólo revalida pertenencia, precio y stock.
        """
        if explicitly_accepted is not True:
            raise ValueError("Falta aceptación explícita")
        if quote_type not in {"REPAIR", "DIRECT_SALE", "PC_BUILD"}:
            raise ValueError("quote_type no admitido")
        labor_cost = _money(labor_cost)
        if quote_type == "DIRECT_SALE" and labor_cost != 0:
            raise ValueError("Venta directa sin mano de obra")
        if observations is not None:
            observations = _text(observations)
        normalized = []
        seen = set()
        for line in lines:
            if line.get("custom_item_name") is not None:
                raise ValueError("Artículo externo sin cotización verificable")
            part_id = _id(line["spare_part_id"])
            if part_id in seen:
                raise ValueError("Repuesto duplicado; consolidar cantidades")
            seen.add(part_id)
            quantity = _quantity(line["quantity"])
            price = _money(line["unit_price"])
            subtotal = _subtotal(price, quantity)
            if "subtotal" in line and _money(line["subtotal"]) != subtotal:
                raise ValueError("Subtotal no coincide con la propuesta")
            normalized.append(dict(spare_part_id=part_id, custom_item_name=None,
                                   quantity=quantity, unit_price=price, subtotal=subtotal))
        normalized.sort(key=lambda line: line["spare_part_id"])
        if not normalized and quote_type != "REPAIR":
            raise ValueError("Faltan artículos")
        parts_cost = _total(line["subtotal"] for line in normalized)
        total = _total([labor_cost, parts_cost])
        with self.engine.begin() as connection:
            self._customer(connection, customer_id)
            tickets, ticket = self._ticket(connection, customer_id, ticket_id, lock=True)
            allowed = {"REPAIR": {"REPAIR", "SUPPORT"}, "DIRECT_SALE": {"SALE"}, "PC_BUILD": {"PC_BUILD"}}
            if ticket["request_type"] not in allowed[quote_type]:
                raise ValueError("Tipo de cotización incompatible con ticket")
            quotes = self._table(connection, "quotes")
            existing = list(connection.execute(select(quotes).where(
                quotes.c.ticket_id == ticket_id, quotes.c.status == "ACCEPTED",
            )).mappings())
            values = dict(ticket_id=ticket_id, quote_type=quote_type, labor_cost=labor_cost,
                          parts_cost=parts_cost, total_amount=total, status="ACCEPTED",
                          observations=observations)
            if existing:
                saved_lines = self._lines(connection, existing[0]["id"])
                matches = [{key: line[key] for key in normalized[0]} for line in saved_lines] if normalized else []
                if (len(existing) != 1 or any(existing[0][key] != value for key, value in values.items())
                        or len(saved_lines) != len(normalized) or matches != normalized):
                    raise RetryConflict("Ticket con cotización aceptada diferente")
                return {**existing[0], "lines": saved_lines}
            if ticket["status"] not in {"NEW", "IN_DIAGNOSIS"}:
                raise ValueError("Ticket no admite nueva cotización")
            parts = self._table(connection, "spare_parts")
            for line in normalized:
                item = connection.execute(select(parts).where(
                    parts.c.id == line["spare_part_id"], parts.c.active.is_(True),
                ).with_for_update()).mappings().first()
                if (item is None or item["current_stock"] < line["quantity"]
                        or item["unit_price"] != line["unit_price"]):
                    raise ValueError("Inventario o precio cambió; renovar propuesta")
            quote_id = connection.execute(insert(quotes).values(**values).returning(quotes.c.id)).scalar_one()
            details = self._table(connection, "quote_details")
            for line in normalized:
                connection.execute(insert(details).values(quote_id=quote_id, **line))
            result = connection.execute(update(tickets).where(
                tickets.c.id == ticket_id, tickets.c.customer_id == customer_id,
            ).values(status="QUOTED"))
            if result.rowcount != 1:
                raise RuntimeError("No se actualizó el ticket")
            return {**connection.execute(select(quotes).where(quotes.c.id == quote_id)).mappings().one(),
                    "lines": self._lines(connection, quote_id)}

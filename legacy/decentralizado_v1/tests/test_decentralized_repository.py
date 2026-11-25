"""SQLite aislado con columnas v2; nunca ejecuta scripts de referencia."""
from decimal import Decimal, localcontext

import pytest
from sqlalchemy import (Boolean, CheckConstraint, Column, ForeignKey, Integer,
                        MetaData, Numeric, String, Table, Text, create_engine,
                        event, func, select)
from sqlalchemy.dialects import postgresql

from app.database.decentralized_repository import DecentralizedRepository, RetryConflict


@pytest.fixture
def database():
    engine = create_engine("sqlite://")
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    metadata = MetaData()
    users = Table("users", metadata, Column("id", Integer, primary_key=True),
                  Column("active", Boolean), Column("role", String))
    tickets = Table("tickets", metadata, Column("id", Integer, primary_key=True),
                    Column("code", String(20), unique=True, nullable=False),
                    Column("customer_id", ForeignKey("users.id"), nullable=False),
                    Column("title", String(200), nullable=False),
                    Column("failure_description", Text, nullable=False),
                    Column("request_type", String, nullable=False),
                    Column("diagnosis_type", String, nullable=False),
                    Column("status", String, nullable=False),
                    Column("hardware_diagnosis", Text), Column("software_diagnosis", Text),
                    Column("is_remote_service", Boolean, nullable=False))
    parts = Table("spare_parts", metadata, Column("id", Integer, primary_key=True),
                  Column("code", String, unique=True), Column("name", String),
                  Column("category", String), Column("description", Text),
                  Column("unit_price", Numeric(10, 2)), Column("current_stock", Integer),
                  Column("minimum_threshold", Integer), Column("active", Boolean))
    quotes = Table("quotes", metadata, Column("id", Integer, primary_key=True),
                   Column("ticket_id", ForeignKey("tickets.id"), nullable=False),
                   Column("quote_type", String), Column("labor_cost", Numeric(10, 2)),
                   Column("parts_cost", Numeric(10, 2)), Column("total_amount", Numeric(10, 2)),
                   Column("status", String), Column("observations", Text))
    details = Table("quote_details", metadata, Column("id", Integer, primary_key=True),
                    Column("quote_id", ForeignKey("quotes.id"), nullable=False),
                    Column("spare_part_id", ForeignKey("spare_parts.id")),
                    Column("custom_item_name", String), Column("quantity", Integer),
                    Column("unit_price", Numeric(10, 2)), Column("subtotal", Numeric(10, 2)),
                    CheckConstraint("quantity > 0"))
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(users.insert(), [dict(id=1, active=True, role="CUSTOMER"),
                                      dict(id=2, active=True, role="CUSTOMER"),
                                      dict(id=3, active=False, role="CUSTOMER"),
                                      dict(id=4, active=True, role="ADMIN")])
        conn.execute(parts.insert(), [
            dict(id=1, code="SSD-TEST", name="SSD de prueba", category="SSD", description="Catálogo de prueba",
                 unit_price=Decimal("180.00"), current_stock=3, minimum_threshold=1, active=True),
            dict(id=2, code="RAM-TEST", name="RAM de prueba", category="RAM", description="Catálogo de prueba",
                 unit_price=Decimal("150.00"), current_stock=0, minimum_threshold=1, active=True),
            dict(id=3, code="INACTIVE", name="Inactivo", category="SSD", description="",
                 unit_price=Decimal("180.00"), current_stock=3, minimum_threshold=1, active=False),
        ])
    yield DecentralizedRepository(engine), engine, tickets, parts, quotes, details
    engine.dispose()


def ticket(repo, **changes):
    values = dict(customer_id=1, code="TCK-TEST", title="Venta de prueba",
                  failure_description="SSD de prueba", request_type="SALE")
    return repo.create_ticket(**{**values, **changes})


def quote(repo, ticket_id, **changes):
    values = dict(customer_id=1, ticket_id=ticket_id, quote_type="DIRECT_SALE",
                  labor_cost=Decimal("0.00"), explicitly_accepted=True,
                  lines=[dict(spare_part_id=1, quantity=2, unit_price=Decimal("180.00"))])
    return repo.create_accepted_quote(**{**values, **changes})


def test_ticket_v2_reintento_y_pertenencia(database):
    repo, *_ = database
    first = ticket(repo)
    assert first["status"] == "NEW" and first["diagnosis_type"] == "NONE"
    assert "provisional_diagnosis" not in first
    assert ticket(repo)["id"] == first["id"]
    assert repo.get_ticket(customer_id=1, ticket_id=first["id"])["code"] == "TCK-TEST"
    assert len(repo.list_tickets(customer_id=1)) == 1
    assert repo.list_tickets(customer_id=2) == []
    with pytest.raises(LookupError):
        repo.get_ticket(customer_id=2, ticket_id=first["id"])
    with pytest.raises(RetryConflict):
        ticket(repo, title="Otra solicitud")
    with pytest.raises(RetryConflict):
        ticket(repo, customer_id=2)


@pytest.mark.parametrize("customer_id", [3, 4, 99])
def test_cliente_inactivo_admin_o_inexistente(database, customer_id):
    with pytest.raises(LookupError):
        ticket(database[0], customer_id=customer_id)


@pytest.mark.parametrize("request_type", ["INFO_QUERY", "REFUND", "WARRANTY_STATUS_CHECK"])
def test_no_persiste_intenciones_como_enum(database, request_type):
    with pytest.raises(ValueError):
        ticket(database[0], request_type=request_type)


def test_inventario_exacto_candidatos_y_sin_stock(database):
    repo, *_ = database
    assert repo.search_inventory(term="SSD-TEST")[0]["id"] == 1
    assert [p["id"] for p in repo.search_inventory(term="prueba", category="SSD")] == [1]
    assert repo.search_inventory(term="%") == []
    assert repo.search_inventory(term="' OR 1=1 --") == []
    assert repo.get_inventory(spare_part_id=99, quantity=1) is None
    assert repo.get_inventory(spare_part_id=3, quantity=1) is None
    assert repo.get_inventory(spare_part_id=2, quantity=1)["available"] is False
    result = repo.get_inventory(spare_part_id=1, quantity=4)
    assert result["unit_price"] == Decimal("180.00") and result["available"] is False


def test_quote_atomica_decimal_reintento_y_ownership(database):
    repo, engine, tickets, parts, quotes, details = database
    row = ticket(repo)
    result = quote(repo, row["id"])
    assert result["status"] == "ACCEPTED" and result["total_amount"] == Decimal("360.00")
    assert quote(repo, row["id"])["id"] == result["id"]
    assert repo.get_ticket(customer_id=1, ticket_id=row["id"])["status"] == "QUOTED"
    assert len(repo.list_quotes(customer_id=1, ticket_id=row["id"])) == 1
    assert repo.get_quote(customer_id=1, quote_id=result["id"])["lines"][0]["subtotal"] == Decimal("360.00")
    with pytest.raises(LookupError):
        repo.get_quote(customer_id=2, quote_id=result["id"])
    with pytest.raises(LookupError):
        repo.list_quotes(customer_id=2, ticket_id=row["id"])
    with pytest.raises(LookupError):
        quote(repo, row["id"], customer_id=2)
    with pytest.raises(RetryConflict):
        quote(repo, row["id"], lines=[dict(spare_part_id=1, quantity=1, unit_price=Decimal("180.00"))])
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(quotes)) == 1
        assert conn.scalar(select(parts.c.current_stock).where(parts.c.id == 1)) == 3


@pytest.mark.parametrize("price", [180.0, "180.00", Decimal("NaN"), Decimal("Infinity"),
                                  Decimal("-1"), Decimal("180.001"), Decimal("100000000")])
def test_importes_invalidos(database, price):
    repo = database[0]
    with pytest.raises(ValueError):
        quote(repo, ticket(repo)["id"], lines=[dict(spare_part_id=1, quantity=1, unit_price=price)])


@pytest.mark.parametrize("line", [
    dict(spare_part_id=1, quantity=4, unit_price=Decimal("180.00")),
    dict(spare_part_id=1, quantity=1, unit_price=Decimal("179.00")),
    dict(spare_part_id=2, quantity=1, unit_price=Decimal("150.00")),
    dict(spare_part_id=3, quantity=1, unit_price=Decimal("180.00")),
    dict(spare_part_id=99, quantity=1, unit_price=Decimal("180.00")),
    dict(spare_part_id=1, quantity=True, unit_price=Decimal("180.00")),
])
def test_revalida_stock_precio_activo_y_cantidades(database, line):
    repo, engine, _, _, quotes, _ = database
    row = ticket(repo)
    with pytest.raises(ValueError):
        quote(repo, row["id"], lines=[line])
    assert repo.get_ticket(customer_id=1, ticket_id=row["id"])["status"] == "NEW"
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(quotes)) == 0


def test_fallo_detalle_revierte_quote_y_ticket(database):
    repo, engine, _, _, quotes, details = database
    row = ticket(repo)
    @event.listens_for(engine, "before_cursor_execute")
    def fail_detail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO quote_details"):
            raise RuntimeError("Fallo de detalle simulado")
    with pytest.raises(RuntimeError):
        quote(repo, row["id"])
    event.remove(engine, "before_cursor_execute", fail_detail)
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(quotes)) == 0
        assert conn.scalar(select(func.count()).select_from(details)) == 0
    assert repo.get_ticket(customer_id=1, ticket_id=row["id"])["status"] == "NEW"
    assert quote(repo, row["id"])["status"] == "ACCEPTED"


def test_fallo_actualizacion_ticket_revierte_detalles(database):
    repo, engine, _, _, quotes, details = database
    row = ticket(repo)
    @event.listens_for(engine, "before_cursor_execute")
    def fail_update(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE tickets"):
            raise RuntimeError("Fallo de actualización simulado")
    with pytest.raises(RuntimeError):
        quote(repo, row["id"])
    event.remove(engine, "before_cursor_execute", fail_update)
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(quotes)) == 0
        assert conn.scalar(select(func.count()).select_from(details)) == 0
    assert repo.get_ticket(customer_id=1, ticket_id=row["id"])["status"] == "NEW"


def test_ticket_cancelado_no_admite_cotizacion(database):
    repo, engine, tickets, *_ = database
    row = ticket(repo)
    with engine.begin() as conn:
        conn.execute(tickets.update().where(tickets.c.id == row["id"]).values(status="CANCELLED"))
    with pytest.raises(ValueError, match="Ticket"):
        quote(repo, row["id"])


def test_no_acepta_articulos_externos_duplicados_o_enum_invalido(database):
    repo = database[0]
    row = ticket(repo)
    line = dict(spare_part_id=1, quantity=1, unit_price=Decimal("180.00"))
    with pytest.raises(ValueError, match="externo"):
        quote(repo, row["id"], lines=[{**line, "custom_item_name": "Otro artículo"}])
    with pytest.raises(ValueError, match="duplicado"):
        quote(repo, row["id"], lines=[line, line])
    with pytest.raises(ValueError, match="quote_type"):
        quote(repo, row["id"], quote_type="SALE")


def test_aceptacion_tipo_y_servicio_sin_piezas(database):
    repo = database[0]
    row = ticket(repo, request_type="SUPPORT")
    with pytest.raises(ValueError):
        quote(repo, row["id"], explicitly_accepted=False)
    with pytest.raises(ValueError):
        quote(repo, row["id"])
    result = quote(repo, row["id"], quote_type="REPAIR", labor_cost=Decimal("35.00"), lines=[])
    assert result["total_amount"] == Decimal("35.00")
    assert quote(repo, row["id"], quote_type="REPAIR", labor_cost=Decimal("35.00"), lines=[])["id"] == result["id"]


def test_sql_postgres_usa_bloqueos_en_escrituras(database):
    repo, engine, *_ = database
    statements = []
    @event.listens_for(engine, "before_execute")
    def capture(conn, clause, multiparams, params, execution_options):
        if getattr(clause, "_for_update_arg", None) is not None:
            statements.append(str(clause.compile(dialect=postgresql.dialect())))
    quote(repo, ticket(repo)["id"])
    assert any("FROM users" in sql and "FOR UPDATE" in sql for sql in statements)
    assert any("FROM tickets" in sql and "FOR UPDATE" in sql for sql in statements)
    assert any("FROM spare_parts" in sql and "FOR UPDATE" in sql for sql in statements)


def test_calculo_independiente_de_precision_decimal_global(database):
    repo = database[0]
    row = ticket(repo)
    with localcontext() as context:
        context.prec = 3
        result = quote(repo, row["id"], quote_type="DIRECT_SALE")
    assert result["total_amount"] == Decimal("360.00")


def test_subtotal_aportado_debe_coincidir_con_propuesta(database):
    repo = database[0]
    with pytest.raises(ValueError, match="Subtotal"):
        quote(repo, ticket(repo)["id"], lines=[dict(
            spare_part_id=1, quantity=2, unit_price=Decimal("180.00"), subtotal=Decimal("180.00"))])


def test_reintento_no_ignora_nombre_externo_persistido(database):
    repo, engine, _, _, _, details = database
    row = ticket(repo)
    saved = quote(repo, row["id"])
    with engine.begin() as conn:
        conn.execute(details.update().where(details.c.quote_id == saved["id"]).values(
            custom_item_name="Artículo externo diferente"))
    with pytest.raises(RetryConflict):
        quote(repo, row["id"])


def test_cantidad_fuera_de_integer_postgres(database):
    repo = database[0]
    with pytest.raises(ValueError, match="Cantidad"):
        repo.get_inventory(spare_part_id=1, quantity=2147483648)


@pytest.mark.parametrize("accepted", [False, None, 1, "True"])
def test_aceptacion_requiere_booleano_true(database, accepted):
    repo = database[0]
    with pytest.raises(ValueError, match="aceptación"):
        quote(repo, ticket(repo)["id"], explicitly_accepted=accepted)


def test_colision_unique_durante_insert_ticket_usa_savepoint(database):
    repo, engine, tickets, *_ = database
    injected = []
    # Simula otra inserción entre lectura inicial e INSERT; no es una prueba
    # de concurrencia PostgreSQL, sí del camino de recuperación de UNIQUE(code).
    @event.listens_for(engine, "after_cursor_execute")
    def collide(conn, cursor, statement, parameters, context, executemany):
        if "WHERE tickets.code =" in statement and not injected:
            injected.append(True)
            conn.execute(tickets.insert().values(
                customer_id=1, code="TCK-TEST", title="Venta de prueba",
                failure_description="SSD de prueba", request_type="SALE",
                status="NEW", diagnosis_type="NONE", is_remote_service=False))
    result = ticket(repo)
    event.remove(engine, "after_cursor_execute", collide)
    assert injected and result["code"] == "TCK-TEST"
    assert len(repo.list_tickets(customer_id=1)) == 1


def test_reintento_con_precio_actual_distinto_no_reescribe_quote(database):
    repo, engine, _, parts, *_ = database
    row = ticket(repo)
    saved = quote(repo, row["id"])
    with engine.begin() as conn:
        conn.execute(parts.update().where(parts.c.id == 1).values(
            unit_price=Decimal("150.00"), current_stock=0))
    # Repetir una operación ya confirmada devuelve la cotización histórica,
    # sin recalcularla ni afirmar disponibilidad actual.
    assert quote(repo, row["id"])["id"] == saved["id"]
    assert repo.get_quote(customer_id=1, quote_id=saved["id"])["total_amount"] == Decimal("360.00")


def test_importe_maximo_y_limite_bigint(database):
    repo = database[0]
    row = ticket(repo, request_type="SUPPORT")
    result = quote(repo, row["id"], quote_type="REPAIR", lines=[],
                   labor_cost=Decimal("99999999.99"))
    assert result["total_amount"] == Decimal("99999999.99")
    with pytest.raises(ValueError, match="Identificador"):
        repo.get_ticket(customer_id=1, ticket_id=9223372036854775808)

from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import sessionmaker

from app.adapters.persistence.accounting import AccountingRepositoryAdapter


def _new_test_user(connection):
    suffix = uuid4().hex
    return connection.execute(text("""INSERT INTO users
        (email, phone, password_hash, name, role, active)
        VALUES (:email, :phone, 'test-only-hash', 'Accounting Test', CAST('ADMIN' AS user_role_enum), TRUE)
        RETURNING id"""),
        {"email": f"accounting-{suffix}@test.invalid", "phone": f"+519{suffix[:9]}"}).scalar_one()


def _new_test_entry(connection, actor_id, *, debit="100.00", credit="100.00", concept="Prueba contable", detail="Solo prueba transaccional"):
    category_id = connection.execute(text("SELECT id FROM accounting_categories WHERE code = 'SALE'")).scalar_one()
    entry_id = connection.execute(text("""INSERT INTO accounting_entries
        (operation_date, concept, detail, category_id, currency, debit_total, credit_total,
         status, responsible_user_id)
        VALUES ('2026-11-02', :concept, :detail, :category,
                'PEN', :debit, :credit, 'CONFIRMED', :actor) RETURNING id"""),
        {"category": category_id, "debit": debit, "credit": credit, "actor": actor_id,
         "concept": concept, "detail": detail}).scalar_one()
    connection.execute(text("""INSERT INTO accounting_entry_lines
        (entry_id, line_number, account_code, account_name, debit, credit)
        VALUES (:entry, 1, '101', 'Debe', 100.00, 0.00),
               (:entry, 2, '701', 'Haber', 0.00, 100.00)"""), {"entry": entry_id})
    connection.execute(text("""INSERT INTO accounting_audit_events
        (entry_id, actor_user_id, event_type) VALUES (:entry, :actor, 'ENTRY_CREATED')"""),
        {"entry": entry_id, "actor": actor_id})
    return int(entry_id), int(category_id)


def test_accounting_migration_tables_constraints_and_deferred_triggers(accounting_test_engine):
    with accounting_test_engine.connect() as connection:
        tables = connection.execute(text("""SELECT to_regclass('accounting_categories'),
            to_regclass('accounting_entries'), to_regclass('accounting_entry_lines'),
            to_regclass('accounting_audit_events')""")).one()
        assert all(tables)
        constraints = connection.execute(text("""SELECT conname FROM pg_constraint
            WHERE conname IN ('accounting_entry_line_one_side','accounting_entry_not_self_reversal',
                              'accounting_entry_reversed_timestamp')""")).scalars().all()
        assert set(constraints) == {"accounting_entry_line_one_side", "accounting_entry_not_self_reversal", "accounting_entry_reversed_timestamp"}
        foreign_keys = connection.execute(text("""SELECT child.relname, parent.relname
            FROM pg_constraint constraint_row
            JOIN pg_class child ON child.oid = constraint_row.conrelid
            JOIN pg_class parent ON parent.oid = constraint_row.confrelid
            WHERE constraint_row.contype = 'f' AND child.relname LIKE 'accounting_%'""")).all()
        assert ("accounting_entries", "users") in foreign_keys
        assert ("accounting_entries", "accounting_categories") in foreign_keys
        assert ("accounting_entry_lines", "accounting_entries") in foreign_keys
        unique_indexes = connection.execute(text("""SELECT indexname FROM pg_indexes
            WHERE tablename = 'accounting_entries' AND indexdef LIKE 'CREATE UNIQUE INDEX%'""")).scalars().all()
        assert any("entry_number" in name for name in unique_indexes)
        assert any("reversal_of_entry_id" in name for name in unique_indexes)
        triggers = connection.execute(text("""SELECT tgname FROM pg_trigger
            WHERE tgname IN ('accounting_balance_after_entry','accounting_balance_after_line') AND NOT tgisinternal""")).scalars().all()
        assert set(triggers) == {"accounting_balance_after_entry", "accounting_balance_after_line"}


def test_deferred_trigger_rejects_unbalanced_entry_and_rolls_back_everything(accounting_test_engine):
    email = f"accounting-{uuid4().hex}@test.invalid"
    with accounting_test_engine.connect() as connection:
        transaction = connection.begin()
        actor_id = connection.execute(text("""INSERT INTO users
            (email, phone, password_hash, name, role, active)
            VALUES (:email, :phone, 'test-only-hash', 'Accounting Test', CAST('ADMIN' AS user_role_enum), TRUE)
            RETURNING id"""), {"email": email, "phone": f"+519{uuid4().hex[:9]}"}).scalar_one()
        category = connection.execute(text("SELECT id FROM accounting_categories WHERE code = 'SALE'")).scalar_one()
        entry_id = connection.execute(text("""INSERT INTO accounting_entries
            (operation_date, concept, detail, category_id, currency, debit_total, credit_total,
             status, responsible_user_id)
            VALUES ('2026-11-02', 'Desbalanceado', 'Debe abortar', :category,
                    'PEN', 100.00, 99.00, 'CONFIRMED', :actor) RETURNING id"""),
            {"category": category, "actor": actor_id}).scalar_one()
        connection.execute(text("""INSERT INTO accounting_entry_lines
            (entry_id, line_number, account_code, account_name, debit, credit)
            VALUES (:entry, 1, '101', 'Debe', 100.00, 0.00),
                   (:entry, 2, '701', 'Haber', 0.00, 99.00)"""), {"entry": entry_id})
        with pytest.raises(DBAPIError):
            connection.execute(text("SET CONSTRAINTS accounting_balance_after_entry, accounting_balance_after_line IMMEDIATE"))
        transaction.rollback()
    with accounting_test_engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM users WHERE email = :email"), {"email": email}).scalar_one() == 0


def test_reversal_is_atomic_and_original_remains_auditable(accounting_test_engine):
    email = f"accounting-{uuid4().hex}@test.invalid"
    with accounting_test_engine.connect() as connection:
        transaction = connection.begin()
        actor_id = connection.execute(text("""INSERT INTO users
            (email, phone, password_hash, name, role, active)
            VALUES (:email, :phone, 'test-only-hash', 'Accounting Test', CAST('ADMIN' AS user_role_enum), TRUE)
            RETURNING id"""), {"email": email, "phone": f"+519{uuid4().hex[:9]}"}).scalar_one()
        original_id, category_id = _new_test_entry(connection, actor_id)
        reversal_id = connection.execute(text("""INSERT INTO accounting_entries
            (operation_date, concept, detail, category_id, currency, debit_total, credit_total,
             status, responsible_user_id, reversal_of_entry_id, reversal_reason)
            VALUES ('2026-11-03', 'Prueba contable', 'Solo prueba transaccional', :category,
                    'PEN', 100.00, 100.00, 'CONFIRMED', :actor, :original, 'Corrección de prueba')
            RETURNING id"""), {"category": category_id, "actor": actor_id, "original": original_id}).scalar_one()
        connection.execute(text("""INSERT INTO accounting_entry_lines
            (entry_id, line_number, account_code, account_name, debit, credit)
            VALUES (:entry, 1, '101', 'Debe', 0.00, 100.00),
                   (:entry, 2, '701', 'Haber', 100.00, 0.00)"""), {"entry": reversal_id})
        connection.execute(text("""INSERT INTO accounting_audit_events
            (entry_id, actor_user_id, event_type, related_entry_id, reason)
            VALUES (:original, :actor, 'ENTRY_REVERSED', :reversal, 'Corrección de prueba'),
                   (:reversal, :actor, 'REVERSAL_CREATED', :original, 'Corrección de prueba')"""),
            {"original": original_id, "reversal": reversal_id, "actor": actor_id})
        connection.execute(text("UPDATE accounting_entries SET status = 'REVERSED', reversed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = :id"), {"id": original_id})
        connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        original = connection.execute(text("SELECT status FROM accounting_entries WHERE id = :id"), {"id": original_id}).scalar_one()
        event_count = connection.execute(text("SELECT count(*) FROM accounting_audit_events WHERE entry_id = :id"), {"id": original_id}).scalar_one()
        assert original == "REVERSED" and event_count == 2
        with pytest.raises(IntegrityError):
            connection.execute(text("""INSERT INTO accounting_entries
                (operation_date, concept, detail, category_id, currency, debit_total, credit_total,
                 status, responsible_user_id, reversal_of_entry_id, reversal_reason)
                VALUES ('2026-11-03', 'Duplicada', 'Debe fallar', :category, 'PEN', 100, 100,
                        'CONFIRMED', :actor, :original, 'Segunda reversión')"""),
                {"category": category_id, "actor": actor_id, "original": original_id})
        transaction.rollback()
    with accounting_test_engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM users WHERE email = :email"), {"email": email}).scalar_one() == 0


def test_concurrent_reversal_creates_one_compensating_entry(accounting_test_engine):
    with accounting_test_engine.begin() as connection:
        actor_id = connection.execute(text("""SELECT id FROM users
            WHERE role::text = 'ADMIN' AND active IS TRUE ORDER BY id LIMIT 1""")).scalar_one_or_none()
        if actor_id is None:
            actor_id = _new_test_user(connection)
        original_id, _category_id = _new_test_entry(
            connection, actor_id, concept="[TEST] Concurrent reversal", detail="Synthetic integration fixture"
        )

    repository = AccountingRepositoryAdapter(
        sessionmaker(bind=accounting_test_engine, autoflush=False, expire_on_commit=False)
    )
    start = Barrier(2)

    def reverse_once():
        start.wait(timeout=10)
        return repository.reverse_entry(
            int(actor_id), original_id, date(2026, 11, 4), "Prueba de concurrencia automatizada"
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(reverse_once) for _ in range(2)]
        outcomes = [future.result(timeout=30) for future in results]

    assert sorted(replayed for _result, replayed in outcomes) == [False, True]
    reversal_ids = {outcome["reversal"]["id"] for outcome, _replayed in outcomes}
    assert len(reversal_ids) == 1
    with accounting_test_engine.connect() as connection:
        assert connection.execute(text("SELECT status FROM accounting_entries WHERE id = :id"), {"id": original_id}).scalar_one() == "REVERSED"
        assert connection.execute(text("SELECT count(*) FROM accounting_entries WHERE reversal_of_entry_id = :id"), {"id": original_id}).scalar_one() == 1
    # El usuario de prueba queda inactivo; la FK de auditoría conserva la evidencia.
    with accounting_test_engine.begin() as connection:
        connection.execute(text("UPDATE users SET active = FALSE WHERE id = :id"), {"id": actor_id})

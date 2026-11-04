-- Restore the accounting immutability guards after the explicitly approved test cleanup.
BEGIN;

DO $$
DECLARE
    found_count INTEGER;
BEGIN
    IF current_database() <> 'multiagentedb' THEN
        RAISE EXCEPTION 'Expected local test database multiagentedb; no trigger changed';
    END IF;

    SELECT count(*) INTO found_count
    FROM pg_trigger t
    JOIN pg_class c ON c.oid=t.tgrelid
    JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='public' AND NOT t.tgisinternal
      AND t.tgenabled='D'
      AND (c.relname,t.tgname) IN (
        ('accounting_entries','accounting_entries_immutable'),
        ('accounting_entry_lines','accounting_lines_immutable'),
        ('accounting_audit_events','accounting_audit_append_only')
      );

    IF found_count <> 3 THEN
        RAISE EXCEPTION 'Expected all three temporary accounting guards disabled; no trigger changed';
    END IF;
END $$;

ALTER TABLE public.accounting_entries ENABLE TRIGGER accounting_entries_immutable;
ALTER TABLE public.accounting_entry_lines ENABLE TRIGGER accounting_lines_immutable;
ALTER TABLE public.accounting_audit_events ENABLE TRIGGER accounting_audit_append_only;

COMMIT;

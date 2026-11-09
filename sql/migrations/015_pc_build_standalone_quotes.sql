-- PC_BUILD is a commercial quote; it must not require a service ticket.
-- Preserve quote, payment, order, line and audit identifiers. Historical ticket
-- rows remain intact; their relationship is detached from PC_BUILD commerce.
BEGIN;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
    WHERE n.nspname='public' AND t.typname='quote_type_enum'
      AND EXISTS (SELECT 1 FROM pg_enum e WHERE e.enumtypid=t.oid AND e.enumlabel='PC_BUILD')
  ) THEN
    RAISE EXCEPTION 'quote_type_enum must contain PC_BUILD before this migration';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='quotes' AND column_name='ticket_id'
  ) THEN
    RAISE EXCEPTION 'public.quotes.ticket_id is required';
  END IF;
END $$;

-- Existing PC_BUILD quotes and their payments keep all commercial data and
-- audit history. Only the invalid service-ticket links are removed.
UPDATE public.payments p
SET ticket_id = NULL
FROM public.quotes q
WHERE p.quote_id=q.id AND q.quote_type='PC_BUILD' AND q.ticket_id IS NOT NULL;

UPDATE public.quotes
SET ticket_id=NULL, updated_at=CURRENT_TIMESTAMP
WHERE quote_type='PC_BUILD' AND ticket_id IS NOT NULL;

ALTER TABLE public.quotes DROP CONSTRAINT IF EXISTS chk_quotes_ticket_kind;
ALTER TABLE public.quotes ADD CONSTRAINT chk_quotes_ticket_kind CHECK (
    (quote_type IN ('DIRECT_SALE','PC_BUILD') AND ticket_id IS NULL)
    OR (quote_type='REPAIR' AND ticket_id IS NOT NULL)
);

COMMIT;

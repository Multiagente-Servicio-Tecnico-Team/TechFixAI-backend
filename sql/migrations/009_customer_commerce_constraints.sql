-- Constraints are applied only after 008, issue resolution, fixture cleanup,
-- and pre/post row-count validation on an isolated restored database.
BEGIN;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM public.customer_commerce_migration_issues WHERE resolved_at IS NULL) THEN
    RAISE EXCEPTION 'customer-commerce backfill has unresolved migration issues';
  END IF;
  IF EXISTS (SELECT 1 FROM public.tickets WHERE commercial_customer_id IS NULL) THEN
    RAISE EXCEPTION 'tickets without commercial_customer_id remain';
  END IF;
  IF EXISTS (SELECT 1 FROM public.quotes WHERE customer_id IS NULL) THEN
    RAISE EXCEPTION 'quotes without customer_id remain';
  END IF;
  IF EXISTS (SELECT 1 FROM public.payments WHERE commercial_customer_id IS NULL) THEN
    RAISE EXCEPTION 'payments without commercial_customer_id remain';
  END IF;
  IF EXISTS (SELECT 1 FROM public.quotes q JOIN public.tickets t ON t.id=q.ticket_id
             WHERE q.ticket_id IS NOT NULL AND q.customer_id<>t.commercial_customer_id) THEN
    RAISE EXCEPTION 'service quote customer differs from ticket customer';
  END IF;
  IF EXISTS (SELECT 1 FROM public.quotes WHERE quote_type='DIRECT_SALE' AND ticket_id IS NOT NULL) THEN
    RAISE EXCEPTION 'ticket-linked DIRECT_SALE quotations remain; clean only the separately verified fixture first';
  END IF;
  IF EXISTS (SELECT 1 FROM public.quotes WHERE quote_type<>'DIRECT_SALE' AND ticket_id IS NULL) THEN
    RAISE EXCEPTION 'service quotation without ticket remains';
  END IF;
END $$;

ALTER TABLE public.tickets ALTER COLUMN commercial_customer_id SET NOT NULL;
ALTER TABLE public.quotes ALTER COLUMN customer_id SET NOT NULL;
ALTER TABLE public.payments ALTER COLUMN commercial_customer_id SET NOT NULL;

DO $$ BEGIN
  ALTER TABLE public.tickets ADD CONSTRAINT uq_tickets_id_commercial_customer
    UNIQUE (id, commercial_customer_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE public.quotes ADD CONSTRAINT uq_quotes_id_customer
    UNIQUE (id, customer_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE public.quotes ADD CONSTRAINT fk_quotes_ticket_customer
    FOREIGN KEY (ticket_id, customer_id)
    REFERENCES public.tickets(id, commercial_customer_id) ON DELETE RESTRICT;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE public.quotes ADD CONSTRAINT chk_quotes_ticket_kind
    CHECK ((quote_type='DIRECT_SALE' AND ticket_id IS NULL)
        OR (quote_type<>'DIRECT_SALE' AND ticket_id IS NOT NULL));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE public.payments ADD CONSTRAINT fk_payments_quote_customer
    FOREIGN KEY (quote_id, commercial_customer_id)
    REFERENCES public.quotes(id, customer_id) ON DELETE RESTRICT;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS ix_payments_customer_status_created
    ON public.payments (commercial_customer_id, status, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS ix_quotes_customer_status_created
    ON public.quotes (customer_id, status, created_at DESC, id DESC);

COMMIT;

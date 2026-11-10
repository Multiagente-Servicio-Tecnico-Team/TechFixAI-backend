-- Allow the ticket audit event written when a customer accepts a service quote.
-- The old CHECK constraint made accept_ticket_quote() roll back its whole transaction.
BEGIN;

ALTER TABLE public.ticket_audit_events
    DROP CONSTRAINT IF EXISTS ticket_audit_events_event_type_check;

ALTER TABLE public.ticket_audit_events
    ADD CONSTRAINT ticket_audit_events_event_type_check
    CHECK (event_type IN (
        'CREATED',
        'UPDATED',
        'STATUS_CHANGED',
        'CANCELLED',
        'QUOTE_CREATED',
        'QUOTE_ACCEPTED'
    ));

COMMIT;

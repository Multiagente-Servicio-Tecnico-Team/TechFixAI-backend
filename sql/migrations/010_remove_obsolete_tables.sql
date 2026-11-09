-- Limpia auxiliares de backfill completado y la tabla de notificaciones sin consumidor.
-- Requiere 009 registrada, incidencias resueltas y respaldo restaurable.
BEGIN;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM public.schema_migrations WHERE version = '009') THEN
    RAISE EXCEPTION 'La migración 009 no está registrada; no se puede limpiar el backfill';
  END IF;

  IF EXISTS (
    SELECT 1 FROM public.customer_commerce_migration_issues WHERE resolved_at IS NULL
  ) THEN
    RAISE EXCEPTION 'Hay incidencias de migración comercial abiertas';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.customer_commerce_migration_map m
    WHERE (m.source_entity = 'users' AND NOT EXISTS (
             SELECT 1 FROM public.customers c
             WHERE c.id = m.customer_id AND c.user_id = m.source_id))
       OR (m.source_entity = 'manual_ticket' AND NOT EXISTS (
             SELECT 1 FROM public.tickets t
             WHERE t.id = m.source_id AND t.commercial_customer_id = m.customer_id))
       OR m.source_entity NOT IN ('users', 'manual_ticket')
  ) THEN
    RAISE EXCEPTION 'El mapa de backfill contiene vínculos no reconciliables';
  END IF;

  IF EXISTS (SELECT 1 FROM public.notification_history) THEN
    RAISE EXCEPTION 'notification_history contiene filas; debe revisarse antes de eliminarla';
  END IF;
END $$;

DROP TABLE public.customer_commerce_migration_issues;
DROP TABLE public.customer_commerce_migration_map;
DROP TABLE public.notification_history;

COMMIT;

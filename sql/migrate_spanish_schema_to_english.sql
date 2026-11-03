-- Rename the existing public-schema objects in place.
-- Existing rows, identities, constraints, indexes and foreign keys are preserved.
-- Requires Spanish source tables and must not be run if English tables already exist.
-- Run with psql -v ON_ERROR_STOP=1 -f sql/migrate_spanish_schema_to_english.sql
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

ALTER TYPE public.rol_usuario_enum RENAME VALUE 'CLIENTE' TO 'CUSTOMER';
ALTER TYPE public.rol_usuario_enum RENAME VALUE 'TECNICO' TO 'TECHNICIAN';
ALTER TYPE public.tipo_solicitud_enum RENAME VALUE 'REPARACION' TO 'REPAIR';
ALTER TYPE public.tipo_solicitud_enum RENAME VALUE 'VENTA' TO 'SALE';
ALTER TYPE public.tipo_solicitud_enum RENAME VALUE 'SOPORTE' TO 'SUPPORT';
ALTER TYPE public.estado_ticket_enum RENAME VALUE 'NUEVO' TO 'NEW';
ALTER TYPE public.estado_ticket_enum RENAME VALUE 'EN_DIAGNOSTICO' TO 'IN_DIAGNOSIS';
ALTER TYPE public.estado_ticket_enum RENAME VALUE 'PRESUPUESTADO' TO 'QUOTED';
ALTER TYPE public.estado_ticket_enum RENAME VALUE 'EN_REPARACION' TO 'IN_REPAIR';
ALTER TYPE public.estado_ticket_enum RENAME VALUE 'LISTO_PARA_RETIRO'
    TO 'READY_FOR_PICKUP';
ALTER TYPE public.estado_ticket_enum RENAME VALUE 'ENTREGADO' TO 'DELIVERED';
ALTER TYPE public.estado_ticket_enum RENAME VALUE 'CANCELADO' TO 'CANCELLED';
ALTER TYPE public.estado_presupuesto_enum RENAME VALUE 'PENDIENTE' TO 'PENDING';
ALTER TYPE public.estado_presupuesto_enum RENAME VALUE 'ACEPTADO' TO 'ACCEPTED';
ALTER TYPE public.estado_presupuesto_enum RENAME VALUE 'RECHAZADO' TO 'REJECTED';
ALTER TYPE public.tipo_notificacion_enum RENAME VALUE 'CONFIRMACION_PRESUPUESTO'
    TO 'QUOTE_CONFIRMATION';
ALTER TYPE public.tipo_notificacion_enum RENAME VALUE 'AVISO_RETIRO'
    TO 'PICKUP_NOTICE';
ALTER TYPE public.tipo_notificacion_enum RENAME VALUE 'CAMBIO_ESTADO'
    TO 'STATUS_CHANGE';

ALTER TYPE public.rol_usuario_enum RENAME TO user_role_enum;
ALTER TYPE public.tipo_solicitud_enum RENAME TO request_type_enum;
ALTER TYPE public.estado_ticket_enum RENAME TO ticket_status_enum;
ALTER TYPE public.estado_presupuesto_enum RENAME TO quote_status_enum;
ALTER TYPE public.tipo_notificacion_enum RENAME TO notification_type_enum;

ALTER TABLE public.usuarios RENAME TO users;
ALTER TABLE public.users RENAME COLUMN telefono TO phone;
ALTER TABLE public.users RENAME COLUMN nombre TO name;
ALTER TABLE public.users RENAME COLUMN apellido TO last_name;
ALTER TABLE public.users RENAME COLUMN rol TO role;
ALTER TABLE public.users RENAME COLUMN activo TO active;

ALTER TABLE public.tokens_recuperacion RENAME TO recovery_tokens;
ALTER TABLE public.recovery_tokens RENAME COLUMN usuario_id TO user_id;
ALTER TABLE public.recovery_tokens RENAME COLUMN expira_en TO expires_at;
ALTER TABLE public.recovery_tokens RENAME COLUMN usado TO used;

ALTER TABLE public.repuestos RENAME TO spare_parts;
ALTER TABLE public.spare_parts RENAME COLUMN codigo TO code;
ALTER TABLE public.spare_parts RENAME COLUMN nombre TO name;
ALTER TABLE public.spare_parts RENAME COLUMN descripcion TO description;
ALTER TABLE public.spare_parts RENAME COLUMN precio_unitario TO unit_price;
ALTER TABLE public.spare_parts RENAME COLUMN stock_actual TO current_stock;
ALTER TABLE public.spare_parts RENAME COLUMN umbral_minimo TO minimum_threshold;
ALTER TABLE public.spare_parts RENAME COLUMN activo TO active;

ALTER TABLE public.tickets RENAME COLUMN codigo TO code;
ALTER TABLE public.tickets RENAME COLUMN cliente_id TO customer_id;
ALTER TABLE public.tickets RENAME COLUMN tecnico_id TO technician_id;
ALTER TABLE public.tickets RENAME COLUMN titulo TO title;
ALTER TABLE public.tickets RENAME COLUMN descripcion_falla TO failure_description;
ALTER TABLE public.tickets RENAME COLUMN tipo_solicitud TO request_type;
ALTER TABLE public.tickets RENAME COLUMN estado TO status;
ALTER TABLE public.tickets RENAME COLUMN diagnostico_provisional
    TO provisional_diagnosis;

ALTER TABLE public.presupuestos RENAME TO quotes;
ALTER TABLE public.quotes RENAME COLUMN costo_mano_obra TO labor_cost;
ALTER TABLE public.quotes RENAME COLUMN costo_repuestos TO parts_cost;
ALTER TABLE public.quotes RENAME COLUMN monto_total TO total_amount;
ALTER TABLE public.quotes RENAME COLUMN estado TO status;
ALTER TABLE public.quotes RENAME COLUMN observaciones TO observations;

ALTER TABLE public.detalles_presupuesto RENAME TO quote_details;
ALTER TABLE public.quote_details RENAME COLUMN presupuesto_id TO quote_id;
ALTER TABLE public.quote_details RENAME COLUMN repuesto_id TO spare_part_id;
ALTER TABLE public.quote_details RENAME COLUMN cantidad TO quantity;
ALTER TABLE public.quote_details RENAME COLUMN precio_unitario TO unit_price;

ALTER TABLE public.historial_notificaciones RENAME TO notification_history;
ALTER TABLE public.notification_history RENAME COLUMN usuario_id TO user_id;
ALTER TABLE public.notification_history RENAME COLUMN tipo_evento TO event_type;
ALTER TABLE public.notification_history RENAME COLUMN destinatario TO recipient;
ALTER TABLE public.notification_history RENAME COLUMN enviado_exitosamente
    TO sent_successfully;
ALTER TABLE public.notification_history RENAME COLUMN error_mensaje
    TO error_message;
ALTER TABLE public.notification_history RENAME COLUMN fecha_envio TO sent_at;

ALTER SEQUENCE public.usuarios_id_seq RENAME TO users_id_seq;
ALTER SEQUENCE public.tokens_recuperacion_id_seq RENAME TO recovery_tokens_id_seq;
ALTER SEQUENCE public.repuestos_id_seq RENAME TO spare_parts_id_seq;
ALTER SEQUENCE public.presupuestos_id_seq RENAME TO quotes_id_seq;
ALTER SEQUENCE public.detalles_presupuesto_id_seq RENAME TO quote_details_id_seq;
ALTER SEQUENCE public.historial_notificaciones_id_seq
    RENAME TO notification_history_id_seq;

COMMIT;

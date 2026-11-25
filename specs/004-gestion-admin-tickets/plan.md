# Implementation Plan: Gestión administrativa de tickets

**Branch**: `004-gestion-admin-tickets` | **Date**: 2026-11-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-gestion-admin-tickets/spec.md`

## Summary

Completar la gestión de tickets de ADMIN que alimentará el tablero y formulario de taller: extender la persistencia para origen manual/en línea, contacto presencial, adelanto y auditoría; ajustar lista, detalle, alta, edición y baja a los contratos aclarados; mantener el tipo y estado canónicos en backend; permitir una cotización pendiente posterior ligada al ticket y calculada con datos autorizados. La migración será SQL aditiva y versionada. Los tickets online seguirán ligados a la cuenta autenticada; los manuales podrán existir sin usuario.

La API administrativa no implementará el frontend. El formulario `NewTicket.jsx` todavía usa estado local; su conexión se pedirá por separado en el repositorio frontend.

## Technical Context

**Language/Version**: Python 3.12, versión documentada por el backend  
**Primary Dependencies**: FastAPI, Pydantic 2, SQLAlchemy 2, PostgreSQL/pg8000; no se agrega dependencia  
**Storage**: PostgreSQL con esquema ampliado v2 y migración `sql/migrations/004_admin_ticket_management.sql`  
**Testing**: pytest; pruebas unitarias, contract, integración HTTP y PostgreSQL aislado  
**Target Platform**: API HTTP existente de TechFix.AI (desarrollo local y despliegues actuales)  
**Project Type**: Backend web en capas domain/application/adapters/infrastructure  
**Performance Goals**: Sin SLA nuevo. Lista paginada, 50 por defecto y máximo 200; medir solo para evitar regresión en la consulta actual  
**Constraints**: Solo ADMIN opera `/api/admin`; identidad online viene de sesión, no del request; importes en Decimal/NUMERIC; no crear usuarios ficticios; no inferir pagos confirmados; no borrar tickets por cascada; migrar solo una BD de prueba autorizada  
**Scale/Scope**: Capacidad administrativa de tickets del taller; conservar consultas del portal cliente; contrato backend solamente; cinco request types y diez estados actuales; sin administración de clientes, diseño del frontend ni facturación/POS nueva

## Constitution Check

### Gate previo a investigación

- **Reglas de negocio compartidas**: PASS. Categorías/tipos, estado, importe, quote y errores se validan en capacidades backend; no se delega al LLM.
- **Persistencia autorizada**: PASS. Las rutas administrativas requieren la sesión ADMIN verificada. Las rutas online derivan `customer_id` de la sesión del cliente.
- **Exactitud financiera**: PASS. `advance_amount` usa NUMERIC/Decimal y se mantiene distinto de `quotes.total_amount`; el endpoint de quote calcula el total desde mano de obra y catálogo y no genera pago por inferencia.
- **Evidencia y privacidad**: PASS. Se registran actores/fechas sin incluir cookie, credenciales, payload de contacto ni texto de excepciones en auditoría/trazas.
- **Seguridad**: PASS. ADMIN es obligatorio en administración; el portal filtra por usuario autenticado; MANUAL no necesita usuario ni credenciales ficticias.
- **Cambio trazable de esquema**: PASS. Migración 004 aditiva, versionada; filas históricas mantienen origen desconocido; no se ejecuta durante planificación.
- **Pruebas**: PASS. Contratos y pruebas de equivalencia de lecturas para admin/portal; integración de migración y restricciones en PostgreSQL aislado.

### Gate posterior al diseño

- **Diseño consistente con la constitución**: PASS. No se agregan tecnologías; escritura de ticket/auditoría/quote transaccional; cancelación conserva dependencias; cambios SQL solo tras revisión de destino de prueba.
- **Excepciones**: Ninguna. El origen histórico nullable se limita a filas ya existentes cuya procedencia no puede reconstruirse con la tabla actual.

## Research Summary

Las decisiones y alternativas están en [research.md](research.md). El modelo de migración y relaciones está en [data-model.md](data-model.md). Los contratos de lista, detalle, alta manual, edición, cancelación por estado y creación posterior de cotización están en [contracts/admin-tickets.openapi.yaml](contracts/admin-tickets.openapi.yaml). Los escenarios de validación están en [quickstart.md](quickstart.md).

## Project Structure

### Documentation (this feature)

```text
specs/004-gestion-admin-tickets/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/admin-tickets.openapi.yaml
├── checklists/requirements.md
└── tasks.md                         # generado por speckit-tasks
```

### Source Code (repository root)

```text
app/
├── adapters/api/admin_tickets.py               # ampliar rutas/DTO ADMIN
├── adapters/persistence/admin_tickets.py       # persistencia para tickets administrativos y quote draft
├── application/admin_tickets.py                # casos de uso de lista, alta, edición, cancelación y cotización
├── application/ports.py                        # puerto de persistencia administrativa
├── database/repository.py                      # conservar operaciones usadas por chat y portal
├── accounts/session.py                         # reusar require_admin/actor de sesión; sin cambio de auth esperado
└── infrastructure/chat_app.py                 # componer casos de uso/router; habilitar PATCH en CORS
sql/migrations/
└── 004_admin_ticket_management.sql             # migración aditiva; no aplicar en planning
tests/
├── contract/test_admin_ticket_list_contract.py
├── contract/test_admin_ticket_create_contract.py
├── contract/test_admin_ticket_quote_contract.py
├── contract/test_admin_ticket_detail_contract.py
├── unit/domain/test_ticket_management.py
├── unit/application/test_admin_ticket_quotes.py
├── integration/test_admin_ticket_list_api.py
├── integration/test_admin_ticket_create_api.py
├── integration/test_admin_ticket_update_api.py
├── integration/test_admin_ticket_audit_api.py
└── integration/test_admin_ticket_migration_postgres.py
```

**Structure Decision**: Extender el backend monolítico existente. Mantener rutas FastAPI bajo el adaptador de API y mover reglas de creación/cancelación/quote a aplicación; adaptar la persistencia actual sin modificar el flujo independiente del chat. El router se seguirá componiendo desde `app/infrastructure/chat_app.py`.

## Design Decisions

1. **Migración**: añadir `origin`, contacto snapshot manual, adelanto/método y `ticket_audit_events`; permitir `customer_id NULL` solo en tickets MANUAL. No cambiar `request_type_enum`, `quotes` ni `payments` salvo que revisión de constraints en la BD de prueba revele drift.
2. **Origen histórico**: dejar `origin=NULL` solo para filas previas; las nuevas escrituras exigen `MANUAL` o `ONLINE`. No asumir origen a partir del hecho de tener cuenta.
3. **Consultas**: sustituir INNER JOIN a users por LEFT JOIN, resolver datos del cliente según origen y aplicar filtro/búsqueda sobre código, contacto, título y detalle. Devolver `total` y orden determinista.
4. **Create manual**: actor ADMIN se deriva de sesión; asignar `origin=MANUAL`; tomar contacto del body; no crear usuario. Tipo, estado inicial y validaciones usan enumeraciones vigentes.
5. **Create online**: conservar la identidad y el comportamiento de `create_intake_ticket`; asignar `origin=ONLINE` y evento inicial en la misma transacción.
6. **Update/cancel**: cada actualización crea evento. El estado admite cualquiera de los diez códigos backend; el borrado físico se bloquea y `CANCELLED` es la baja lógica.
7. **Quotes**: crear quote pendiente posterior a ticket; total se calcula desde importes de trabajo y componentes del inventario con Decimal; no crear payment ni alterar advance fields en esta operación.
8. **Compatibilidad**: conservar lectura de tickets cliente y antiguos filtros administrativos; añadir campos/filtros aditivamente. `GET /api/customer/tickets` nunca incluye ticket MANUAL sin `customer_id`.
9. **Transporte web**: permitir PATCH en CORS para el origen frontend configurado y responder `Cache-Control: no-store` en rutas de gestión con datos personales.

## Complexity Tracking

La tabla `ticket_audit_events` y la separación de la cotización pendiente son complejidad justificada por la trazabilidad requerida y por evitar el borrado en cascada de quotes/payments/refunds. No se añade un servicio nuevo, una nueva dependencia ni un modelo de permisos.

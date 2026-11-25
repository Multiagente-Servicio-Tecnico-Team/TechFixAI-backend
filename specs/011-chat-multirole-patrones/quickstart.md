# Validación de chat multirol y paridad

## Requisitos para una prueba manual

1. Usa una base de datos de prueba, `AUTH_SECRET`, proveedor/modelo de chat y, para voz, `AUDIO_TRANSCRIPTION_ENABLED` con credencial de Groq. No uses credenciales ni base de producción.
2. Desde la raíz del backend, activa `.venv` y ejecuta `uvicorn app.main:app --reload --port 8000`.
3. Obtén sesiones autenticadas CUSTOMER, ADMIN y TECHNICIAN. La identidad de cliente viene de la sesión; el chat no acepta un `customer_id` como autoridad.
4. Repite los escenarios de `contracts/pattern-parity.md` con `hierarchical`, `orchestrator` y `decentralized`. Compara registros y estados normalizados, no los nombres de nodos ni el fraseo literal.
5. Para una escritura ADMIN, comprueba que el primer turno devuelve una propuesta sin modificar datos; otra identidad no puede confirmarla; el mismo ADMIN puede confirmarla una sola vez; cancelar o responder de forma ambigua no ejecuta la operación.
6. Prueba voz para cliente y ADMIN. Una solicitud de escritura ADMIN por audio solo propone; una confirmación hablada inequívoca posterior puede confirmar la propuesta pendiente del mismo ADMIN y conversación. Cambiar de rol no comparte esa conversación.
7. Comprueba cotizaciones `DIRECT_SALE` y `PC_BUILD` sin ticket: se guardan pendientes, al aceptar reservan stock y el pago sigue pendiente. Comprueba cotizaciones `REPAIR` ligadas a un ticket: se guardan al confirmar y no reservan inventario.
7a. En «Mis Tickets», confirma que el cliente ve las evaluaciones de hardware/software de sus tickets propios; inicia sesión con otro CUSTOMER y verifica que no recibe las de la primera cuenta.
8. No pruebes garantía de PC_BUILD desde este flujo: sigue siendo necesario definir la fuente de garantía asociada a una venta sin ticket.
9. Para instalar en otro entorno las migraciones requeridas por esta feature, revisa `sql/migrations/015_pc_build_standalone_quotes.sql` y `016_supplier_audit_events.sql`, respalda esa base y verifica después el ledger y las restricciones. El comando `python -m app.database.migrations status` es de solo lectura; no ejecuta SQL.

## Validación ejecutada

- `python -m pytest -p no:cacheprovider tests/contract -q --tb=short`: **124 passed**.
- Contratos más pruebas unitarias y de integración de Orquestador, Descentralizado, reembolsos y cotizaciones de servicio: **167 passed**.
- `python -m app.database.migrations status`: ledger presente; migraciones 006–016 aparecen como `RECORDED` en la base local de prueba. No se imprime ni se copia la cadena de conexión.
- Las pruebas son automatizadas y usan dobles de repositorio/modelo. No se ejecutó una sesión manual con Groq/LangSmith ni se validó una interfaz frontend.

Los contratos HTTP están en `contracts/admin-chat.openapi.yaml`; los invariantes por patrón están en `contracts/pattern-parity.md` y las capacidades ADMIN en `contracts/shared-capabilities.md`.

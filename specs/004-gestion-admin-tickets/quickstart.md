# Quickstart: Validar gestión administrativa de tickets

Guía de validación que se ejecutará durante implementación. No modifica el frontend ni aplica una migración por sí sola.

## Requisitos previos

1. Backend instalado según `requirements.txt` y entorno virtual del proyecto activado.
2. PostgreSQL **desechable de pruebas** inicializado con el esquema v2 y con datos sintéticos; no usar la BD compartida o producción.
3. Configurar una variable separada `TICKETS_TEST_DATABASE_URL` para las pruebas PostgreSQL. Las pruebas no deben cargar `.env` ni sustituirla por `DATABASE_URL`.
4. Cuenta activa ADMIN para emitir cookie de sesión y cuenta CUSTOMER para comprobar rechazo por rol.
5. Revisar el destino de la migración `sql/migrations/004_admin_ticket_management.sql` antes de aplicarla.
6. Contrato: [admin-tickets.openapi.yaml](contracts/admin-tickets.openapi.yaml); modelo: [data-model.md](data-model.md).

## Aplicación de migración (solo entorno de prueba)

```powershell
if (-not $env:TICKETS_TEST_DATABASE_URL) { throw 'Configura TICKETS_TEST_DATABASE_URL con una BD desechable de pruebas.' }
psql "$env:TICKETS_TEST_DATABASE_URL" -v ON_ERROR_STOP=1 -c "SELECT current_database() AS database_name, current_user AS database_user;"
# Confirma que database_name es la BD desechable esperada antes de continuar.
psql "$env:TICKETS_TEST_DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/migrations/004_admin_ticket_management.sql
```

La migración no se ejecuta en esta etapa de planificación. Confirmar que tickets preexistentes mantienen IDs, clientes, estado, cotizaciones y pagos; `origin` histórico queda desconocido, sin inferir origen.

## Escenarios HTTP

1. Sin cookie, `GET /api/admin/tickets` → `401`.
2. Con cookie CUSTOMER o TECHNICIAN, listar, crear o modificar tickets → `403`.
3. Desde el origen de frontend permitido, enviar preflight/`PATCH` con cookie y credenciales → CORS permite método y `Cache-Control: no-store` está presente.
4. Con cookie ADMIN, listar tickets con `limit`, `offset`, `request_type`, `status`, `origin` y `search`; comprobar `items`, `total` y orden determinista.
5. Crear ticket MANUAL sin usuario, con nombre/teléfono, correo opcional, título, detalle y tipo válido → `201`; consultar detalle y comprobar `origin=MANUAL`, contacto, adelanto/método y estado inicial.
6. Adelanto positivo sin método o método sin monto → `422`; importe negativo/formato inválido → `422`.
7. Crear ticket ONLINE desde flujo autenticado → `customer_id` proviene de la cookie; el cliente ve solo su ticket en `GET /api/customer/tickets`; ningún ticket MANUAL sin vínculo aparece ahí.
8. Actualizar equipo, detalle o estado a uno de los valores canónicos → `200`; el código permanece igual y existe evento de auditoría. Estado desconocido → `422`.
9. Asignar estado `CANCELLED` → ticket persiste, vínculos quote/payment/refund permanecen y se registra el actor. `DELETE` no elimina filas ni relaciones y devuelve conflicto/deprecación documentada.
10. Crear cotización para ticket elegible → `201`, `status=PENDING`, total calculado por servidor como mano de obra más líneas; `ticket_id` enlaza al ticket. No se crea pago ni se altera el adelanto del ticket.
11. Buscar un teléfono, correo, código o nombre y filtrar por origen/tipo/estado; paginar todas las páginas y comprobar que no hay registros omitidos ni duplicados.

## Pruebas

```powershell
.venv/Scripts/python.exe -m pytest tests/contract/test_admin_ticket_list_contract.py tests/contract/test_admin_ticket_create_contract.py tests/unit/test_ticket_management.py tests/integration/test_admin_ticket_api.py -q
.venv/Scripts/python.exe -m compileall -q app
git diff --check
```

En esta ejecución pasaron las pruebas anteriores (7 tests) y compilación. No se ejecutó la migración PostgreSQL: `TICKETS_TEST_DATABASE_URL` no está configurada. Cuando exista una BD desechable, verificar preservación de datos, nullable `customer_id`, restricciones y referencias al cancelar antes de conectar el frontend.


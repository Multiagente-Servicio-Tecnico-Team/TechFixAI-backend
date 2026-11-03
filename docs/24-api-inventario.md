# API de inventario del taller

**Estado**: implementada en backend.  
**Spec Kit**: `specs/005-api-inventario/`.  
**Contrato**: `specs/005-api-inventario/contracts/inventory.openapi.yaml`.

## Rutas

| Método y ruta | Resultado |
|---|---|
| `GET /api/inventory/parts` | Lista repuestos activos como `{ "parts": [...] }`. |
| `GET /api/inventory/categories` | Lista categorías distintas de repuestos activos como `{ "categories": [...] }`. |
| `POST /api/inventory/parts` | Crea un repuesto activo; devuelve 201 y `{ "part": ... }`. |
| `PUT /api/inventory/parts/{code}` | Reemplaza los datos editables; devuelve 200 y `{ "part": ... }`. El código no se puede cambiar. |
| `DELETE /api/inventory/parts/{code}` | Elimina si es posible; devuelve 204 sin cuerpo. Si un presupuesto lo referencia, devuelve 409 `in_use`. |

Todas las rutas requieren la cookie `techfix_session` y aceptan roles `ADMIN` y `TECHNICIAN`. Una sesión inválida devuelve 401; un cliente devuelve 403.

## Datos y compatibilidad

- El API utiliza la tabla existente `spare_parts`; no hubo migración.
- El precio se recibe y devuelve como texto decimal de dos posiciones y se persiste sin conversiones a float.
- El código sigue el formato de SKU que valida el formulario actual. Stock y mínimo son enteros de 0 a 999999.
- Las categorías se conservan tal como están en la base. La ruta de categorías permite cubrir valores fuera de las cinco opciones fijas que la interfaz muestra hoy.
- El origen del frontend debe estar en `FRONTEND_ORIGINS`. CORS incluye `PUT`, necesario para el formulario de edición.
- La FK `quote_details.spare_part_id` conserva el historial: una referencia impide eliminar el repuesto. La FK de `purchase_order_items` mantiene su regla existente `ON DELETE SET NULL`.

## Verificación

Las pruebas de contrato e integración focalizadas se ejecutaron con el Python del entorno `.venv`:

```text
7 passed
```

La integración usa SQLite aislado con relaciones FK equivalentes; no se modificó ni consultó la base PostgreSQL configurada en `.env`. Para verificación manual, seguir `specs/005-api-inventario/quickstart.md`.

## Limitación frontend pendiente

El cliente ya usa las rutas CRUD esperadas y envía credenciales. Aún debe solicitar `/api/inventory/categories` para sustituir sus opciones estáticas y permitir editar todos los valores existentes del catálogo.

# Data Model: API de inventario

## Repuesto (spare_parts)

Entidad existente; no se requiere migración.

| Campo API | Campo PostgreSQL | Restricción | Regla |
|---|---|---|---|
| id | id | BIGINT PK identity | Interno; no se acepta del cliente. |
| code | code | VARCHAR(50), unique, not null | Código público de 1–50; mayúsculas ASCII, dígitos y guiones; inmutable en edición. |
| name | name | VARCHAR(150), not null | 3–150 caracteres tras recortar espacios externos. |
| category | category | VARCHAR(50), nullable en BD | Obligatoria para API, 1–50; se conserva exacta. |
| description | description | TEXT | Opcional; descripción/compatibilidad para interfaz. |
| unit_price | unit_price | NUMERIC(10,2), not null | String decimal positivo, dos posiciones y dentro del límite del tipo. |
| current_stock | current_stock | INTEGER, >= 0 | Entero de 0 a 999999. |
| minimum_threshold | minimum_threshold | INTEGER, >= 0 | Entero de 0 a 999999. |
| active | active | BOOLEAN default true | Alta activa; catálogo filtra true. |
| created_at | created_at | TIMESTAMPTZ | Solo lectura; ISO 8601. |
| updated_at | updated_at | TIMESTAMPTZ / trigger | Actualizado al editar; ISO 8601. |

Ejemplo de recurso:

    {
      "code": "SSD-NVME-2TB-KC",
      "name": "SSD NVMe M.2 2TB Kingston KC3000 PCIe 4.0",
      "category": "Almacenamiento SSD / HDD",
      "description": "M.2 2280",
      "unit_price": "114.75",
      "current_stock": 8,
      "minimum_threshold": 2,
      "active": true,
      "created_at": "2026-11-02T12:30:00+00:00",
      "updated_at": "2026-11-02T12:30:00+00:00"
    }

## Categoría derivada

No tiene tabla propia. Es el valor spare_parts.category. GET /api/inventory/categories devuelve categorías distintas, no nulas ni vacías, de repuestos activos, ordenadas establemente y sin traducir.

## Relaciones

- quote_details.spare_part_id → spare_parts.id usa ON DELETE RESTRICT. Si hay referencia, DELETE devuelve 409 y no modifica el artículo.
- purchase_order_items.spare_part_id → spare_parts.id usa ON DELETE SET NULL. PostgreSQL conserva la línea de orden sin vínculo.

## Cuerpos de escritura

- Create y replace aceptan code, name, category, description, unit_price, current_stock y minimum_threshold.
- En replace, code debe coincidir con el parámetro de ruta.
- id, active, created_at y updated_at son de solo lectura. El cliente no puede asignar active ni campos adicionales.

## Errores

| Situación | HTTP | Código | Campo |
|---|---:|---|---|
| Sin sesión | 401 | session_required | — |
| Rol CUSTOMER | 403 | staff_only | — |
| Código inexistente | 404 | not_found | — |
| Duplicado / FK de presupuesto | 409 | duplicate / in_use | code para duplicado |
| Datos inválidos | 422 | invalid | si aplica |
| Persistencia no disponible | 503 | inventory_unavailable | — |

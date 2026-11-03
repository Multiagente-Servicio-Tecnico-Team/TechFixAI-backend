# Quickstart: validar API de inventario

## Prerrequisitos

- Backend configurado con .env local y PostgreSQL de prueba con el esquema ampliado.
- Cuenta autenticada con rol ADMIN o TECHNICIAN y cookie válida.
- Origen frontend agregado a FRONTEND_ORIGINS.

## Arranque

Desde la raíz del backend, activa el entorno virtual del proyecto y ejecuta el comando de desarrollo documentado (por defecto: `uvicorn app.main:app --reload --port 8000`). No publiques el contenido de .env.

## Consultar catálogo

Reemplaza `<COOKIE>` por la cookie de la sesión local; no la publiques ni la guardes en el repositorio.

```bash
curl -i http://localhost:8000/api/inventory/parts \
  -H 'Accept: application/json' \
  -H 'Cookie: techfix_session=<COOKIE>'

curl -i http://localhost:8000/api/inventory/categories \
  -H 'Accept: application/json' \
  -H 'Cookie: techfix_session=<COOKIE>'
```

Esperado: 200, { "parts": [...] } con los campos del frontend y el `id` numérico estable de cada fila de `spare_parts`; { "categories": [...] } devuelve los valores sin traducir. El frontend puede enviar ese `id` como `spare_part_id` al registrar líneas de compra; `code` es el SKU visible, no una clave numérica.

## Crear

Usa un SKU de prueba único:

```bash
curl -i -X POST http://localhost:8000/api/inventory/parts \
  -H 'Content-Type: application/json' \
  -H 'Cookie: techfix_session=<COOKIE>' \
  --data '{"code":"QA-SSD-001","name":"SSD de prueba 480 GB","category":"Almacenamiento SSD / HDD","description":"SATA 2.5 pulgadas","unit_price":"125.90","current_stock":4,"minimum_threshold":1}'
```

Esperado: 201 con { "part": {...} }, active true y precio "125.90".

## Actualizar

PUT usa todos los campos editables y conserva el SKU:

```bash
curl -i -X PUT http://localhost:8000/api/inventory/parts/QA-SSD-001 \
  -H 'Content-Type: application/json' \
  -H 'Cookie: techfix_session=<COOKIE>' \
  --data '{"code":"QA-SSD-001","name":"SSD de prueba 480 GB","category":"Almacenamiento SSD / HDD","description":"SATA 2.5 pulgadas","unit_price":"129.90","current_stock":3,"minimum_threshold":1}'
```

Esperado: 200 con precio y stock actualizados.

## Validar errores y permisos

- Sin cookie: 401, session_required.
- Sesión CUSTOMER: 403, staff_only.
- SKU repetido: 409, duplicate.
- Precio inválido, stock negativo, nombre corto o categoría vacía: 422 y sin cambios persistidos.
- Código inexistente en PUT/DELETE: 404.
- Repuesto referenciado por quote_details: DELETE responde 409, in_use, y preserva registro e historial.

## Comprobar en el frontend

1. Configura VITE_INVENTORY_URL según el .env.example del frontend.
2. Inicia sesión como personal y abre Inventario. Comprueba lista, búsqueda, filtros, métricas, edición y alta.
3. En DevTools verifica que el preflight CORS permite PUT y credenciales desde el origen frontend.
4. El frontend actual tiene cinco categorías estáticas. Para mostrar categorías adicionales debe consumir /api/inventory/categories en una tarea frontend posterior.

## Pruebas automatizadas previstas

Tras generar tareas e implementar:

```bash
python -m pytest -q tests/unit/test_inventory.py tests/contract/test_inventory_contract.py tests/integration/test_inventory_api.py
```

La integración requiere PostgreSQL de prueba para verificar la FK de presupuestos.

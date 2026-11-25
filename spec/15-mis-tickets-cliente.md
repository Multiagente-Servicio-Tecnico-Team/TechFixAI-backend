# Spec 15 - consulta de tickets del cliente

**Estado retrospectivo: Parcial — revisar error conocido al cargar tickets con cotización contra la rama actual.**
**Evidencia revisada:** docs/18-mis-tickets-cliente.md; app/database/repository.py; app/adapters/api/
**Alcance de esta revisión:** inspección estática; no se ejecutaron pruebas ni servicios. Ver [README.md](README.md) para el criterio y el flujo Spec Kit.


## Objetivo

Mostrar en el portal de cliente los tickets persistidos que pertenecen a la
cuenta autenticada, conservando el diseño de tarjetas y los filtros existentes.

## Requisitos

- `GET /api/customer/tickets` requiere una sesión CUSTOMER válida.
- El servidor filtra por el `customer_id` de la sesión; no acepta identificador
  de cliente del navegador como criterio de consulta.
- Responder tickets ordenados por fecha, estado, tipo, título, descripción,
  y la cotización más reciente con sus líneas cuando exista.
- La vista conserva búsqueda/filtros/estado visual, muestra estados del esquema
  PostgreSQL y es solo lectura.
- No incluir botones para aprobar presupuestos, revisar con asistente ni otras
  acciones administrativas en Mis Tickets. La futura vista administrativa va
  separada.
- Si no hay tickets, mostrar estado vacío; si el API falla, permitir reintentar.

## Limitaciones

La vista no modifica estados ni procesa aprobaciones. Una aprobación comercial
se ejecuta a través del flujo conversacional/backend que la implemente.

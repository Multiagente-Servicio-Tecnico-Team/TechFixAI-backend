# Evidencia 18 - Mis Tickets conectado a la cuenta

Se añadió `GET /api/customer/tickets`, protegido por `SessionGuard` como ruta de
cliente. El ID usado en la consulta se obtiene de la cookie validada, y la
consulta del repositorio limita filas con `tickets.customer_id`. Incluye la
cotización más reciente y líneas de productos para representar el resumen.

La pantalla React consume el endpoint con cookie (`credentials: include`),
conserva tarjetas, filtros y búsqueda, presenta estados reales del esquema y
retira aprobación/revisión de presupuesto de esta vista. Queda como listado de
solo lectura.

Validación: compileall, build Vite y `git diff --check` aprobados. No se ejecutaron pruebas automatizadas ni se consultó/escribió PostgreSQL.

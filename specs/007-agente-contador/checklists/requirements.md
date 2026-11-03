# Specification Quality Checklist: Asistente contable común

**Purpose**: Revisar coherencia con 001, 003 y 006 antes de planificar.
**Created**: 2026-11-03
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] Alcance limitado a especificación; sin código ni documentación paralela.
- [x] Misma capacidad y contrato en los tres patrones, con coordinación propia.
- [x] Operaciones existentes de 003 identificadas; no se duplican rutas, servicios, tablas ni migraciones.
- [x] D1 y D2 de 003 respetadas: ingreso manual de ADMIN y asiento CONFIRMED en una operación.
- [x] FR-015 de 006 respetada: una compra o recepción no crea asientos.

## Requirement Completeness

- [x] Acceso ADMIN comprobado en backend; CUSTOMER y TECHNICIAN excluidos.
- [x] Fecha, concepto, detalle, categoría y líneas provienen de ADMIN.
- [x] Vista previa temporal sin persistencia, correlativo ni DRAFT.
- [x] Validación determinista de estructura y balance de 003.
- [x] Escritura solo después de confirmación explícita de ADMIN.
- [x] Consulta de categorías, listado, detalle, creación y reversión con motivo cubiertas.
- [x] Fuentes comerciales excluidas de la generación de líneas y asientos.
- [x] Escenarios de autorización, validación, creación, reversión y equivalencia entre patrones presentes.

## Feature Readiness

- [x] Alcance y criterios de aceptación documentados sin inventar cuentas ni IGV.
- [ ] Plan e implementación preparados: fuera de esta etapa.

## Notes

- Revisión documental. No se ejecutaron pruebas de PostgreSQL ni de los patrones.
- No se adoptan cuentas, reglas tributarias ni decisiones de arquitectura de Pollería.

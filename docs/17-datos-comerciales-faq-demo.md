# Evidencia 17 - datos comerciales y preguntas frecuentes

La FAQ RAG cubre servicios, dirección y horario de tienda, tarifas base,
formas de pago, pasos de compra/servicio, garantía y logística.

- Tarifas base alineadas con `Settings`: diagnóstico S/ 50, mantenimiento S/ 35,
  armado S/ 50 y venta directa sin mano de obra; el total de cotización se toma
  del servidor si hay overrides.
- Medios de pago de demostración: Yape, Plin, transferencia, Visa/Mastercard y
  efectivo en tienda. El backend solo registra una orden PENDING, no procesa ni
  confirma los medios; la FAQ no inventa cuentas o QR.
- El proceso refleja aceptación explícita, logística pendiente y garantía de
  tres meses que el flujo genera para venta/armado una vez registrado lo logístico.
- Los datos comerciales se marcan en comentario HTML para reemplazo antes de
  producción; el recuperador lexical excluye el preámbulo y entrega secciones.

Validación: 15 pruebas FAQ/workflows, compileall y `git diff --check` correctos;
LangSmith desactivado. Sin escrituras a PostgreSQL. Dirección/horario/métodos de
pago son valores ficticios para demostración.

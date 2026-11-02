# Spec 14 - datos comerciales de FAQ para demostración

**Estado retrospectivo: Implementada para demostración; dirección, horario y medios de pago son ficticios.**
**Evidencia revisada:** docs/17-datos-comerciales-faq-demo.md; data/knowledge/; app/rag/
**Alcance de esta revisión:** inspección estática; no se ejecutaron pruebas ni servicios. Ver [README.md](README.md) para el criterio y el flujo Spec Kit.


## Objetivo

Responder preguntas habituales sobre los servicios y la tienda TechFix con
información concreta cargada en el RAG de FAQ.

## Requisitos

- Dirección del escenario: Av. Los Talleres 450, San Borja, Lima, Perú.
- Atención de lunes a viernes de 09:00 a 18:00 y sábados de 09:00 a 13:00,
  hora local de Lima; domingos y feriados cerrado.
- Tarifas base de mano de obra: diagnóstico S/ 50.00, mantenimiento/reparación
  definida S/ 35.00, armado S/ 50.00, venta directa S/ 0.00. El servidor puede
  aplicar overrides; la cotización generada es el total vigente.
- Medios comerciales de demostración: Yape, Plin, transferencia, Visa/Mastercard
  y efectivo en tienda. El chat no procesa ni confirma pagos ni comparte datos
  de cuenta/QR; tras aceptación solo registra pago `PENDING`.
- Explicar el proceso: solicitud, consulta de inventario o evaluación, selección
  y cambios, cotización, aceptación explícita, logística pendiente y garantía.
- El flujo crea una garantía de tres meses para ventas directas y armados al
  completar el registro logístico; la consulta individual requiere código de
  póliza. El flujo no promete cobertura automática de reparación.
- Mantener los datos ficticios identificados internamente para sustituirlos
  antes de operar con información comercial real.

## Limitaciones

La dirección, horarios y medios de pago son ficticios para la demostración y no
se deben usar como datos de una tienda real. El backend no procesa el pago, no
reserva inventario y no confirma despacho/recepción. Tarifas base configurables.

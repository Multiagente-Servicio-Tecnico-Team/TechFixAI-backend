# 01 — Ventas del patrón jerárquico

**Estado retrospectivo: Parcial — revisar el estado del esquema y el flujo de guardado antes de tratarlo como completo.**
**Evidencia revisada:** docs/01-ventas.md; app/agents/jerarquico/; app/database/repository.py
**Alcance de esta revisión:** inspección estática; no se ejecutaron pruebas ni servicios. Ver [README.md](README.md) para el criterio y el flujo Spec Kit.


## Objetivo

El equipo comercial debe atender ventas directas consultando exclusivamente el
catálogo PostgreSQL. El supervisor solicita los datos mínimos del pedido, el
agente de almacén identifica coincidencias y disponibilidad y ventas calcula la
propuesta con `Decimal`.

## Reglas

- No inventar códigos, precios, moneda, stock ni proveedor.
- No elegir una coincidencia ambigua automáticamente; pedir el código o modelo.
- No cotizar productos sin precio positivo ni cantidades sin stock suficiente.
- El triage crea inmediatamente un ticket `NEW` para ventas, armado y solicitudes
de servicio que ya tienen la información mínima. El diagnóstico de reparación
actualiza ese mismo ticket a `IN_DIAGNOSIS`.
- Una propuesta requiere aceptación explícita antes de persistir cotización,
detalles y pago pendiente. El rechazo cancela el ticket de ingreso y no crea
cotización ni pago.
- Registrar el pago como `PENDING`; la creación no implica recepción de dinero,
reserva de stock, despacho ni entrega.
- Registrar la modalidad logística como preferencia pendiente de recepción.
- No ofrecer armado de PC como cotización final mientras no exista una relación
de compatibilidad verificable entre componentes en el esquema.
- Compras puede explicar la limitación si no hay una cotización verificable de
proveedor asociada al artículo.

## Persistencia y esquema

Se emplean `tickets`, `quotes`, `quote_details`, `payments`,
`logistics_records` y `spare_parts` del esquema PostgreSQL vigente. Los importes
se manejan como `Decimal`. El ticket se crea como `NEW` durante el triage; el
diagnóstico actualiza `diagnosis_type`, `hardware_diagnosis` o
`software_diagnosis` y el estado a `IN_DIAGNOSIS`. Tras la aceptación explícita,
la cotización `ACCEPTED`, sus detalles, el pago `PENDING` y el estado final
`PAYMENT_PENDING` se registran en una transacción.

La tarifa de mantenimiento/reparación predeterminada es S/ 35.00, según los
prompts de servicio; `LABOR_MAINTENANCE_PRICE` permite una tarifa configurada
explícitamente. Diagnóstico y armado mantienen sus tarifas configurables.

## Criterios de aceptación

- La consulta a catálogo usa parámetros; el LLM no genera SQL ni importes.
- El rechazo cancela el ticket de ingreso y no crea cotización aceptada ni pago.
- El flujo de reparación guarda `hardware_diagnosis` o
  `software_diagnosis` según `diagnosis_type`; no depende de la columna antigua
  `provisional_diagnosis`.
- Las pruebas aisladas verifican venta aceptada, pago pendiente, logística,
  diagnóstico hardware/software, catálogo ambiguo y límites de inventario.

Checkpoint de commit del usuario: ____________________

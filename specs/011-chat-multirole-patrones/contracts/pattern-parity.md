# Contrato de paridad para los tres patrones

Para cada caso se instancian los adaptadores `hierarchical`, `orchestrator` y `decentralized` con el mismo perfil de modelo, retriever y repositorios falsos. Se comparan efectos/resultados normalizados; no el orden interno de nodos.

## Matriz requerida

| Dominio | Caso | Invariante |
|---|---|---|
| Cliente | Consulta FAQ con documentos comunes | Misma respuesta basada en pasajes/citas y misma abstención sin evidencia |
| Cliente | RAM/SSD/precio/stock | Datos leídos del catálogo SQL; nunca afirmar stock o precio de RAG |
| Cliente | Reparación/soporte | Crear y mostrar el ticket de servicio al completar la recepción, antes del diagnóstico; persistir la evaluación técnica en el ticket del mismo cliente; mientras se decide, exponer el mismo código en los tres patrones; al aceptar, agregar la cotización `REPAIR` a ese ticket y dejar pago `PENDING`, sin reservar inventario |
| Cliente | Venta y PC_BUILD | Cotización sin ticket; aceptación reserva inventario y mantiene pago pendiente |
| Cliente | Aceptar/consultar | Propiedad comprobada desde sesión; pago solo cambia tras confirmación de pago soportada |
| Admin | Lectura de tickets/clientes/inventario/proveedores/compras/órdenes/ventas/contabilidad | Solo capacidad allowlisted; actor y rol provienen de sesión |
| Admin | Crear/actualizar/cancelar/emitir/recibir/asiento | Primer turno solo crea propuesta; mismo actor confirma; revalidación e idempotencia |
| Auth | CUSTOMER/TECHNICIAN pide acción ADMIN | Denegado antes de invocar la capacidad |
| Voz | CUSTOMER y ADMIN | Mismas capacidades por rol; una transcripción ADMIN inequívoca puede confirmar solo la propuesta pendiente de esa sesión y conversación |
| Modelo | Inspección runtime | Mismo provider/model/temperature efectiva, no solo igual metadata |
| Robustez | Reintento/doble confirmación o recurso cambiado | Efecto a lo sumo una vez; conflicto sin mutación parcial |

## Normalización

- Comparar tipo de resultado, importes como decimal/cadena monetaria, referencias de entidades y estado final.
- Ignorar nombres de nodos, traza interna, fraseo superficial y orden de recuperación si los mismos pasajes y evidencia se mantienen.
- Falsificar proveedores externos; ningún test de contrato requiere Groq, LangSmith ni PostgreSQL remoto.

## Estado de implementación observado

- Los tres patrones guardan las cotizaciones `DIRECT_SALE` y `PC_BUILD` sin ticket de servicio. Al aceptar, revalidan stock, reservan unidades y dejan el pago pendiente.
- Los tres patrones crean tickets para reparación/soporte antes de terminar el diagnóstico, persisten la evaluación técnica con titularidad validada y exponen el código durante la propuesta. El Orquestador conserva el ticket desde la recepción y, cuando el cliente acepta, agrega la cotización `REPAIR` a ese mismo ticket y registra un pago `PENDING`. El flujo no reserva ni descuenta inventario. Jerárquico y Descentralizado mantienen sus topologías y pasos propios, con la misma relación y estados persistidos.
- Los adaptadores mantienen sus topologías, pero comparten política de rol, perfil efectivo del modelo y corpus documental canónico.
- El servicio ADMIN y su registro allowlisted de capacidades son comunes a los tres valores de patrón. `pattern` conserva contexto y trazabilidad; las operaciones ADMIN no se delegan al grafo CUSTOMER.
- Las migraciones 015 (`PC_BUILD` sin ticket) y 016 (`supplier_audit_events`) están registradas en el ledger de la base local de prueba junto con las versiones 006–014. Esto no demuestra que otro entorno tenga el mismo esquema: cada entorno debe ejecutar y verificar sus migraciones versionadas.
- La suite de contratos usa proveedores, repositorios y perfiles falsos; no requiere Groq, LangSmith ni PostgreSQL remoto. El resultado más reciente está registrado en `quickstart.md`.


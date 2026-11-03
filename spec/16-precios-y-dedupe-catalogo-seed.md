# Spec 16 - precios y deduplicación del seed de inventario

**Estado retrospectivo: Aplicada al archivo seed según evidencia; no actualiza automáticamente bases ya pobladas.**
**Evidencia revisada:** docs/19-precios-y-dedupe-catalogo-seed.md; sql/; contexto/
**Alcance de esta revisión:** inspección estática; no se ejecutaron pruebas ni servicios. Ver [README.md](README.md) para el criterio y el flujo Spec Kit.


## Objetivo

Mejorar el catálogo de demostración usado para ventas, con precios de referencia
en soles peruanos y menos filas redundantes por familia de componentes.

## Requisitos

- Revisar precios de componentes con fuentes comerciales peruanas y expresar
  importes en PEN.
- Mantener alternativas por marca cuando representen opciones reales de compra;
  no multiplicar filas solo por cambiar frecuencia cuando el seed no especifica
  un número de parte distinto.
- Eliminar filas de producto repetidas entre los bloques inicial y ampliado.
- Conservar el stock/precio solo como dato de demostración sujeto a actualización.
- No modificar una base conectada al editar el archivo de inserción.
- Documentar que `ON CONFLICT (code) DO NOTHING` no actualiza filas existentes.

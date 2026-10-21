# Instrucciones del proyecto

Backend de TechFix.AI (FastAPI + LangGraph + PostgreSQL). El frontend vive en
[TechFixAI-frontend](https://github.com/Multiagente-Servicio-Tecnico-Team/TechFixAI-frontend).

## Antes de escribir código

1. Lee `memory.md` (historial y limitaciones), `features.md` (qué existe, dónde y de quién) y `docs.md` (índice de documentación).
2. Revisa el trabajo en curso para no duplicarlo: `git fetch --all`, `gh pr list` y las ramas abiertas.
3. Busca si ya existe lo que vas a hacer (`git grep`). Reutiliza y extiende; no reescribas un módulo que funciona.
4. Si el cambio toca carpetas de otro integrante (tabla de responsables en `features.md`), avisa antes o hazlo en un PR aparte.

## Reglas originales del proyecto

- Implementar y validar en orden: 1) ventas, 2) trazabilidad, 3) chat autenticado.
- Mantener especificaciones en `spec/` y evidencia y plan en `docs/`, numerados por tarea.
- Actualizar `memory.md` al cerrar cada tarea; registrar limitaciones reales.
- Usar Decimal para dinero; no inventar precios fuera del catálogo de prueba.
- No registrar mensajes, credenciales, entradas completas ni textos de excepciones en trazas.
- Ejecutar pruebas aisladas en `tests/`; los scripts raíz requieren servicios externos.
- La compilación final se realiza después de validar las tres tareas.

## Dónde va cada cosa

- Un patrón nuevo o un cambio en la API del chat: respeta el contrato `POST /api/chat` (`app/chat/contract.py`); el frontend depende de él.
- Si existe `app/domain/` (PR #32, Clean Architecture): las reglas de negocio van en `domain`, los casos de uso en `application`, y cada patrón se conecta con su adaptador en `app/adapters/patterns/`. `domain` y `application` no importan FastAPI, SQLAlchemy, LangGraph ni Groq (lo verifica `tests/unit/architecture`).
- Lógica interna de cada patrón: `app/agents/<patrón>/`, a cargo de su responsable.
- Acceso a datos: `app/database/repository.py` (SQL parametrizado; el modelo nunca escribe SQL). Cambios de esquema: script en `sql/` y aviso al equipo.
- Cuentas y sesión: `app/accounts/` (la identidad sale siempre de la cookie firmada, nunca del cuerpo de la petición).

## Responsabilidades repetidas: usa la existente

Hay piezas implementadas más de una vez; no agregues otra copia (detalle en `features.md`, sección «Código duplicado»):
- Configuración: `app/settings.py` (patrones y BD) y `app/accounts/config.py` (cuentas). `app/config.py` solo lo usa el Orquestador.
- Contraseñas: `app/accounts/security.py`. `app/auth.py` no se usa.
- Presupuestos: `app/agents/jerarquico/tools/quotes.py` y `app/agents/orquestador/agentes/quotes.py` calculan distinto.
- Búsqueda en conocimiento: `app/agents/jerarquico/retriever.py`, `app/agents/orquestador/knowledge/retriever.py` y `app/rag/retriever.py`.

## Convenciones

- Código e identificadores en inglés; comentarios pueden estar en español; mensajes al usuario en español.
- Commits convencionales (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`) en español, sin mencionar herramientas ni agentes.
- Trabajo en ramas y PR hacia `develop`; nada directo a `main` ni a `develop`.
- Nunca subir `.env`, `.env.example` ni archivos con claves; no mostrar claves en logs ni en mensajes.
- Pruebas: `python -m pytest -q` (suite aislada). Las que usan Groq, PostgreSQL o SMTP reales no son parte de la suite aislada.

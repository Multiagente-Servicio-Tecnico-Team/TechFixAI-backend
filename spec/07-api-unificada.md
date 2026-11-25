# Especificación 07 — API unificada de cuentas y chat

**Estado retrospectivo: Implementada según la estructura actual; evidencia estática, sin ejecución en esta revisión.**
**Evidencia revisada:** app/main.py; app/accounts/; app/adapters/api/; tests/integration/test_combined_api.py
**Alcance de esta revisión:** inspección estática; no se ejecutaron pruebas ni servicios. Ver [README.md](README.md) para el criterio y el flujo Spec Kit.


## Objetivo

Exponer la autenticación y el chat multiagente bajo el mismo origen HTTP para
que la cookie de sesión del cliente se comparta al invocar los patrones.

## Requisitos

1. La aplicación unificada conserva el contrato de chat en `/api/chat` y
   `/api/chat/patterns`.
2. La aplicación de cuentas se monta en `/auth`; sus rutas quedan, por ejemplo,
   en `/auth/registro`, `/auth/login`, `/auth/me` y `/auth/logout`.
3. El login y el chat usan la misma configuración de firma de sesión y la misma
   fábrica de conexiones de base de datos.
4. Las APIs originales pueden seguir ejecutándose por separado para pruebas o
   desarrollo aislado.
5. El frontend local dirige autenticación y chat al único backend en el puerto
   8000; no se incluyen secretos en variables `VITE_*`.

## Criterios de aceptación

- Sin cookie, `GET /api/chat/patterns` devuelve `401`.
- Una sesión iniciada en `/auth/login` permite acceder a
  `/api/chat/patterns` con el mismo cliente HTTP.
- Las rutas del chat conservan sus contratos y el frontend compila con los
  nuevos valores de URL.

## Fuera de alcance

La configuración de servicios, bases de datos y dominios del proveedor cloud;
se documentará cuando se soliciten explícitamente los archivos de despliegue.

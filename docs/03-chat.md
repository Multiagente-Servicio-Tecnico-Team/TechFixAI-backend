# 03 — Chat autenticado y cookie de sesión

Se conserva la cookie HttpOnly `SameSite=Lax; Path=/` emitida por login. El
cliente React ya utilizaba `credentials: "include"` tanto para login como para
chat; el problema del despliegue era permitir bases absolutas a distintos
orígenes. En producción, `resolveApiBaseUrl` ahora fuerza el proxy same-origin:

- Auth: `/backend/auth` → `/auth/*` del backend unificado.
- Chat: `/backend` → rutas `/api/*` del backend unificado.

La regla de `landing/public/_redirects` dirige `/backend/*` al servicio Render.
Esto hace que el navegador reciba la cookie bajo el origen del portal y la
envíe en `POST /backend/api/chat`; evita depender de cookies cross-site
`SameSite=Lax`. URLs absolutas de producción son reemplazadas por los fallbacks
same-origin incluso si una variable de build contiene el host externo.

## Validación completada

- Cliente auth y chat: pruebas existentes verifican `credentials: "include"`.
- Configuración URL: tres pruebas prueban fallback de producción, rechazo de
  URLs absolutas en producción y conservación de URLs de desarrollo/rutas proxy.
- Vitest: **61 pruebas en 7 archivos aprobadas**.
- `npm --prefix landing run build`: correcto; Vite genera assets y publica
  `dist/_redirects`.

## Límite de validación

No se dispone de una sesión automatizada en el dominio Netlify desplegado; la
propagación real de `Set-Cookie` a través del proxy, sus atributos en ese
dominio y el reenvío de `Cookie` al backend requieren smoke test después de
publicar. La ruta proxy debe mantenerse configurada para cualquier hosting de
producción distinto de Netlify.

Checkpoint de commit del usuario: ____________________

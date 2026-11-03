# Evidencia 10 — proxy de API desde Netlify

## Cambio

Se agregó `landing/public/_redirects` para enviar `/backend/*` desde Netlify
hacia la API unificada de Render. La segunda regla conserva el fallback de
rutas de la SPA. Al estar el archivo en `public/`, Vite lo copia al directorio
de publicación `dist/`.

Login y chat deben compartir el origen del portal: el navegador recibe la cookie
HttpOnly del proxy y la vuelve a enviar al endpoint de chat bajo el mismo host.
En producción `SameSite=Lax` funciona en esta topología; llamadas cross-site al
host de Render no son fiables y no se deben usar para la sesión.

Configurar antes del build del sitio de Netlify:

```env
VITE_API_URL=/backend/auth
VITE_CHAT_URL=/backend
```

El origen del sitio Netlify debe estar incluido en `FRONTEND_ORIGINS` del
backend Render solo si el frontend también necesita llamadas CORS directas. Con
las rutas proxy same-origin no se requiere CORS para login ni chat. Los clientes
de autenticación y chat usan `/backend/auth` y `/backend` como fallback de
producción; una URL absoluta configurada en producción se reemplaza por esas
rutas para no intentar enviar cookies al origen externo. En desarrollo se
conservan las URLs configuradas (por ejemplo, `localhost:8000`).

Después de cambiar variables o reglas, reconstruir y volver a publicar el
frontend, cerrar sesión e iniciar una sesión nueva para obtener una cookie del
origen correcto. No se debe usar `SameSite=None` como sustituto del proxy:
además de requerir `Secure`, los navegadores pueden bloquear cookies de terceros.

## Validación

Se verifica con `npm --prefix landing run build` que Vite publica
`dist/_redirects` junto con los recursos estáticos. La propagación HTTP de las
reglas y la cookie en dominio real requieren un deploy de Netlify y no se
consideran probadas localmente. Las pruebas unitarias verifican que la
configuración de producción selecciona las rutas del mismo origen y que ambos
clientes HTTP incluyen credenciales.

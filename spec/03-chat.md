# 03 — Chat autenticado del portal

**Estado retrospectivo: Parcial — contrato backend implementado; proxy y smoke test de producción dependen del frontend/despliegue.**
**Evidencia revisada:** docs/03-chat.md; app/accounts/; app/chat/; TechFixAI-frontend
**Alcance de esta revisión:** inspección estática; no se ejecutaron pruebas ni servicios. Ver [README.md](README.md) para el criterio y el flujo Spec Kit.


## Objetivo

El cliente autenticado debe poder usar el chat de patrones sin incluir su correo,
ID ni credenciales en el cuerpo de la conversación. El backend obtiene la
identidad de una cookie HttpOnly emitida al iniciar sesión.

## Contrato de sesión y origen

- Login bajo `/backend/auth/login`; chat bajo `/backend/api/chat`.
- `auth.js` y `chat.js` envían `credentials: "include"`.
- En producción ambos clientes usan rutas same-origin del proxy; URLs absolutas
  se sustituyen por el fallback local para evitar una cookie cross-site.
- La cookie tiene `HttpOnly`, `Secure`, `SameSite=Lax` y `Path=/` en HTTPS.
- El proxy debe transmitir `Set-Cookie` de login y reenviar `Cookie` en chat.
- No cambiar la cookie a `SameSite=None` para compensar un proxy/origen mal
  configurado; los navegadores pueden bloquear cookies de terceros.

## Comportamiento

El chat conserva los flujos de venta, soporte y otros agentes del patrón
seleccionado. Sin cookie válida, el backend responde 401 y el portal redirige a
inicio de sesión. El cliente no guarda secretos; los mensajes permanecen en la
conversación activa de la sesión y no se agregan a la traza.

## Aceptación y límites

- Tests prueban el envío de credenciales en login y chat, base same-origin de
  producción y error de sesión vencida.
- Build publica el proxy `_redirects`.
- La transmisión efectiva de cookie y la sesión deben confirmarse en el dominio
  desplegado; una prueba local no acredita la configuración de Netlify.

Checkpoint de commit del usuario: ____________________

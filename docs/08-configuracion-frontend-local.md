# Evidencia 08 — configuración local del frontend

## Cambio

Se creó `landing/.env` para que Vite conecte el portal con las APIs locales:

```dotenv
VITE_API_URL=http://localhost:8000
VITE_CHAT_URL=http://localhost:8001
```

`VITE_API_URL` configura `landing/src/api/auth.js` para registro, inicio de
sesión y demás operaciones de cuenta. `VITE_CHAT_URL` configura
`landing/src/api/chat.js`, que envía el patrón seleccionado a `/api/chat`.

El archivo `.env` local está ignorado por `landing/.gitignore`; no se versiona.
`landing/.env.example` contiene los mismos valores de referencia. Vite carga
variables al arrancar, por lo que hay que reiniciar el servidor tras editarlas.

## Validación

- `npm --prefix landing run build`: aprobado.
- El bundle de producción contiene las dos URLs locales configuradas.

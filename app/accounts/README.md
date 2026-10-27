# API de cuentas — registro, inicio de sesión y recuperación de contraseña

Servicio Python que registra clientes en la tabla `users` de PostgreSQL con la contraseña protegida por hash
bcrypt, abre sesión con una cookie firmada y permite restablecer la contraseña con un enlace temporal enviado
por correo (tabla `recovery_tokens`). Lo usa el frontend (`landing/`) para las pantallas de registro, inicio de
sesión, recuperación y restablecimiento.

## Frameworks y librerías

| Uso | Herramienta |
| --- | --- |
| API HTTP | FastAPI 0.142 + Uvicorn 0.54 |
| Acceso a datos | SQLAlchemy 2.1 con el driver `pg8000` (Python puro, sin compilación) |
| Base de datos | PostgreSQL 16 (esquema del script `creacion_tablas_sin_inserciones.sql`) |
| Hash de contraseñas | bcrypt (costo 12, formato `$2b$12$…`) |
| Validación | Pydantic 2 |
| Correo | Plantilla Jinja2 y servicio SMTP del repositorio (`app/email`) |
| Pruebas | pytest + TestClient (SQLite en memoria); colección de Postman ejecutable con Newman |

Dependencias en [`requirements-auth.txt`](../../requirements-auth.txt).

## Estructura

```text
app/accounts/
├── api.py        # Aplicación FastAPI: rutas, CORS, cookie de sesión y manejo de errores
├── config.py     # Configuración leída de variables de entorno
├── mailer.py     # Correo de restablecimiento: SMTP o carpeta local (outbox)
├── models.py     # Mapeo de las tablas users y recovery_tokens (no crea tablas en PostgreSQL)
├── schemas.py    # Validación de los cuerpos de las rutas
├── security.py   # bcrypt, firma de la cookie, tokens de restablecimiento y límite de intentos
└── service.py    # Reglas de registro, autenticación y restablecimiento
app/email/templates/password_reset.html        # Plantilla del correo de restablecimiento
tests/test_accounts_api.py                     # Pruebas de registro e inicio de sesión
tests/test_accounts_recovery.py                # Pruebas de recuperación y restablecimiento
postman/techfix-auth.postman_collection.json   # Pruebas de API con Postman
```

## Rutas

| Método y ruta | Cuerpo | Respuestas |
| --- | --- | --- |
| `POST /registro` | `{ nombre, apellido?, email, telefono, password }` | `201 { usuario }` + cookie `techfix_session` · `409` correo ya registrado · `422` datos inválidos |
| `POST /login` | `{ email, password }` | `200 { usuario }` + cookie `techfix_session` · `401` credenciales · `429` demasiados intentos |
| `POST /logout` | — | `204` y borra la cookie |
| `GET /me` | — | `200 { usuario }` con sesión válida · `401` sin sesión |
| `POST /recuperar` | `{ email }` | `200` con el mismo mensaje exista o no la cuenta · `422` correo inválido · `429` demasiadas solicitudes |
| `POST /restablecer` | `{ token, password }` | `200` contraseña actualizada · `410` enlace inválido, vencido o usado · `422` contraseña débil |
| `GET /salud` | — | `200 { estado, bd }` |

`usuario` = `{ id, nombre, apellido, email, rol }`. El rol viene de la columna `role` (`CUSTOMER`,
`TECHNICIAN`, `ADMIN`); el registro público siempre crea `CUSTOMER`.

El código está en inglés (`RegisterIn.first_name`, `last_name`, `phone`; `UserOut.role`; `SessionCustomer.first_name`)
y los alias de Pydantic mantienen las claves JSON en español de esta tabla, así que el contrato no cambia.

## Reglas principales

- Correo en minúsculas y único sin distinguir mayúsculas; teléfono en formato E.164 (`+51987654321`).
- Contraseña de 8 a 72 bytes con mayúscula, número y símbolo. Solo se guarda `password_hash`.
- Si `apellido` no se envía, `nombre` se separa en la primera palabra (nombre) y el resto (apellido).
- El inicio de sesión responde igual para correo inexistente, contraseña incorrecta o cuenta inactiva, y
  siempre verifica un hash para no revelar qué correos existen por el tiempo de respuesta.
- 5 intentos fallidos del mismo correo en 15 minutos bloquean temporalmente el acceso (429).
- Los errores 422 indican el campo pero no repiten los valores enviados.
- Cookie de sesión `HttpOnly`, `SameSite=Lax`, firmada con HMAC-SHA256 y válida 8 horas.

### Recuperación de contraseña

- `/recuperar` responde siempre igual para no revelar qué correos tienen cuenta; el correo se envía en
  segundo plano.
- El enlace `FRONTEND_URL/portal/restablecer?token=…` dura 15 minutos, sirve una sola vez y solo vale el último
  solicitado (los anteriores se invalidan).
- En `recovery_tokens.token` se guarda el **hash SHA-256** del token; el token en claro solo existe en el correo.
- Al restablecer se guarda el nuevo hash bcrypt, se invalidan todos los enlaces de la cuenta y se **cierran las
  sesiones abiertas** (la cookie incluye una huella de la contraseña).
- Máximo 5 solicitudes de enlace por correo cada 15 minutos (429).
- Correo: `MAIL_MODE=smtp` usa las variables `SMTP_*`; `MAIL_MODE=outbox` (por defecto) guarda cada correo como
  archivo HTML en `OUTBOX_DIR` (`.local/outbox`, ignorada por git) para probar sin una cuenta de correo.

## Ejecución local

Para ejecutar cuentas y chat juntos (opción recomendada para que compartan el
mismo host y cookie), inicia el punto de entrada unificado desde la raíz:

```bash
.venv/Scripts/python -m uvicorn app.combined:create_app --factory --host localhost --port 8000
```

En esta modalidad, todas las rutas de esta API llevan el prefijo `/auth`
(por ejemplo, `POST /auth/login` y `GET /auth/me`). La API puede ejecutarse por
separado con las rutas sin prefijo descritas arriba:

1. Crear la base de datos y aplicar el script del equipo:

   ```bash
   createdb -U postgres techfix
   psql -U postgres -d techfix -f creacion_tablas_sin_inserciones.sql
   ```

2. Instalar dependencias (Python 3.12):

   ```bash
   python -m venv .venv
   .venv/Scripts/python -m pip install -r requirements-auth.txt
   ```

3. Configurar `.env` en la raíz del repositorio (ver `.env.example`):

   ```bash
   DATABASE_URL=postgresql+pg8000://postgres:CLAVE@localhost:5432/techfix
   AUTH_SECRET=<cadena aleatoria de 32 caracteres o más>
   AUTH_SECURE_COOKIE=false
   FRONTEND_ORIGINS=http://localhost:5173
   FRONTEND_URL=http://localhost:5173
   MAIL_MODE=outbox
   ```

   `AUTH_SECRET` se puede generar con `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

4. Iniciar solo la API de cuentas:

   ```bash
   .venv/Scripts/python -m uvicorn app.accounts.api:create_app --factory --host localhost --port 8000
   ```

5. Conectar el frontend con `VITE_API_URL=http://localhost:8000` en `landing/.env` y ejecutar
   `npm --prefix landing run dev`.

Usar `localhost` (no `127.0.0.1`) tanto en la API como en el frontend: así el navegador trata ambos puertos como
el mismo sitio y envía la cookie de sesión.

## Pruebas

Automáticas, sin PostgreSQL:

```bash
.venv/Scripts/python -m pytest tests/test_accounts_api.py tests/test_accounts_recovery.py -q
```

API con Postman: importar `postman/techfix-auth.postman_collection.json` y ejecutar la colección completa en
orden (la primera petición genera un correo único). También desde la terminal con Newman:

```bash
npx newman run postman/techfix-auth.postman_collection.json
```

Verificación en la base de datos:

```sql
SELECT id, email, phone, password_hash, name, last_name, role, active FROM users ORDER BY id;
SELECT id, user_id, token, used, created_at, expires_at FROM recovery_tokens ORDER BY id;
```

## Despliegue

- Definir `DATABASE_URL` hacia la base de datos en la nube, un `AUTH_SECRET` propio y
  `FRONTEND_ORIGINS` con la URL pública del frontend.
- Servir con HTTPS y dejar `AUTH_SECURE_COOKIE=true` (valor por defecto).
- Ejecutar detrás de un proxy o con varios procesos de Uvicorn; el límite de intentos fallidos vive en la
  memoria de cada proceso.

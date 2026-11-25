# 05 — Frontend: landing, registro de cuenta e inicio de sesión

**Estado retrospectivo: Histórica — la implementación vive en el repositorio TechFixAI-frontend.**
**Evidencia revisada:** TechFixAI-frontend/; docs/05-frontend-landing-auth.md
**Alcance de esta revisión:** inspección estática; no se ejecutaron pruebas ni servicios. Ver [README.md](README.md) para el criterio y el flujo Spec Kit.


Tarea: Landing, Registro de cuenta e Inicio de sesión. Esta es la **spec 1 de la tarea (solo frontend)**.
Las specs siguientes (backend `/registro` y `/login`, persistencia en BD, contraseñas con hash y pruebas con
Postman) se definen después y deben respetar el contrato de este documento.

Rama: `frontend`. Código: `landing/` (React 18 + Vite 5 + React Router 6).
Diseño de referencia: Final Designs de Figma ("Landing TechFix.AI", "Registro de Cuenta", "Iniciar Sesión",
"Recuperar Contraseña" del Portal de Cliente).

## Alcance

| Ruta | Pantalla |
| --- | --- |
| `/` | Landing |
| `/portal/registro` | Registro de cuenta de cliente |
| `/portal/acceso` | Inicio de sesión del cliente |
| `/portal/recuperar` | Recuperar contraseña |
| `/portal/restablecer?token=…` | Restablecer contraseña (destino del enlace enviado por correo; no estaba en Figma) |

Fuera de alcance: backend, base de datos, hash, envío real de correos. Las demás pantallas del portal y del
taller ya existentes en la rama se conservan, pero no forman parte de esta spec.

## Navegación

- Landing: "Iniciar sesión" → `/portal/acceso`; "Ver TechFix.AI en acción" → ruta protegida (pide acceso).
- Acceso ↔ registro ↔ recuperación enlazados entre sí.
- Una ruta protegida sin sesión redirige a `/portal/acceso` y, tras ingresar, vuelve a la ruta solicitada.
- Registro exitoso abre sesión y lleva a `/portal/tickets`.
- Con sesión abierta, acceso y registro redirigen al área del usuario y la landing muestra "Ir a mi portal"
  (o "Ir al panel" para el taller) en lugar de "Iniciar sesión".
- Recuperación → enlace con `token` → restablecer → acceso. Sin token, o con token inválido o vencido, se
  muestra "Enlace no válido" con la opción de pedir uno nuevo.

## Validación en el cliente

Registro:
- Nombre y apellido: mínimo 3 caracteres.
- Correo: formato válido; se envía recortado y en minúsculas.
- Teléfono: 9 dígitos; se envía en E.164 con el prefijo elegido (`+51987654321`).
- Contraseña: mínimo 8 caracteres, una mayúscula, un número y un símbolo; indicador de seguridad en vivo.
- Confirmación igual a la contraseña. Aceptación de términos obligatoria.

Inicio de sesión: correo con formato válido y contraseña no vacía (la política se valida solo al registrarse).
Recuperación: correo con formato válido; la respuesta no revela si el correo existe.
Restablecimiento: misma política de contraseña que el registro y confirmación igual.

## Contrato con el backend (para las specs siguientes)

Base: `VITE_API_URL`. Sin definir, el frontend usa un simulador local (modo demostración).
Todas las peticiones: `POST`, JSON, `credentials: "include"`.

| Endpoint | Cuerpo | Éxito | Errores esperados |
| --- | --- | --- | --- |
| `/registro` | `{ nombre, email, telefono, password }` | `201 { usuario: { id, nombre, email } }` | `409` correo duplicado; `400/422` datos inválidos (opcional `field`) |
| `/login` | `{ email, password }` | `200 { usuario: { id, nombre, email } }` + cookie de sesión HttpOnly | `401` credenciales incorrectas; `429` demasiados intentos |
| `/recuperar` | `{ email }` | `200` siempre (no revela existencia); envía enlace `/portal/restablecer?token=…` válido 15 min | `429` |
| `/restablecer` | `{ token, password }` | `200`; el token queda invalidado | `400/410` token inválido, vencido o ya usado |

Mensajes que muestra el frontend: 409 → error en el campo correo; 401 → "Correo o contraseña incorrectos";
5xx o red → mensaje genérico, nunca el texto del servidor.

## Seguridad

- El frontend nunca guarda contraseñas ni tokens. La sesión del navegador solo guarda rol, nombre y correo.
- El hash de la contraseña es responsabilidad del backend (spec siguiente).
- No se registran en consola ni en trazas contraseñas, cuerpos de petición ni textos de excepción.

## Criterios de aceptación

1. Las pantallas reproducen los diseños de Figma y son usables de 390 px a 1440 px sin scroll horizontal.
2. Los formularios muestran errores por campo, estado de carga y error general.
3. El contrato de peticiones está cubierto por pruebas automáticas.
4. `npm --prefix landing test` y `npm --prefix landing run build` terminan sin errores.

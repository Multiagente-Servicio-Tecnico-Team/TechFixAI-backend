/*
 * Cliente del chat del portal: POST /api/chat del patrón LangGraph.
 *
 * - Con VITE_CHAT_URL definido llama al patrón; la identidad la da la cookie del inicio de sesión
 *   (credentials: "include"). El cuerpo nunca lleva correo ni identificador del cliente.
 * - Sin VITE_CHAT_URL el asistente sigue en modo demostración.
 */

export class ChatError extends Error {
  constructor(message, { status = 0, code = "error" } = {}) {
    super(message);
    this.name = "ChatError";
    this.status = status;
    this.code = code;
  }
}

export const CHAT_MESSAGES = {
  session: "Tu sesión terminó. Inicia sesión otra vez para seguir conversando.",
  customerOnly: "El chat es para clientes. Ingresa con una cuenta de cliente.",
  notFound: "Esta conversación ya no está disponible. Empieza una nueva.",
  noQuote: "Este presupuesto ya fue respondido.",
  patternLocked: "Para cambiar de patrón, inicia una conversación nueva.",
  tooMany: "Enviaste muchos mensajes seguidos. Espera un minuto y vuelve a intentar.",
  invalid: "Revisa el mensaje: no puede estar vacío ni superar 2000 caracteres.",
  unavailable: "El asistente no está disponible en este momento. Inténtalo de nuevo.",
};

function toChatError(status, data) {
  if (status === 401) return new ChatError(CHAT_MESSAGES.session, { status, code: "session_required" });
  if (status === 403) return new ChatError(CHAT_MESSAGES.customerOnly, { status, code: "customer_only" });
  if (status === 404) return new ChatError(CHAT_MESSAGES.notFound, { status, code: "not_found" });
  if (status === 409) {
    const code = data?.code === "pattern_locked" ? "pattern_locked" : "no_quote";
    return new ChatError(CHAT_MESSAGES[code === "pattern_locked" ? "patternLocked" : "noQuote"], { status, code });
  }
  if (status === 422) return new ChatError(CHAT_MESSAGES.invalid, { status, code: "invalid" });
  if (status === 429) return new ChatError(CHAT_MESSAGES.tooMany, { status, code: "rate_limited" });
  return new ChatError(CHAT_MESSAGES.unavailable, { status, code: data?.code || "unavailable" });
}

export function createChatApi({ baseUrl = "", fetchImpl } = {}) {
  const base = baseUrl.replace(/\/+$/, "");
  const doFetch = fetchImpl ?? ((...args) => globalThis.fetch(...args));

  return {
    mode: base ? "api" : "mock",
    async sendMessage({
      conversationId = null,
      message = null,
      action = null,
      proposalId = null,
      pattern = "hierarchical",
    }) {
      let res;
      try {
        res = await doFetch(`${base}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          credentials: "include",
          body: JSON.stringify({ conversation_id: conversationId, message, action, pattern,
            ...(proposalId ? { proposal_id: proposalId } : {}) }),
        });
      } catch {
        throw new ChatError(CHAT_MESSAGES.unavailable, { code: "network" });
      }
      let data = null;
      try {
        data = await res.json();
      } catch {
        data = null;
      }
      if (!res.ok) throw toChatError(res.status, data);
      return data;
    },
  };
}

export const chatApi = createChatApi({ baseUrl: import.meta.env?.VITE_CHAT_URL ?? "" });

/** Estados de ticket del script de BD -> texto para el cliente. */
export const TICKET_STATUS_LABEL = {
  NEW: "Recibido",
  IN_DIAGNOSIS: "En diagnóstico",
  QUOTED: "Presupuesto enviado",
  IN_REPAIR: "En reparación",
  READY_FOR_PICKUP: "Listo para retiro",
  DELIVERED: "Entregado",
  CANCELLED: "Cancelado",
};

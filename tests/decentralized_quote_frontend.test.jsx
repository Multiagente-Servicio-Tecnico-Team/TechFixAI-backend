import { describe, expect, it, vi } from "../landing/node_modules/vitest/dist/index.js";
import { render, screen } from "../landing/node_modules/@testing-library/react/dist/index.js";
import userEvent from "../landing/node_modules/@testing-library/user-event/dist/esm/index.js";
import { MemoryRouter } from "../landing/node_modules/react-router-dom/dist/index.js";
import LiveChat from "../landing/src/pages/portal/LiveChat.jsx";
import { StoreProvider } from "../landing/src/data/store.jsx";
import { createChatApi } from "../landing/src/api/chat.js";

const quote = (id) => ({ proposal_id: id, status: "proposed", currency: "PEN", total: "360.00",
  lines: [{ label: "SSD × 2", amount: "360.00" }] });

function mount(api) {
  sessionStorage.setItem("techfix.session", JSON.stringify({ role: "client", name: "Cliente sintético", email: "fixture@example.test" }));
  return render(<MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
    <StoreProvider><LiveChat api={api} /></StoreProvider>
  </MemoryRouter>);
}

describe("identidad de propuestas descentralizadas", () => {
  it("transporta proposal_id y cookie sin aceptar importes o identidad financiera", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ reply: "Aceptada" }) });
    const api = createChatApi({ baseUrl: "http://fixture.test", fetchImpl });
    await api.sendMessage({ conversationId: "conversation", action: "accept_quote", pattern: "decentralized", proposalId: "version-a" });
    const options = fetchImpl.mock.calls[0][1];
    expect(options.credentials).toBe("include");
    expect(JSON.parse(options.body)).toEqual({ conversation_id: "conversation", message: null,
      action: "accept_quote", pattern: "decentralized", proposal_id: "version-a" });
  });

  it.each(["accept_quote", "reject_quote"])("el botón %s identifica la tarjeta presentada", async (action) => {
    const user = userEvent.setup();
    const api = { sendMessage: vi.fn()
      .mockResolvedValueOnce({ conversation_id: "conversation", reply: "Propuesta", quote: quote("version-a") })
      .mockResolvedValueOnce({ conversation_id: "conversation", reply: "Procesada" }) };
    mount(api);
    await user.type(screen.getByLabelText("Mensaje"), "Cotiza los SSD{Enter}");
    await screen.findByText("Propuesta");
    await user.click(screen.getByRole("button", { name: action === "accept_quote" ? /Confirmar y guardar/ : /No guardar/ }));
    expect(api.sendMessage).toHaveBeenLastCalledWith({ conversationId: "conversation", pattern: "decentralized",
      action, proposalId: "version-a" });
  });

  it("deshabilita la tarjeta anterior y transmite exclusivamente la versión nueva", async () => {
    const user = userEvent.setup();
    const api = { sendMessage: vi.fn()
      .mockResolvedValueOnce({ conversation_id: "conversation", reply: "Primera", quote: quote("version-a") })
      .mockResolvedValueOnce({ conversation_id: "conversation", reply: "Actualizada", quote: quote("version-b") })
      .mockResolvedValueOnce({ conversation_id: "conversation", reply: "Aceptada" }) };
    mount(api);
    await user.type(screen.getByLabelText("Mensaje"), "Cotiza{Enter}");
    await screen.findByText("Primera");
    await user.type(screen.getByLabelText("Mensaje"), "Cambia cantidad{Enter}");
    await screen.findByText("Actualizada");
    expect(screen.getAllByRole("button", { name: /Confirmar y guardar/ })).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: /Confirmar y guardar/ }));
    expect(api.sendMessage).toHaveBeenLastCalledWith({ conversationId: "conversation", pattern: "decentralized",
      action: "accept_quote", proposalId: "version-b" });
  });

  it("no agrega proposal_id al contrato de los patrones existentes", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    const api = createChatApi({ baseUrl: "http://fixture.test", fetchImpl });
    await api.sendMessage({ conversationId: "c", action: "accept_quote", pattern: "hierarchical" });
    expect(JSON.parse(fetchImpl.mock.calls[0][1].body)).toEqual({ conversation_id: "c", message: null,
      action: "accept_quote", pattern: "hierarchical" });
  });
});

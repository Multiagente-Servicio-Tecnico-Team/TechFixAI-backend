"""Chat local de varios turnos. Ejecutar explícitamente: python probar_chat.py.

Usa Groq y puede consultar RAG/PostgreSQL; no ejecutar como prueba aislada.
"""

import re


def mostrar_diagnostico(result):
    """Solo metadatos: nunca mensajes, argumentos ni textos de excepciones."""
    agents = {"soporte", "tecnico", "almacen", "ventas"}
    for handoff in result.get("handoff_history", []):
        origin, target = handoff.get("origen"), handoff.get("destino")
        if origin in agents and target in agents:
            print(f"[Transferencia: {origin} → {target}]")
    for error in result.get("errors", []):
        match = re.fullmatch(r"Error en el agente (Soporte|Técnico|Ventas|Almacén): ([A-Za-z_][A-Za-z_0-9]*)", error)
        if match:
            print(f"[Diagnóstico: {match[1]} / {match[2]}]")
        else:
            print("[Diagnóstico: error controlado del flujo]")


def main():
    from app.agents.decentralized.conversation import Conversation
    from app.agents.decentralized.graph import graph

    conversation = Conversation(graph)
    print("Escribe /salir para terminar o /nuevo para iniciar otra consulta.")
    new_request = False
    while True:
        try:
            text = input("Tú: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text == "/salir":
            break
        if text == "/nuevo":
            new_request = True
            print("La próxima pregunta iniciará una consulta nueva.")
            continue
        if not text:
            continue
        try:
            result = conversation.send(text, new_request=new_request)
        except Exception as exc:
            print("No se pudo completar el turno. Puedes volver a intentarlo.")
            print(f"[Diagnóstico: {type(exc).__name__}]")
            continue
        new_request = False
        mostrar_diagnostico(result)
        print(f"{result.get('current_agent', 'asistente')}: {result['messages'][-1].content}")


if __name__ == "__main__":
    main()

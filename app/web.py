import streamlit as st
from langchain_core.messages import HumanMessage

from app.agents.orquestador import build_graph, new_thread_id
from app.database.repository import find_user_by_email


st.set_page_config(page_title="TechFix | Prueba de agentes", layout="centered")
st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] { background: #f4f6f2; color: #18322e; }
    [data-testid="stHeader"] { background: transparent; }
    [data-testid="stAppViewContainer"] h1,
    [data-testid="stAppViewContainer"] p,
    [data-testid="stAppViewContainer"] label { color: #18322e !important; }
    [data-testid="stAppViewContainer"] h1 { font-size: 2rem; }
    [data-testid="stTextInput"] input { background: #fff; color: #18322e; }
    [data-testid="stButton"] button { background: #153c39; color: #fff; }
    [data-testid="stChatMessage"] { border-radius: 8px; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def _agent_graph():
    return build_graph()


st.title("Prueba del agente técnico")
st.caption("Taller · diagnóstico y cotización provisional")

if "user_id" not in st.session_state:
    with st.form("identify_user"):
        email = st.text_input("Correo de un usuario activo")
        submitted = st.form_submit_button("Continuar")

    if submitted:
        if not email.strip():
            st.error("Ingresa el correo para continuar.")
        else:
            try:
                user = find_user_by_email(email)
            except Exception as error:
                st.error(f"No se pudo consultar la base de datos ({type(error).__name__}).")
            else:
                if user is None:
                    st.error("No encontramos un usuario activo con ese correo.")
                else:
                    st.session_state.user_id = user["id"]
                    st.session_state.user_name = user.get("name", "Cliente")
                    st.session_state.thread_id = new_thread_id()
                    st.session_state.chat_history = [
                        {
                            "role": "assistant",
                            "content": (
                                f"Hola, {st.session_state.user_name}. Soy TechFix Copilot. "
                                "Puedo orientarte con soporte y reparaciones, consultar componentes y cotizaciones, "
                                "ayudarte a armar una PC según tu presupuesto y resolver consultas de garantía "
                                "o logística. ¿Qué necesitas hoy? Antes de guardar un ticket o cotización, "
                                "te mostraré el resumen y esperaré tu confirmación."
                            ),
                        }
                    ]
                    st.rerun()
else:
    with st.sidebar:
        st.write(f"Usuario: {st.session_state.user_name}")
        if st.button("Cerrar sesión"):
            for key in ("user_id", "user_name", "thread_id", "chat_history"):
                st.session_state.pop(key, None)
            st.rerun()

    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = st.chat_input("Describe la falla del equipo")
    if prompt:
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        try:
            with st.spinner("Analizando el caso y consultando inventario..."):
                result = _agent_graph().invoke(
                    {
                        "messages": [HumanMessage(content=prompt)],
                        "user_id": st.session_state.user_id,
                    },
                    {
                        "configurable": {"thread_id": st.session_state.thread_id},
                        "run_name": "prueba-agente-soporte",
                        "tags": ["prototipo-web"],
                    },
                )
        except Exception as error:
            st.error(f"No se pudo completar la consulta ({type(error).__name__}).")
        else:
            response = result.get("response", "No se recibió respuesta del agente.")
            st.session_state.chat_history.append({"role": "assistant", "content": response})
            with st.chat_message("assistant"):
                st.markdown(response)
            if result.get("quote_id") or result.get("ticket_cancelled"):
                st.session_state.thread_id = new_thread_id()

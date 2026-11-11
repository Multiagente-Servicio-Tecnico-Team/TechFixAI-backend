"""Aislamiento de toda la suite: nada de servicios externos aunque exista el .env del desarrollador.

`app.main.create_app` llama a `load_dotenv(override=False)`. Fijar estas variables antes evita que el
.env active el trazado de LangChain/LangSmith y que las pruebas envíen ejecuciones a un servicio real.
"""
import os

for name, value in {
    "LANGSMITH_TRACING": "false",
    "LANGCHAIN_TRACING_V2": "false",
    "LANGCHAIN_TRACING": "false",
    "LANGSMITH_API_KEY": "",
    "LANGCHAIN_API_KEY": "",
}.items():
    os.environ[name] = value

from langchain_core.tools import tool

from app.rag.retriever import retrieve_documents


@tool
def consultar_base_conocimiento(consulta: str) -> str:
    """Consulta la base de conocimiento del servicio técnico."""

    documentos = retrieve_documents(
        consulta,
        limit=2,
    )

    if not documentos:
        return "No se encontró información relevante."

    resultados = []

    for documento in documentos:
        fuente = documento.source_path or documento.source_id

        resultados.append(
            f"Fuente: {fuente} (confianza: {documento.trust_level}; "
            f"área: {documento.area}; sección: {documento.section or documento.title or 'sin título'})\n"
            f"{documento.content}"
        )

    return "\n\n".join(resultados)


if __name__ == "__main__":
    resultado = consultar_base_conocimiento.invoke(
        {
            "consulta": "¿Qué revisar si una computadora no enciende?"
        }
    )

    print(resultado)

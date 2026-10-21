from app.agents.jerarquico.agents.faq import MarkdownFaqRetriever


def test_faq_retriever_selects_topic_for_natural_questions():
    retriever = MarkdownFaqRetriever()
    cases = {
        "tengo una consulta que funciones puedes realizar": "Servicios disponibles",
        "donde queda la tienda": "Ubicación de la tienda",
        "cual es el horario de atencion": "Horario de atención",
        "que medios de pago aceptan": "Pagos",
        "cuales son los metodos de pago": "Pagos",
        "como funciona el proceso de compra": "Proceso de atención y compra",
        "como consulto mi garantia": "Garantía",
        "puedo recoger mi equipo presencialmente": "Retiro y envío",
        "tienen RAM disponible": "Compras y disponibilidad",
    }

    for question, expected_heading in cases.items():
        context = retriever.retrieve(question, limit=1)
        assert expected_heading in context, question


def test_faq_retriever_provides_store_address_and_opening_hours():
    retriever = MarkdownFaqRetriever()
    location = retriever.retrieve("donde esta el local", limit=1).casefold()
    hours = retriever.retrieve("cuando abren", limit=1).casefold()

    assert "sí, contamos con tienda física" in location
    assert "av. los talleres 450, san borja, lima, perú" in location
    assert "lunes a viernes de 09:00 a 18:00" in hours
    assert "sábados de 09:00 a 13:00" in hours


def test_faq_explains_payment_process_fees_and_warranty_duration():
    retriever = MarkdownFaqRetriever()
    payment = retriever.retrieve("que formas de pago aceptan", limit=1).casefold()
    process = retriever.retrieve("como funciona el proceso de compra", limit=1).casefold()
    warranty = retriever.retrieve("cuanto dura la garantia de un armado", limit=1).casefold()
    fees = retriever.retrieve("cuanto cuesta el diagnostico y armado", limit=1).casefold()

    assert all(method in payment for method in ("yape", "plin", "visa", "efectivo"))
    assert "pendiente" in process and "aceptación explícita" in process
    assert "3 meses" in warranty
    assert "s/ 50.00" in fees and "s/ 35.00" in fees

from app.agents.jerarquico.agents.faq import MarkdownFaqRetriever
import unicodedata


def normalize(text):
    return "".join(
        char for char in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(char)
    )


def test_faq_retriever_selects_topic_for_natural_questions():
    retriever = MarkdownFaqRetriever()
    cases = {
        "tengo una consulta que funciones puedes realizar": "Servicios disponibles",
        "donde queda la tienda": "Ubicacion de la tienda",
        "cual es el horario de atencion": "Horario de atencion",
        "que medios de pago aceptan": "Pagos",
        "como funciona el proceso de compra": "Proceso de atencion y compra",
        "como consulto mi garantia": "Garantia",
        "puedo recoger mi equipo presencialmente": "Retiro y envio",
        "tienen RAM disponible": "Compras y disponibilidad",
    }
    for question, expected_heading in cases.items():
        context = retriever.retrieve(question, limit=1)
        assert normalize(expected_heading) in normalize(context), question
        assert "fuente demostrativa" in context.casefold()


def test_faq_demo_address_and_hours_are_never_unlabelled():
    retriever = MarkdownFaqRetriever()
    location = retriever.retrieve("donde esta el local", limit=1).casefold()
    hours = retriever.retrieve("cuando abren", limit=1).casefold()
    assert "fuente demostrativa" in location and "av. los talleres 450" in location
    assert "fuente demostrativa" in hours and "09:00 a 18:00" in hours


def test_faq_demo_payment_prices_and_warranty_keep_provenance():
    retriever = MarkdownFaqRetriever()
    for question in (
        "que formas de pago aceptan",
        "como funciona el proceso de compra",
        "cuanto dura la garantia de un armado",
        "cuanto cuesta el diagnostico y armado",
    ):
        context = retriever.retrieve(question, limit=1)
        assert "fuente demostrativa" in context.casefold()

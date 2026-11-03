from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from langchain_core.messages import HumanMessage

from app.agents.jerarquico.agents.logistics import LogisticsDecision
from app.agents.jerarquico.agents.warranty import make_warranty_agent
from app.agents.jerarquico.graph.builder import build_multiagent_graph
from app.agents.jerarquico.graph.routing import after_knowledge_retrieval
from app.agents.jerarquico.supervisor import _catalog_search_term
from app.agents.jerarquico.schemas import (
    IntakeDecision,
    PartRequest,
    QuoteConfirmation,
)
from app.settings import Settings


class FakeSaleModel:
    def __init__(
        self,
        route="sale",
        *,
        search_term="Mouse Gamer",
        budget_max=Decimal("3000"),
        intended_use="juegos",
        part_requests=None,
    ):
        self.route = route
        self.search_term = search_term
        self.budget_max = budget_max
        self.intended_use = intended_use
        self.part_requests = part_requests
        self.quote_response = QuoteConfirmation(decision="confirm")

    def with_structured_output(self, schema, *, method="function_calling"):
        del method
        model = self

        class Result:
            def invoke(self, _messages):
                if schema is IntakeDecision:
                    return IntakeDecision(
                        route=model.route,
                        request_type="SALE" if model.route == "sale" else "PC_BUILD",
                        title="Compra de prueba",
                        failure_description="Solicitud comercial de prueba",
                        required_parts=(
                            model.part_requests
                            or [PartRequest(search_term=model.search_term, quantity=2)]
                        ) if model.route == "sale" else [],
                        budget_max=(
                            model.budget_max if model.route == "pc_build" else None
                        ),
                        intended_use=(
                            model.intended_use if model.route == "pc_build" else None
                        ),
                        informational_response=(
                            "No dispongo de datos confirmados sobre la dirección, horarios ni disponibilidad de la tienda física."
                            if model.route == "informational"
                            else None
                        ),
                    )
                if schema is QuoteConfirmation:
                    return model.quote_response
                if schema is LogisticsDecision:
                    return LogisticsDecision(mode="PHYSICAL_STORE")
                raise AssertionError(f"Unexpected schema: {schema}")

        return Result()

    def invoke(self, _messages):
        return SimpleNamespace(content="Respuesta FAQ de prueba.")


class FakeCommercialRepository:
    def __init__(self):
        self.created_ticket = None
        self.saved_order = None
        self.logistics = None
        self.warranties = []
        self.catalog_searches = []

    def find_customer(self, _email):
        return {"id": 12}

    def create_intake_ticket(self, **values):
        self.created_ticket = values
        return 41

    def find_spare_parts(self, _search_term):
        return [
            {
                "id": 7,
                "code": "MOU-001",
                "name": "Mouse Gamer Logitech",
                "unit_price": Decimal("24.50"),
                "current_stock": 5,
            }
        ]

    def find_catalog_items(self, search_term, *, limit=20):
        del limit
        self.catalog_searches.append(search_term)
        if "ram" in search_term.casefold():
            return [
                {
                    "id": 8,
                    "code": "RAM-D4-16GB-3200-CRU",
                    "name": "Memoria RAM DDR4 16GB Crucial",
                    "category": "RAM Desktop",
                    "unit_price": Decimal("45.00"),
                    "current_stock": 20,
                },
                {
                    "id": 9,
                    "code": "RAM-D4-16GB-3200-KIN",
                    "name": "Memoria RAM DDR4 16GB Kingston",
                    "category": "RAM Desktop",
                    "unit_price": Decimal("48.00"),
                    "current_stock": 10,
                },
            ]
        if "ssd" in search_term.casefold():
            return [
                {
                    "id": 18,
                    "code": "SSD-240-CRU",
                    "name": "SSD SATA 2.5 pulgadas 240GB Crucial",
                    "category": "Almacenamiento",
                    "unit_price": Decimal("25.00"),
                    "current_stock": 7,
                },
                {
                    "id": 19,
                    "code": "SSD-240-KIN",
                    "name": "SSD SATA 2.5 pulgadas 240GB Kingston",
                    "category": "Almacenamiento",
                    "unit_price": Decimal("25.00"),
                    "current_stock": 7,
                },
            ]
        if "procesador" in search_term.casefold():
            processors = [
                ("CPU-I5-12400F", "Intel Core i5-12400F", "145.00", 12),
                ("CPU-I5-13400F", "Intel Core i5-13400F", "210.00", 5),
                ("CPU-I5-14400", "Intel Core i5-14400", "230.00", 5),
            ]
            if "13" in search_term:
                processors = [processors[1]]
            return [
                {
                    "id": 40 + index,
                    "code": code,
                    "name": name,
                    "category": "Procesador",
                    "unit_price": Decimal(price),
                    "current_stock": stock,
                }
                for index, (code, name, price, stock) in enumerate(processors)
            ]
        return [
            {
                "id": 7,
                "code": "MOU-001",
                "name": "Mouse Gamer Logitech",
                "category": "Periféricos",
                "unit_price": Decimal("24.50"),
                "current_stock": 5,
            }
        ]

    def find_spare_part_by_code(self, code):
        for item in self.find_catalog_items("RAM"):
            if item["code"] == code:
                return item
        code_to_item = {
            "CPU-AMD-R5-5600": ("Procesador", "AMD Ryzen 5 5600", "115.00"),
            "CPU-AMD-R5-5600G": ("Procesador", "AMD Ryzen 5 5600G", "125.00"),
            "MB-ASUS-B550-PLUS": ("Placa Madre", "ASUS TUF B550-PLUS", "135.00"),
            "RAM-D4-32GB-3600-COR": (
                "RAM Desktop", "Corsair Vengeance DDR4 32GB", "95.00"
            ),
            "GPU-ASUS-RTX3050-8G": (
                "Tarjeta de Video", "ASUS GeForce RTX 3050 8GB", "225.00"
            ),
            "SSD-M2-NVME-1TB": ("Almacenamiento", "SSD M.2 NVMe 1TB", "75.00"),
            "COOL-AIR-AG400-BK": (
                "Refrigeración PC", "Disipador CPU DeepCool AG400", "28.00"
            ),
            "PSU-COOLERMASTER-650-Gold": (
                "Fuente de Poder", "Cooler Master 650W Gold", "92.00"
            ),
            "CASE-COR-4000D-AIR": (
                "Gabinete", "Corsair 4000D AIRFLOW ATX", "105.00"
            ),
            "CPU-AMD-R5-5600X": ("Procesador", "AMD Ryzen 5 5600X", "155.00"),
            "RAM-D-DDR4-3200-16-CRU": (
                "RAM Desktop", "RAM Desktop DDR4 16GB Crucial", "38.40"
            ),
            "GPU-MSI-GTX1650-4G": (
                "Tarjeta de Video", "MSI GeForce GTX 1650 4GB", "155.00"
            ),
            "SSD-M2-NVME-500GB": (
                "Almacenamiento", "SSD M.2 NVMe 500GB Kingston", "42.00"
            ),
            "CASE-MSI-FORGE-100R": (
                "Gabinete", "MSI MAG FORGE 100R ATX", "72.00"
            ),
            "RAM-D-DDR4-3600-32-CVL": (
                "RAM Desktop", "RAM Desktop DDR4 32GB Corsair Vengeance", "82.80"
            ),
            "GPU-GIGA-RTX3060-12G": (
                "Tarjeta de Video", "Gigabyte RTX 3060 12GB", "295.00"
            ),
            "SSD-NVME-KINGSTON-NV2-1000": (
                "Almacenamiento", "SSD M.2 NVMe 1TB Kingston", "68.00"
            ),
            "PSU-CORSAIR-750-Gold": (
                "Fuente de Poder", "Corsair 750W Gold", "125.00"
            ),
            "SSD-240-CRU": (
                "Almacenamiento", "SSD SATA 2.5 pulgadas 240GB Crucial", "25.00"
            ),
            "SSD-240-KIN": (
                "Almacenamiento", "SSD SATA 2.5 pulgadas 240GB Kingston", "25.00"
            ),
        }
        item = code_to_item.get(code)
        if not item:
            return None
        category, name, price = item
        return {
            "id": 100 + len(code),
            "code": code,
            "name": name,
            "category": category,
            "unit_price": Decimal(price),
            "current_stock": 5,
        }

    def accept_ticket_quote(self, **values):
        self.saved_order = values
        return {
            "quote_id": 51,
            "payment_id": 61,
            "payment_code": "PAY-TEST",
            "payment_status": "PENDING",
        }

    def cancel_ticket(self, _ticket_id, _customer_id):
        raise AssertionError("The test accepts the proposal.")

    def create_logistics_record(self, **values):
        self.logistics = values
        return 71

    def create_order_warranty(self, **values):
        self.warranties.append(values)
        return {"id": 81, "warranty_code": values["warranty_code"]}


def make_settings():
    return Settings(
        groq_api_key="test-key",
        groq_model="test-model",
        database_url="postgresql://unused",
        langsmith_api_key=None,
        langsmith_tracing=False,
        langsmith_project="tests",
        langsmith_hide_inputs=True,
        langsmith_hide_outputs=True,
        labor_maintenance_price=Decimal("40.00"),
        labor_diagnosis_price=Decimal("50.00"),
        labor_pc_build_price=Decimal("50.00"),
    )


def test_direct_sale_queries_catalog_and_creates_payment_only_after_acceptance():
    repository = FakeCommercialRepository()
    graph = build_multiagent_graph(
        settings=make_settings(),
        repository=repository,
        model=FakeSaleModel(),
    )
    config = {"configurable": {"thread_id": "sale-flow"}}

    proposal = graph.invoke(
        {
            "messages": [
                HumanMessage(content="Quiero comprar dos mouse gamer.")
            ],
            "customer_id": 12,
        },
        config=config,
    )

    assert proposal["outcome"] == "awaiting_confirmation"
    assert proposal["quote_type"] == "DIRECT_SALE"
    assert proposal["quote"]["labor_cost"] == Decimal("0.00")
    assert proposal["quote"]["total_amount"] == Decimal("49.00")
    assert repository.created_ticket["request_type"] == "SALE"
    assert repository.saved_order is None

    accepted = graph.invoke(
        {"messages": [HumanMessage(content="Sí, acepto")]},
        config=config,
    )

    assert accepted["outcome"] == "quoted"
    assert accepted["ticket_status"] == "PAYMENT_PENDING"
    assert accepted["payment_code"] == "PAY-TEST"
    assert repository.saved_order["quote_type"] == "DIRECT_SALE"
    assert repository.saved_order["parts"][0]["subtotal"] == Decimal("49.00")
    assert "PENDIENTE" in accepted["messages"][-1].content

    logistics = graph.invoke(
        {"messages": [HumanMessage(content="Lo recojo en tienda")]},
        config=config,
    )

    assert logistics["outcome"] == "order_completed"
    assert repository.logistics["mode"] == "PHYSICAL_STORE"
    assert logistics["warranty_code"].startswith("WAR-")


def test_pc_build_quotes_a_curated_profile_and_registers_warranty_after_logistics():
    repository = FakeCommercialRepository()
    graph = build_multiagent_graph(
        settings=make_settings(),
        repository=repository,
        model=FakeSaleModel(route="pc_build"),
    )

    options = graph.invoke(
        {
            "messages": [
                HumanMessage(
                    content="Quiero armar una PC para juegos con S/ 3,000."
                )
            ],
            "customer_id": 12,
        },
        config={"configurable": {"thread_id": "pc-build-flow"}},
    )

    assert options["outcome"] == "awaiting_build_selection"
    assert len(options["build_options"]) == 3
    assert "PC gamer económica" in options["messages"][-1].content
    assert "PC de entrada para juegos" in options["messages"][-1].content
    assert "PC gamer de mayor rendimiento" in options["messages"][-1].content

    result = graph.invoke(
        {"messages": [HumanMessage(content="elijo la 3")]},
        config={"configurable": {"thread_id": "pc-build-flow"}},
    )
    assert result["outcome"] == "awaiting_confirmation"
    assert result["build_profile_id"] == "gaming-rendimiento"
    assert result["quote"]["total_amount"] == Decimal("1043.80")
    assert "GPU" in result["messages"][-1].content or "Tarjeta de Video" in result["messages"][-1].content

    accepted = graph.invoke(
        {"messages": [HumanMessage(content="Sí, acepto")]},
        config={"configurable": {"thread_id": "pc-build-flow"}},
    )
    assert accepted["outcome"] == "quoted"
    assert accepted["payment_code"] == "PAY-TEST"

    completed = graph.invoke(
        {"messages": [HumanMessage(content="Lo recojo en tienda")]},
        config={"configurable": {"thread_id": "pc-build-flow"}},
    )
    assert completed["outcome"] == "order_completed"
    assert completed["warranty_code"].startswith("WAR-")
    assert repository.warranties[0]["warranty_months"] == 3
    assert "pendiente" in completed["messages"][-1].content
    assert "Gracias por tu preferencia" in completed["messages"][-1].content


def test_sale_category_search_uses_name_selection_without_exposing_sku():
    repository = FakeCommercialRepository()
    graph = build_multiagent_graph(
        settings=make_settings(),
        repository=repository,
        model=FakeSaleModel(search_term="RAM"),
    )
    config = {"configurable": {"thread_id": "ram-choice-flow"}}

    options = graph.invoke(
        {
            "messages": [HumanMessage(content="Quiero comprar una RAM.")],
            "customer_id": 12,
        },
        config=config,
    )
    assert options["outcome"] == "awaiting_inventory_selection"
    assert "Crucial" in options["messages"][-1].content
    assert "Kingston" in options["messages"][-1].content
    assert "RAM-D4" not in options["messages"][-1].content

    selected = graph.invoke(
        {"messages": [HumanMessage(content="la segunda")]},
        config=config,
    )
    assert selected["outcome"] == "awaiting_confirmation"
    assert selected["quote"]["parts"][0]["name"] == "Memoria RAM DDR4 16GB Kingston"
    assert "RAM-D4" not in selected["messages"][-1].content


def test_multi_item_sale_keeps_pending_queue_and_selects_ram_then_ssd_brand():
    repository = FakeCommercialRepository()
    model = FakeSaleModel(
        route="sale",
        part_requests=[
            PartRequest(search_term="RAM 8GB", quantity=1),
            PartRequest(search_term="SSD 240GB", quantity=1),
        ],
    )
    graph = build_multiagent_graph(
        settings=make_settings(), repository=repository, model=model
    )
    config = {"configurable": {"thread_id": "multi-item-brand-selection"}}
    ram_options = graph.invoke(
        {
            "messages": [HumanMessage(content="Quiero RAM de 8GB y SSD de 240GB")],
            "customer_id": 12,
        },
        config=config,
    )
    assert ram_options["outcome"] == "awaiting_inventory_selection"
    assert "Crucial" in ram_options["messages"][-1].content
    assert "Kingston" in ram_options["messages"][-1].content

    ssd_options = graph.invoke(
        {"messages": [HumanMessage(content="la segunda") ]}, config=config
    )
    assert ssd_options["outcome"] == "awaiting_inventory_selection"
    assert "SSD SATA" in ssd_options["messages"][-1].content
    assert "Crucial" in ssd_options["messages"][-1].content
    assert "Kingston" in ssd_options["messages"][-1].content

    quote = graph.invoke(
        {"messages": [HumanMessage(content="la primera") ]}, config=config
    )
    assert quote["outcome"] == "awaiting_confirmation"
    assert {part["category"] for part in quote["quote"]["parts"]} == {
        "RAM Desktop", "Almacenamiento"
    }
    assert len(quote["quote"]["parts"]) == 2
    assert "SSD-240" not in quote["messages"][-1].content


def test_capabilities_question_returns_supported_actions_not_store_details():
    graph = build_multiagent_graph(
        settings=make_settings(),
        repository=FakeCommercialRepository(),
        model=FakeSaleModel(route="informational"),
    )

    result = graph.invoke(
        {
            "messages": [HumanMessage(content="tengo una consulta que funciones puedes realizar?")],
            "customer_id": 12,
        },
        config={"configurable": {"thread_id": "capabilities-faq"}},
    )

    answer = result["messages"][-1].content.casefold()
    assert result["outcome"] == "informational"
    assert "diagnosticar" in answer and "hardware" in answer
    assert "cotizaci" in answer and "gaming" in answer
    assert "garant" in answer and "retiro presencial" in answer
    assert "dirección, horarios" not in answer


def test_processor_catalog_question_uses_live_inventory_instead_of_faq_response():
    repository = FakeCommercialRepository()
    graph = build_multiagent_graph(
        settings=make_settings(),
        repository=repository,
        model=FakeSaleModel(route="informational"),
    )

    result = graph.invoke(
        {
            "messages": [
                HumanMessage(
                    content=(
                        "¿Qu\u00e9 procesadores Intel Core i5 de 13.\u00aa "
                        "generaci\u00f3n aparecen en el cat\u00e1logo?"
                    )
                )
            ],
            "customer_id": 12,
        },
        config={"configurable": {"thread_id": "processor-catalog-flow"}},
    )

    assert result["outcome"] == "awaiting_confirmation"
    assert repository.catalog_searches == ["procesador i5 13"]
    assert "Intel Core i5-13400F" in result["messages"][-1].content
    assert "S/ 210.00" in result["messages"][-1].content
    assert "¿Aceptas esta propuesta?" in result["messages"][-1].content
    assert "i5-13500" not in result["messages"][-1].content


def test_ram_availability_question_uses_catalog_even_when_model_returns_faq():
    repository = FakeCommercialRepository()
    graph = build_multiagent_graph(
        settings=make_settings(),
        repository=repository,
        model=FakeSaleModel(route="informational"),
    )

    result = graph.invoke(
        {
            "messages": [HumanMessage(content="¿Tienen RAM disponible?")],
            "customer_id": 12,
        },
        config={"configurable": {"thread_id": "ram-availability-fallback"}},
    )

    assert result["outcome"] == "awaiting_inventory_selection"
    assert repository.catalog_searches == ["ram"]
    answer = result["messages"][-1].content
    assert "Crucial" in answer and "Kingston" in answer
    assert "RAM-D4" not in answer


def test_catalog_fallback_keeps_processor_generation_and_rejects_ambiguous_letter():
    assert (
        _catalog_search_term(
            "\u00bfQu\u00e9 procesadores Intel Core i5 de 13.\u00aa generaci\u00f3n hay?"
        )
        == "procesador i5 13"
    )
    assert _catalog_search_term("¿Tienen algún componente C?") is None


def test_technical_repair_and_support_route_to_domain_agents_with_rag():
    assert after_knowledge_retrieval(
        {"request_type": "REPAIR", "rag_context": "hardware RAG"}
    ) == "technical_support_agent"
    assert after_knowledge_retrieval(
        {"request_type": "SUPPORT", "rag_context": "software RAG"}
    ) == "software_support_agent"


def test_pc_build_ram_change_replaces_component_and_recalculates_quote():
    repository = FakeCommercialRepository()
    model = FakeSaleModel(route="pc_build")
    graph = build_multiagent_graph(
        settings=make_settings(),
        repository=repository,
        model=model,
    )
    config = {"configurable": {"thread_id": "pc-build-ram-change"}}
    initial = graph.invoke(
        {
            "messages": [
                HumanMessage(
                    content="Arma una PC para juegos, presupuesto S/ 3,000."
                )
            ],
            "customer_id": 12,
        },
        config=config,
    )
    assert initial["outcome"] == "awaiting_build_selection"
    initial = graph.invoke(
        {"messages": [HumanMessage(content="la segunda")]}, config=config
    )
    original_total = initial["quote"]["total_amount"]
    model.quote_response = QuoteConfirmation(
        decision="modify",
        modification_term="RAM Desktop 16GB",
        replacement_category="RAM Desktop",
    )
    options = graph.invoke(
        {"messages": [HumanMessage(content="Cambia la RAM a 16GB")]},
        config=config,
    )
    assert options["outcome"] == "awaiting_inventory_selection"
    assert "Kingston" in options["messages"][-1].content
    assert "RAM-D4" not in options["messages"][-1].content

    model.quote_response = QuoteConfirmation(decision="confirm")
    revised = graph.invoke(
        {"messages": [HumanMessage(content="la segunda")]},
        config=config,
    )
    assert revised["outcome"] == "awaiting_confirmation"
    assert revised["quote"]["total_amount"] != original_total
    assert [
        part["name"] for part in revised["quote"]["parts"]
        if part["category"] == "RAM Desktop"
    ] == ["Memoria RAM DDR4 16GB Kingston"]

    accepted = graph.invoke(
        {"messages": [HumanMessage(content="Sí, acepto esta versión")]},
        config=config,
    )
    assert accepted["outcome"] == "quoted"
    assert any(
        part["code"] == "RAM-D4-16GB-3200-KIN"
        for part in repository.saved_order["parts"]
    )


def test_pc_build_rejects_profile_above_budget_then_reuses_ticket_for_revision():
    repository = FakeCommercialRepository()
    model = FakeSaleModel(route="pc_build", budget_max=Decimal("500"))
    graph = build_multiagent_graph(
        settings=make_settings(),
        repository=repository,
        model=model,
    )
    config = {"configurable": {"thread_id": "pc-build-budget"}}
    over_budget = graph.invoke(
        {
            "messages": [
                HumanMessage(content="PC para juegos con máximo S/ 500.")
            ],
            "customer_id": 12,
        },
        config=config,
    )
    assert over_budget["outcome"] == "build_over_budget"
    assert over_budget["awaiting_build_budget"] is True
    assert repository.saved_order is None
    ticket_id = over_budget["ticket_id"]

    model.budget_max = Decimal("3000")
    revised = graph.invoke(
        {"messages": [HumanMessage(content="Puedo llegar a S/ 3,000.")]},
        config=config,
    )
    assert revised["outcome"] == "awaiting_build_selection"
    revised = graph.invoke(
        {"messages": [HumanMessage(content="la primera")]}, config=config
    )
    assert revised["outcome"] == "awaiting_confirmation"
    assert revised["ticket_id"] == ticket_id
    assert revised["quote"]["total_amount"] == Decimal("727.40")


def test_warranty_status_lookup_is_scoped_to_authenticated_customer():
    class WarrantyRepository:
        def find_warranty(self, _code):
            return {
                "id": 9,
                "customer_id": 12,
                "warranty_code": "WAR-TEST",
                "item_or_service_name": "Pantalla",
                "warranty_months": 3,
                "start_date": date(2026, 1, 1),
                "end_date": date(2026, 4, 1),
                "status": "ACTIVE",
                "not_expired": True,
            }

    agent = make_warranty_agent(WarrantyRepository())
    result = agent(
        {
            "messages": [HumanMessage(content="¿Sigue vigente?")],
            "request_type": "WARRANTY_STATUS_CHECK",
            "warranty_code": "WAR-TEST",
            "customer_id": 12,
        }
    )

    assert result["outcome"] == "warranty_status_checked"
    assert "vigente" in result["messages"][-1].content

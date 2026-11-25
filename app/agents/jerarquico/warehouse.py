from decimal import Decimal
import re
from typing import Any
from langchain_core.messages import AIMessage

from app.database.repository import ServiceRepository
from app.application.catalog import CatalogService
from app.agents.jerarquico.graph.state import ServiceState
from app.agents.jerarquico.trace import traced_tool


CATALOG_REFINEMENT_THRESHOLD = 8
_CATALOG_BRANDS = (
    "Western Digital", "Cooler Master", "Thermalright", "DeepCool",
    "TeamGroup", "G.Skill", "Kingston", "Crucial", "Corsair", "Samsung",
    "Gigabyte", "Seagate", "Adata", "Arctic", "Seasonic", "Logitech",
    "Intel", "AMD", "ASUS", "MSI", "EVGA", "Acer", "Dell", "Lenovo", "HP",
)


def _refinement_message(search_term: str, candidates: list[dict[str, Any]]) -> str:
    names = [" ".join(str(item.get(field) or "") for field in ("name", "category", "description")) for item in candidates]
    categories = sorted({str(item.get("category", "")).strip() for item in candidates if item.get("category")})
    capacities = sorted({match.group(0).replace(" ", "") for name in names for match in re.finditer(r"\b\d+(?:\.\d+)?\s*(?:GB|TB)\b", name, re.IGNORECASE)})
    generations = sorted({match.group(0).replace(" ", "").upper() for name in names for match in re.finditer(r"\bDDR\s*[345]\b", name, re.IGNORECASE)})
    speeds = sorted({match.group(0).replace(" ", "") for name in names for match in re.finditer(r"\b\d{3,5}\s*(?:MHz|MT\s*/?\s*S)\b", name, re.IGNORECASE)})
    interfaces = sorted({value for name in names for value in ("NVMe", "SATA", "PCIe", "M.2", "SODIMM", "UDIMM") if re.search(rf"\b{re.escape(value)}\b", name, re.IGNORECASE)})
    normalized_names = [name.casefold() for name in names]
    brands = [brand for brand in _CATALOG_BRANDS if any(brand.casefold() in name for name in normalized_names)]
    facets = []
    for label, values in (("tipo o formato", categories), ("capacidad", capacities), ("generación", generations), ("velocidad", speeds), ("interfaz o formato", interfaces), ("marca", brands)):
        if len(values) > 1:
            facets.append(f"{label}: {', '.join(values[:8])}")
    choices = "; ".join(facets) or "marca, modelo o alguna característica técnica"
    return (
        f"Encontré {len(candidates)} artículos con stock para «{search_term}». "
        f"Para no mostrarte una lista demasiado amplia, ¿qué prefieres entre {choices}? "
        "Puedes combinar varios criterios en una sola respuesta."
    )


def _matches_requested_family(
    requested_term: str,
    item: dict[str, Any],
) -> bool:
    family = requested_term.strip().casefold().split("_", maxsplit=1)[0]
    if family.startswith("rep-bat"):
        family = "rep"
    code = str(item.get("code", "")).casefold()
    name = str(item.get("name", "")).casefold()
    category = str(item.get("category", "")).casefold()
    if family == "ssd":
        return code.startswith("ssd") or (
            "ssd" in name
            and "almacenamiento" in category
        )
    if family == "ram":
        return (
            code.startswith("ram")
            or category.startswith("ram")
            or "memoria ram" in name
            or name.startswith("ram ")
        )
    if family == "fuente":
        return (
            code.startswith("psu")
            or "fuente de poder" in category
            or name.startswith("fuente")
        )
    if family == "pasta":
        return (
            code.startswith("paste")
            or "therm" in code
            or name.startswith("pasta ")
            or "insumos" in category
            and ("térmica" in name or "termica" in name or "thermal" in name)
        )
    if family == "ventilador":
        return (
            code.startswith("fan")
            or code.startswith("cool")
            or name.startswith("ventilador")
        )
    if family == "rep":
        return (
            code.startswith("rep-bat")
            or "batería laptop" in category
            or "bateria laptop" in category
            or (
                (name.startswith("batería") or name.startswith("bateria"))
                and "rtc" not in name
                and "cmos" not in name
                and "rtc" not in code
                and "cmos" not in code
            )
        )
    if family == "pila":
        return "cr2032" in code or "cr2032" in name
    if family == "servicio":
        return "mantenimiento" in category or name.startswith("servicio")
    return True


def make_warehouse_agent(
    repository: ServiceRepository,
    *,
    pc_build_labor_cost: Decimal | None = None,
):
    catalog = CatalogService(repository)
    def warehouse_agent(state: ServiceState) -> dict[str, Any]:
        if state.get("request_type") == "PC_BUILD":
            return _lookup_pc_build(state, repository, pc_build_labor_cost, catalog)
        if state.get("request_type") == "SALE":
            return _lookup_commercial_items(state, repository, catalog)

        if not state.get("manual_selection_complete", True):
            return {
                "outcome": "inventory_unavailable",
                "awaiting_quote_confirmation": False,
                "messages": [
                    AIMessage(
                        content=(
                            f"{state['manual_selection_error']} No consultaré "
                            "precios ni generaré una cotización hasta identificar "
                            "el componente o servicio adecuado."
                        )
                    )
                ],
            }

        if not state.get("required_parts"):
            if state.get("labor_task_type") == "diagnosis":
                return {
                    "outcome": "inventory_confirmed",
                    "matched_parts": [],
                    "inventory_substitutions": [],
                }
            return {
                "outcome": "inventory_unavailable",
                "awaiting_quote_confirmation": False,
                "messages": [
                    AIMessage(
                        content=(
                            "No se identificó un artículo o servicio con precio "
                            "positivo en el catálogo de PostgreSQL. No generaré ni "
                            "guardaré una cotización con materiales en cero."
                        )
                    )
                ],
            }

        confirmed_parts = []
        substitutions = []
        for requested in state.get("required_parts", []):
            quantity = int(requested["quantity"])
            requested_term = requested["search_term"]
            candidates = traced_tool(
                state,
                "inventory_lookup",
                lambda: catalog.find_spare_parts(requested_term),
            )
            exact_matches = [
                item
                for item in candidates
                if str(item["code"]).strip().casefold()
                == requested_term.strip().casefold()
                and _matches_requested_family(requested_term, item)
            ]
            direct_part = exact_matches[0] if len(exact_matches) == 1 else None
            if (
                direct_part is not None
                and Decimal(str(direct_part["unit_price"])) <= 0
            ):
                return {
                    "outcome": "inventory_unavailable",
                    "awaiting_quote_confirmation": False,
                    "messages": [
                        AIMessage(
                            content=(
                                f"El repuesto {direct_part['name']} aparece en el "
                                "catálogo, pero no tiene un precio positivo "
                                "configurado. No generaré una cotización hasta que "
                                "se actualice el precio."
                            )
                        )
                    ],
                }
            direct_is_usable = (
                direct_part is not None
                and Decimal(str(direct_part["unit_price"])) > 0
                and int(direct_part["current_stock"]) >= quantity
            )
            if direct_is_usable:
                part = direct_part
            else:
                if len(candidates) > 1:
                    usable_candidates = [
                        item
                        for item in candidates
                        if Decimal(str(item["unit_price"])) > 0
                        and int(item["current_stock"]) >= quantity
                        and _matches_requested_family(requested_term, item)
                    ]
                    if not usable_candidates:
                        return {
                            "outcome": "inventory_unavailable",
                            "awaiting_quote_confirmation": False,
                            "messages": [
                                AIMessage(
                                    content=(
                                        f"Encontré varias coincidencias para "
                                        f"{requested_term}, pero ninguna tiene "
                                        "precio y stock suficientes para cotizar."
                                    )
                                )
                            ],
                        }
                    options = "\n".join(
                        f"- {item['code']} — {item['name']}: "
                        f"{Decimal(str(item['unit_price'])):.2f} c/u; "
                        f"stock {int(item['current_stock'])}."
                        for item in usable_candidates
                    )
                    return {
                        "route": "awaiting_inventory_selection",
                        "outcome": "awaiting_inventory_selection",
                        "awaiting_quote_confirmation": False,
                        "awaiting_inventory_selection": True,
                        "inventory_options": [
                            {
                                "code": item["code"],
                                "quantity": quantity,
                            }
                            for item in usable_candidates
                        ],
                        "messages": [
                            AIMessage(
                                content=(
                                    f"Encontré varias coincidencias para "
                                    f"{requested_term} en el catálogo y no elegiré "
                                    "una automáticamente:\n"
                                    f"{options}\nEl ticket "
                                    f"{state.get('ticket_code', '')} ya está "
                                    "registrado para diagnóstico. Indica el código "
                                    "que deseas que el técnico revise, o responde "
                                    "“solo diagnóstico” para continuar sin repuesto. "
                                    "El técnico debe confirmar la compatibilidad "
                                    "con tu modelo antes de instalar."
                                )
                            )
                        ],
                    }

                alternatives = traced_tool(
                    state,
                    "inventory_lookup",
                    lambda: catalog.find_alternatives(
                        requested_term
                    ),
                )
                direct_ids = {item["id"] for item in exact_matches}
                alternatives = [
                    item for item in alternatives if item["id"] not in direct_ids
                ]
                usable_alternatives = [
                    item
                    for item in alternatives
                    if Decimal(str(item["unit_price"])) > 0
                    and int(item["current_stock"]) >= quantity
                    and _matches_requested_family(requested_term, item)
                ]
                if len(usable_alternatives) == 1:
                    part = usable_alternatives[0]
                    substitutions.append(
                        {
                            "requested_code": requested_term,
                            "suggested_code": part["code"],
                            "suggested_name": part["name"],
                            "quantity": quantity,
                        }
                    )
                elif usable_alternatives:
                    options = "\n".join(
                        f"- {item['code']} — {item['name']}: "
                        f"{Decimal(str(item['unit_price'])):.2f} c/u; "
                        f"stock {int(item['current_stock'])}."
                        for item in usable_alternatives
                    )
                    return {
                        "route": "awaiting_inventory_selection",
                        "outcome": "awaiting_inventory_selection",
                        "awaiting_quote_confirmation": False,
                        "awaiting_inventory_selection": True,
                        "inventory_options": [
                            {
                                "code": item["code"],
                                "quantity": quantity,
                            }
                            for item in usable_alternatives
                        ],
                        "messages": [
                            AIMessage(
                                content=(
                                    f"No encontré una coincidencia única para "
                                    f"{requested_term}. Hay varias opciones de la "
                                    "misma familia en el catálogo; no asumiré "
                                    "compatibilidad ni elegiré una automáticamente:\n"
                                    f"{options}\nEl ticket "
                                    f"{state.get('ticket_code', '')} ya está "
                                    "registrado para diagnóstico. Indica el código "
                                    "que deseas que el técnico revise, o responde "
                                    "“solo diagnóstico” para continuar sin repuesto. "
                                    "El técnico debe confirmar la compatibilidad "
                                    "con tu modelo antes de instalar."
                                )
                            )
                        ],
                    }
                else:
                    stock_alternatives = [
                        item
                        for item in (alternatives or candidates)
                        if _matches_requested_family(requested_term, item)
                    ]
                    if stock_alternatives:
                        options = "\n".join(
                            f"- {item['code']} — {item['name']}: "
                            f"stock {int(item['current_stock'])}, "
                            f"precio {Decimal(str(item['unit_price'])):.2f}."
                            for item in stock_alternatives
                        )
                        detail = (
                            f"No tenemos stock suficiente del repuesto "
                            f"{requested_term} en estos momentos. El stock actual "
                            "es insuficiente."
                        )
                        detail += f"\nOpciones de la misma familia:\n{options}"
                    else:
                        detail = (
                            f"No tenemos disponible el repuesto {requested_term} "
                            "ni encontramos opciones de su misma familia en el "
                            "catálogo."
                        )
                    return {
                        "outcome": "inventory_unavailable",
                        "awaiting_quote_confirmation": False,
                        "messages": [
                            AIMessage(
                                content=(
                                    f"{detail} El ticket "
                                    f"{state.get('ticket_code', '')} ya está "
                                    "registrado para diagnóstico. No generaré una "
                                    "cotización hasta que haya una opción con stock "
                                    "y precio válidos; puedes intentarlo más tarde."
                                )
                            )
                        ],
                    }

            unit_price = Decimal(str(part["unit_price"]))
            confirmed_parts.append(
                {
                    "id": int(part["id"]),
                    "code": part["code"],
                    "name": part["name"],
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "current_stock": int(part["current_stock"]),
                }
            )

        return {
            "outcome": "inventory_confirmed",
            "matched_parts": confirmed_parts,
            "inventory_substitutions": substitutions,
        }

    return warehouse_agent


def _commercial_part(item: dict[str, Any], quantity: int) -> dict[str, Any]:
    return {
        "id": int(item["id"]),
        "code": item["code"],
        "name": item["name"],
        "category": item.get("category", ""),
        "quantity": quantity,
        "unit_price": Decimal(str(item["unit_price"])),
        "current_stock": int(item["current_stock"]),
    }


def _selection_response(
    *,
    candidates: list[dict[str, Any]],
    quantity: int,
    confirmed_parts: list[dict[str, Any]],
    pending_requests: list[dict[str, Any]],
    replaces_category: str = "",
    search_term: str = "",
) -> dict[str, Any]:
    options = "\n".join(
        f"{index}. {item['name']} ({item.get('category', 'artículo')}) — "
        f"S/ {Decimal(str(item['unit_price'])):.2f} c/u; "
        f"{int(item['current_stock'])} disponibles."
        for index, item in enumerate(candidates, start=1)
    )
    return {
        "route": "awaiting_inventory_selection",
        "outcome": "awaiting_inventory_selection",
        "awaiting_quote_confirmation": False,
        "awaiting_inventory_selection": True,
        "awaiting_catalog_refinement": False,
        "catalog_refinement_request": {"search_term": search_term, "quantity": quantity},
        "inventory_options": [
            {
                "code": item["code"],
                "name": item["name"],
                "category": item.get("category", ""),
                "quantity": quantity,
                "replacement_category": replaces_category,
                "unit_price": str(item["unit_price"]),
                "current_stock": int(item["current_stock"]),
            }
            for item in candidates
        ],
        "matched_parts": confirmed_parts,
        "pending_commercial_requests": pending_requests,
        "messages": [
            AIMessage(
                content=(
                    "Estas son las opciones con precio y stock disponibles. "
                    "Elige por número o nombre; no necesitas conocer ningún código:\n"
                    f"{options}"
                )
            )
        ],
    }


def _refinement_response(
    *, search_term: str, quantity: int, candidates: list[dict[str, Any]],
    confirmed_parts: list[dict[str, Any]], pending_requests: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "route": "awaiting_inventory_selection",
        "outcome": "awaiting_catalog_refinement",
        "awaiting_quote_confirmation": False,
        "awaiting_inventory_selection": False,
        "inventory_options": [],
        "awaiting_catalog_refinement": True,
        "catalog_refinement_request": {"search_term": search_term, "quantity": quantity},
        "pending_commercial_requests": pending_requests,
        "matched_parts": confirmed_parts,
        "messages": [AIMessage(content=_refinement_message(search_term, candidates))],
    }


def _lookup_commercial_items(
    state: ServiceState,
    repository: ServiceRepository,
    catalog: CatalogService,
) -> dict[str, Any]:
    selection_requests = list(state.get("required_parts", []))
    pending_requests = list(state.get("pending_commercial_requests", []))
    if not selection_requests and not pending_requests:
        return {
            "outcome": "inventory_unavailable",
            "awaiting_quote_confirmation": False,
            "messages": [
                AIMessage(content="Indícame qué artículo o categoría deseas cotizar.")
            ],
        }
    is_selection = state.get("route") == "inventory_selection"
    confirmed_parts = list(state.get("matched_parts", [])) if is_selection else []
    requests = selection_requests + pending_requests
    for index, requested in enumerate(requests):
        quantity = int(requested["quantity"])
        search_term = requested["search_term"].strip()
        exact = None
        if is_selection:
            exact = traced_tool(
                state,
                "inventory_lookup",
                lambda: catalog.find_by_code(search_term),
            )
        candidates = (
            [exact]
            if exact
            else traced_tool(
                state,
                "inventory_lookup",
                lambda: catalog.find_catalog_items(search_term, limit=500),
            )
        )
        usable = [
            item
            for item in candidates
            if int(item["current_stock"]) >= quantity
            and Decimal(str(item["unit_price"])) > 0
        ]
        if not usable:
            return {
                "route": "clarification",
                "awaiting_catalog_refinement": False,
                "awaiting_inventory_selection": False,
                "catalog_refinement_request": {},
                "inventory_options": [],
                "required_parts": [],
                "pending_commercial_requests": [],
                "matched_parts": [],
                "inventory_selection_replaces_category": "",
                "outcome": "inventory_unavailable",
                "awaiting_quote_confirmation": False,
                "messages": [
                    AIMessage(
                        content=(
                            f"No encontr\u00e9 art\u00edculos con stock suficiente y precio registrado para \u00ab{search_term}\u00bb. "
                            "Puedes ajustar la capacidad, interfaz o marca, o buscar otro art\u00edculo "
                            "del cat\u00e1logo. No se cre\u00f3 una cotizaci\u00f3n, compra, orden ni reserva."
                        )
                    )
                ],
            }
        if len(usable) > CATALOG_REFINEMENT_THRESHOLD:
            return _refinement_response(
                search_term=search_term,
                quantity=quantity,
                candidates=usable,
                confirmed_parts=confirmed_parts,
                pending_requests=requests[index + 1 :],
            )
        if len(usable) > 1:
            return _selection_response(
                candidates=usable,
                quantity=quantity,
                confirmed_parts=confirmed_parts,
                pending_requests=requests[index + 1 :],
                search_term=search_term,
            )
        confirmed_parts.append(_commercial_part(usable[0], quantity))
        is_selection = False
    if not confirmed_parts:
        return {
            "outcome": "inventory_unavailable",
            "messages": [
                AIMessage(content="No se identificaron artículos para consultar.")
            ],
        }
    return {
        "route": (
            "confirm" if state.get("route") == "confirm" else "sale"
        ),
        "outcome": "inventory_confirmed",
        "matched_parts": confirmed_parts,
        "pending_commercial_requests": [],
        "inventory_substitutions": [],
        "awaiting_inventory_selection": False,
    }


def _lookup_pc_build(
    state: ServiceState,
    repository: ServiceRepository,
    labor_cost: Decimal | None,
    catalog: CatalogService,
) -> dict[str, Any]:
    if state.get("route") == "inventory_selection" and state.get(
        "inventory_selection_replaces_category"
    ):
        replacement_category = state["inventory_selection_replaces_category"]
        requests = state.get("required_parts", [])
        if len(requests) != 1:
            raise ValueError("La sustitución del armado requiere exactamente una opción.")
        selected = traced_tool(
            state,
            "inventory_lookup",
            lambda: catalog.find_by_code(requests[0]["search_term"]),
        )
        if not selected or selected.get("category") != replacement_category:
            return {
                "outcome": "inventory_unavailable",
                "awaiting_quote_confirmation": False,
                "messages": [
                    AIMessage(
                        content=(
                            "La opción ya no está disponible en la categoría "
                            "solicitada. No modifiqué ni recoticé el armado."
                        )
                    )
                ],
            }
        if int(selected["current_stock"]) < int(requests[0]["quantity"]):
            return {
                "outcome": "inventory_unavailable",
                "awaiting_quote_confirmation": False,
                "messages": [
                    AIMessage(
                        content=(
                            "El stock cambió antes de confirmar la selección. "
                            "Elige otra opción disponible."
                        )
                    )
                ],
            }
        previous_parts = list(state.get("matched_parts", []))
        revised_parts = [
            part
            for part in previous_parts
            if part.get("category") != replacement_category
        ]
        revised_parts.append(
            _commercial_part(selected, int(requests[0]["quantity"]))
        )
        return {
            "route": (
                "confirm" if state.get("route") == "confirm" else "pc_build"
            ),
            "outcome": "inventory_confirmed",
            "matched_parts": revised_parts,
            "pending_commercial_requests": [],
            "inventory_selection_replaces_category": "",
            "inventory_options": [],
            "awaiting_inventory_selection": False,
        }

    if state.get("route") == "confirm" and state.get("matched_parts"):
        refreshed_parts: list[dict[str, Any]] = []
        for current in state["matched_parts"]:
            item = traced_tool(
                state,
                "inventory_lookup",
                lambda code=current["code"]: catalog.find_by_code(code),
            )
            quantity = int(current["quantity"])
            if (
                item is None
                or item.get("category") != current.get("category")
                or int(item["current_stock"]) < quantity
                or Decimal(str(item["unit_price"])) <= 0
            ):
                return {
                    "outcome": "inventory_unavailable",
                    "awaiting_quote_confirmation": False,
                    "messages": [
                        AIMessage(
                            content=(
                                "Uno de los componentes del armado cambió de stock "
                                "o dejó de tener precio válido. No guardaré la "
                                "cotización hasta revisar de nuevo las opciones."
                            )
                        )
                    ],
                }
            refreshed_parts.append(_commercial_part(item, quantity))
        refreshed_total = sum(
            (part["unit_price"] * part["quantity"] for part in refreshed_parts),
            Decimal("0.00"),
        ) + (labor_cost or Decimal("0.00"))
        budget = state.get("budget_max")
        if budget is not None and refreshed_total > Decimal(str(budget)):
            return {
                "outcome": "build_over_budget",
                "awaiting_build_budget": True,
                "messages": [
                    AIMessage(
                        content=(
                            f"La configuración actualizada suma S/ {refreshed_total:.2f}, "
                            f"por encima del tope de S/ {Decimal(str(budget)):.2f}. "
                            "Mantengo el uso solicitado; puedes revisar el presupuesto "
                            "o pedir otro cambio."
                        )
                    )
                ],
            }
        return {"outcome": "inventory_confirmed", "matched_parts": refreshed_parts}

    try:
        from app.agents.jerarquico.pc_build_profiles import (
            load_pc_build_profiles,
            profiles_for_use,
        )

        profiles = profiles_for_use(
            state.get("intended_use", ""),
            load_pc_build_profiles(),
        )
    except (OSError, ValueError) as exc:
        raise RuntimeError("No se pudieron cargar los perfiles de armado.") from exc

    profile_by_id = {profile.identifier: profile for profile in profiles}
    selected_profile_id = state.get("selected_build_profile_id", "")
    if selected_profile_id and selected_profile_id not in profile_by_id:
        return {
            "outcome": "inventory_unavailable",
            "messages": [AIMessage(content="No pude recuperar la configuración seleccionada. Indica de nuevo el uso de la PC.")],
        }

    catalog_options: list[dict[str, Any]] = []
    for profile in profiles:
        parts: list[dict[str, Any]] = []
        missing: list[str] = []
        for category, code in profile.components:
            item = traced_tool(
                state,
                "inventory_lookup",
                lambda code=code: catalog.find_by_code(code),
            )
            if (
                item is None
                or item.get("category") != category
                or Decimal(str(item["unit_price"])) <= 0
                or int(item["current_stock"]) < 1
            ):
                missing.append(category)
                continue
            parts.append(_commercial_part(item, 1))
        if missing:
            continue
        parts_total = sum(
            (part["unit_price"] * part["quantity"] for part in parts),
            Decimal("0.00"),
        )
        total = parts_total + (labor_cost or Decimal("0.00"))
        catalog_options.append(
            {"profile": profile, "parts": parts, "total": total}
        )

    if not catalog_options:
        return {
            "outcome": "inventory_unavailable",
            "awaiting_quote_confirmation": False,
            "messages": [
                AIMessage(
                    content=(
                        "No encontré un armado completo con precio y stock "
                        "suficientes para el uso pedido. No agregué productos ni "
                        "inventé precios."
                    )
                )
            ],
        }
    budget = state.get("budget_max")
    budget = Decimal(str(budget)) if budget is not None else None
    catalog_options.sort(key=lambda option: (option["total"], option["profile"].identifier))
    fitting = [
        option
        for option in catalog_options
        if budget is None or option["total"] <= budget
    ]
    if selected_profile_id:
        selected = next(
            (option
            for option in catalog_options
            if option["profile"].identifier == selected_profile_id),
            None,
        )
        if selected is None:
            return {
                "outcome": "inventory_unavailable",
                "messages": [
                    AIMessage(
                        content=(
                            "La configuración seleccionada ya no tiene stock o "
                            "precio suficientes. Elige otra opción disponible."
                        )
                    )
                ],
            }
        if budget is not None and selected["total"] > budget:
            gap = selected["total"] - budget
            return {
                "route": "pc_build",
                "outcome": "build_over_budget",
                "awaiting_build_budget": True,
                "messages": [
                    AIMessage(
                        content=(
                            f"La configuración {selected['profile'].title} ahora "
                            f"suma S/ {selected['total']:.2f}, S/ {gap:.2f} por "
                            f"encima de tu tope de S/ {budget:.2f}. Mantengo el "
                            "uso gamer; puedes ajustar el presupuesto o pedir un "
                            "cambio concreto de componente."
                        )
                    )
                ],
            }
    elif len(fitting) > 1:
        options = [
            {
                "code": candidate["profile"].identifier,
                "name": candidate["profile"].title,
                "total": candidate["total"],
            }
            for candidate in fitting
        ]
        descriptions = []
        for index, (candidate, option) in enumerate(zip(fitting, options), 1):
            graphics = next(
                (part["name"] for part in candidate["parts"] if part["category"] == "Tarjeta de Video"),
                "gráficos integrados",
            )
            memory = next(
                (part["name"] for part in candidate["parts"] if part["category"].startswith("RAM")),
                "memoria",
            )
            descriptions.append(
                f"{index}. {option['name']} — {graphics}; {memory}; "
                f"total S/ {option['total']:.2f} (incluye ensamble)."
            )
        return {
            "route": "awaiting_build_selection",
            "outcome": "awaiting_build_selection",
            "awaiting_build_selection": True,
            "build_options": options,
            "messages": [
                AIMessage(
                    content=(
                        "Encontré estas configuraciones para juegos dentro de tu "
                        f"presupuesto de S/ {budget:.2f}:\n"
                        + "\n".join(descriptions)
                        + "\nElige por número o nombre. Después podrás cambiar RAM, "
                        "almacenamiento u otro componente; recalcularé el total "
                        "antes de pedir tu aceptación. Los precios y existencias "
                        "se consultaron ahora en el catálogo."
                    )
                )
            ],
        }
    elif not fitting:
        closest = catalog_options[0]
        gap = closest["total"] - budget if budget is not None else Decimal("0.00")
        return {
            "route": "pc_build",
            "outcome": "build_over_budget",
            "awaiting_quote_confirmation": False,
            "awaiting_build_budget": True,
            "messages": [
                AIMessage(
                    content=(
                        f"La configuración gamer más económica disponible, "
                        f"{closest['profile'].title}, suma S/ {closest['total']:.2f} "
                        f"incluido el ensamble: excede tu tope de S/ {budget:.2f} "
                        f"por S/ {gap:.2f}. Mantengo el uso para juegos; puedes "
                        "ajustar el presupuesto o indicarme componentes concretos "
                        "que quieres cambiar. Aún no guardé la cotización."
                    )
                )
            ],
        }
    else:
        selected = fitting[0]

    profile = selected["profile"]
    parts = selected["parts"]
    return {
        "route": (
            "confirm" if state.get("route") == "confirm" else "pc_build"
        ),
        "outcome": "inventory_confirmed",
        "matched_parts": parts,
        "build_profile_id": profile.identifier,
        "selected_build_profile_id": profile.identifier,
        "build_compatibility_notes": profile.compatibility_notes,
        "pending_commercial_requests": [],
        "inventory_substitutions": [],
        "awaiting_build_budget": False,
        "awaiting_build_selection": False,
        "build_options": [],
    }

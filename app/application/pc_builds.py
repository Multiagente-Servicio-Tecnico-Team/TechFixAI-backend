"""Shared, catalog-validated PC build profile selection and modification."""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.rag.sources import knowledge_sources


@dataclass(frozen=True)
class PCBuildProfile:
    identifier: str
    title: str
    uses: tuple[str, ...]
    components: tuple[tuple[str, str], ...]
    compatibility_notes: str


def load_pc_build_profiles() -> tuple[PCBuildProfile, ...]:
    source = next(
        (item for item in knowledge_sources()
         if item.source_id == "hierarchical:pc_build_profiles"),
        None,
    )
    if source is None:
        raise ValueError("No hay perfiles de armado registrados en el manifiesto de conocimiento.")
    content = source.path.read_text(encoding="utf-8")
    pattern = re.compile(r"(?ms)^## ([a-z0-9_-]+)\s*\n(.*?)(?=^## |\Z)")
    component_pattern = re.compile(r"(?m)^-\s*([^:]+):\s*`([^`]+)`\s*$")
    profiles = []
    for match in pattern.finditer(content):
        identifier, body = match.groups()
        title = re.search(r"(?m)^\*\*Nombre\*\*:\s*(.+)$", body)
        uses = re.search(r"(?m)^\*\*Uso\*\*:\s*(.+)$", body)
        notes = re.search(r"(?m)^\*\*Compatibilidad\*\*:\s*(.+)$", body)
        components = tuple(component_pattern.findall(body))
        if not title or not uses or not notes or not components:
            raise ValueError(f"El perfil {identifier} está incompleto.")
        profiles.append(PCBuildProfile(
            identifier=identifier,
            title=title.group(1).strip(),
            uses=tuple(value.strip().casefold() for value in re.split(r"[,;]", uses.group(1)) if value.strip()),
            components=components,
            compatibility_notes=notes.group(1).strip(),
        ))
    if not profiles:
        raise ValueError("No se encontraron perfiles de armado válidos.")
    return tuple(profiles)


def profiles_for_use(intended_use: str, profiles=None) -> tuple[PCBuildProfile, ...]:
    available = profiles or load_pc_build_profiles()
    normalized = intended_use.casefold()
    matching = tuple(
        profile for profile in available
        if normalized and any(
            use in normalized or normalized in use for use in _field(profile, "uses")
        )
    )
    if matching:
        return matching
    ranked = sorted(available, key=lambda profile: (
        not any(use in normalized for use in _field(profile, "uses")),
        _field(profile, "identifier"),
    ))
    return (ranked[0],)


def choose_pc_build_profile(intended_use: str, profiles=None) -> PCBuildProfile:
    return profiles_for_use(intended_use, profiles)[0]


def _field(profile, name):
    return profile[name] if isinstance(profile, dict) else getattr(profile, name)


def available_pc_builds(
    repository,
    *,
    intended_use: str,
    labor_cost: Decimal,
    budget_max: Decimal | None = None,
    profiles=None,
) -> list[dict[str, object]]:
    labor = Decimal(str(labor_cost))
    budget = Decimal(str(budget_max)) if budget_max is not None else None
    if not labor.is_finite() or labor < 0 or (budget is not None and (not budget.is_finite() or budget <= 0)):
        raise ValueError("El costo de ensamble y el presupuesto deben ser importes válidos.")
    options = []
    for profile in profiles_for_use(intended_use, profiles):
        parts = []
        for category, code in _field(profile, "components"):
            item = repository.find_spare_part_by_code(code)
            if not item or item.get("category") != category:
                break
            try:
                price = Decimal(str(item["unit_price"]))
                stock = int(item["current_stock"])
            except (KeyError, TypeError, ValueError, InvalidOperation):
                break
            if not price.is_finite() or price <= 0 or stock < 1:
                break
            parts.append({**item, "quantity": 1, "unit_price": price, "subtotal": price})
        else:
            total = labor + sum((part["subtotal"] for part in parts), Decimal("0.00"))
            options.append({
                "code": _field(profile, "identifier"),
                "name": _field(profile, "title"),
                "parts": parts,
                "labor_cost": labor,
                "total": total,
                "within_budget": budget is None or total <= budget,
                "compatibility_notes": _field(profile, "compatibility_notes"),
            })
    return sorted(options, key=lambda option: (option["total"], option["code"]))


def replace_pc_build_component(
    repository,
    *,
    current_parts: list[dict[str, object]],
    category: str,
    replacement_code: str,
    quantity: int = 1,
) -> list[dict[str, object]]:
    if type(quantity) is not int or quantity < 1:
        raise ValueError("La cantidad del componente debe ser positiva.")
    refreshed = []
    for part in current_parts:
        code = str(part.get("code", ""))
        item = repository.find_spare_part_by_code(code)
        part_quantity = part.get("quantity", 1)
        if (not item or item.get("category") != part.get("category")
                or type(part_quantity) is not int or part_quantity < 1):
            raise ValueError("Un componente actual del armado ya no es válido.")
        current_price = Decimal(str(item["unit_price"]))
        if (not current_price.is_finite() or current_price <= 0
                or int(item["current_stock"]) < part_quantity):
            raise ValueError("Un componente actual cambió de precio o stock.")
        refreshed.append({**item, "quantity": part_quantity,
                          "unit_price": current_price,
                          "subtotal": current_price * part_quantity})
    indexes = [index for index, part in enumerate(refreshed) if part.get("category") == category]
    if len(indexes) != 1:
        raise ValueError("La categoría debe existir una sola vez en el armado.")
    item = repository.find_spare_part_by_code(replacement_code.strip())
    if not item or item.get("category") != category:
        raise ValueError("El repuesto no pertenece a la categoría seleccionada.")
    try:
        price = Decimal(str(item["unit_price"]))
        stock = int(item["current_stock"])
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise ValueError("No se pudieron validar precio y stock del componente.") from exc
    if not price.is_finite() or price <= 0 or stock < quantity:
        raise ValueError("El repuesto ya no tiene precio o stock suficiente.")
    revised = list(refreshed)
    revised[indexes[0]] = {**item, "quantity": quantity, "unit_price": price, "subtotal": price * quantity}
    return revised


def modify_pc_build(
    repository,
    *,
    profile_id: str,
    intended_use: str,
    labor_cost: Decimal,
    category: str,
    replacement_code: str,
    budget_max: Decimal | None = None,
) -> dict[str, object]:
    profiles = load_pc_build_profiles()
    profile = next((item for item in profiles if item.identifier == profile_id), None)
    normalized_use = intended_use.casefold()
    if profile is None or not any(
        use in normalized_use or normalized_use in use for use in profile.uses
    ):
        raise ValueError("El perfil de armado no corresponde al uso solicitado.")
    available = available_pc_builds(
        repository, intended_use=intended_use, labor_cost=labor_cost,
        budget_max=budget_max, profiles=(profile,),
    )
    if not available:
        raise ValueError("El perfil dejó de tener todos sus componentes disponibles.")
    current = available[0]
    parts = replace_pc_build_component(
        repository, current_parts=current["parts"], category=category,
        replacement_code=replacement_code,
    )
    total = current["labor_cost"] + sum(
        (part["subtotal"] for part in parts), Decimal("0.00")
    )
    budget = Decimal(str(budget_max)) if budget_max is not None else None
    if budget is not None and total > budget:
        raise ValueError("El cambio supera el presupuesto indicado.")
    return {**current, "parts": parts, "total": total,
            "within_budget": True, "profile_id": profile.identifier}

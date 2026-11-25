"""Shared warranty ownership, eligibility and claim-registration rules."""

from uuid import uuid4


def lookup_customer_warranty(repository, *, customer_id: int, warranty_code: str):
    if type(customer_id) is not int or customer_id < 1:
        raise PermissionError("Se requiere una sesión de cliente autenticada.")
    code = warranty_code.strip().upper()
    if not code or len(code) > 32:
        return None
    warranty = repository.find_warranty(code)
    if warranty is None or int(warranty["customer_id"]) != customer_id:
        return None
    return warranty


def register_customer_warranty_claim(
    repository,
    *,
    customer_id: int,
    ticket_id: int,
    warranty_code: str,
    reason: str,
    claim_code: str | None = None,
):
    if type(customer_id) is not int or customer_id < 1:
        raise PermissionError("Se requiere una sesión de cliente autenticada.")
    if type(ticket_id) is not int or ticket_id < 1:
        raise ValueError("Se requiere un ticket válido asociado al cliente.")
    normalized_reason = reason.strip()
    if not normalized_reason or len(normalized_reason) > 2000:
        raise ValueError("El motivo del reclamo es obligatorio y debe ser breve.")
    warranty = lookup_customer_warranty(
        repository, customer_id=customer_id, warranty_code=warranty_code
    )
    if warranty is None:
        raise LookupError("No se encontró una póliza asociada a la cuenta.")
    if warranty.get("status") != "ACTIVE" or not warranty.get("not_expired"):
        raise ValueError("La póliza no está vigente para registrar un reclamo.")

    code = claim_code or f"CLM-{uuid4().hex[:12].upper()}"
    repository.create_warranty_claim(
        warranty_id=int(warranty["id"]),
        ticket_id=ticket_id,
        customer_id=customer_id,
        claim_code=code,
        reason=normalized_reason,
    )
    return {
        "warranty_id": int(warranty["id"]),
        "claim_code": code,
        "status": "IN_REVIEW",
        "ticket_status": "WARRANTY_IN_REVIEW",
    }

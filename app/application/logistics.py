"""Shared validation for customer logistics preferences."""


LOGISTICS_MODES = {"PHYSICAL_STORE", "COURIER_SHIPMENT"}


def record_customer_logistics_preference(
    repository,
    *,
    customer_id: int,
    ticket_id: int | None = None,
    sales_order_id: int | None = None,
    mode: str,
    courier_company: str | None = None,
    shipping_address: str | None = None,
) -> int:
    if type(customer_id) is not int or customer_id < 1:
        raise PermissionError("Se requiere una sesión de cliente autenticada.")
    if (ticket_id is None) == (sales_order_id is None):
        raise ValueError("Indica un ticket de servicio o una venta, pero no ambos.")
    if ticket_id is not None and (type(ticket_id) is not int or ticket_id < 1):
        raise ValueError("El ticket indicado no es válido.")
    if sales_order_id is not None and (type(sales_order_id) is not int or sales_order_id < 1):
        raise ValueError("La venta indicada no es válida.")
    if mode not in LOGISTICS_MODES:
        raise ValueError("Modalidad logística no admitida.")

    company = courier_company.strip() if courier_company else None
    address = shipping_address.strip() if shipping_address else None
    if mode == "COURIER_SHIPMENT" and not (company and address):
        raise ValueError("Courier requiere empresa y dirección.")
    if company and len(company) > 100:
        raise ValueError("El nombre de la empresa courier es demasiado largo.")
    if address and len(address) > 500:
        raise ValueError("La dirección de envío es demasiado larga.")

    return repository.create_logistics_record(
        ticket_id=ticket_id,
        sales_order_id=sales_order_id,
        customer_id=customer_id,
        mode=mode,
        courier_company=company,
        shipping_address=address,
    )

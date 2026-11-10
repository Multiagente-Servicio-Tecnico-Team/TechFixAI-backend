"""ADMIN capability adapters backed by the existing validated services.

The LLM only selects an allowlisted action and suggests arguments. Each write is
validated and previewed here, then revalidated by the domain service at commit.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Type
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PageQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=20, ge=1, le=50)
    offset: int = Field(default=0, ge=0)
    search: str | None = Field(default=None, max_length=100)
    status: str | None = Field(default=None, max_length=30)
    customer_id: int | None = Field(default=None, ge=1)
    supplier_id: int | None = Field(default=None, ge=1)


class RecordId(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int = Field(gt=0)


class CustomerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: int = Field(gt=0)
    values: dict[str, Any]


class TicketUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket_id: int = Field(gt=0)
    values: dict[str, Any]


class InventoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=50)
    values: dict[str, Any]


class StockAdjust(BaseModel):
    model_config = ConfigDict(extra="forbid")
    part_id: int = Field(gt=0)
    expected_stock: int = Field(ge=0, strict=True)
    counted_stock: int = Field(ge=0, strict=True)
    reason: str = Field(min_length=1, max_length=500)


class SupplierUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supplier_id: int = Field(gt=0)
    values: dict[str, Any]


class PurchaseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    purchase_id: int = Field(gt=0)
    values: dict[str, Any]


class PurchaseReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    purchase_id: int = Field(gt=0)
    notes: str | None = Field(default=None, max_length=2000)
    items: list[dict[str, Any]] = Field(min_length=1, max_length=100)


class OrderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: int = Field(gt=0)
    values: dict[str, Any]


class OrderCancel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=500)


class OrderReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: int = Field(gt=0)
    notes: str | None = Field(default=None, max_length=2000)
    items: list[dict[str, Any]] = Field(min_length=1, max_length=100)


class QuoteAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quote_id: int = Field(gt=0)
    notes: str | None = Field(default=None, max_length=1000)
    confirmation_channel: str | None = None


class PaymentAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quote_id: int = Field(gt=0)
    method: Literal["CREDIT_CARD", "DEBIT_CARD", "BANK_TRANSFER", "CASH", "PAYMENT_GATEWAY"]
    transaction_reference: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)


class EntryReverse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entry_id: int = Field(gt=0)
    operation_date: date
    reason: str = Field(min_length=1, max_length=2000)


class ReportExport(BaseModel):
    """Exportación de un reporte contable existente (no modifica datos)."""
    model_config = ConfigDict(extra="forbid")
    report: Literal["journal", "ledger", "trial_balance"]
    from_date: date
    to_date: date
    format: Literal["csv", "xlsx"] = "xlsx"
    status: Literal["CONFIRMED", "REVERSED"] | None = None
    plan_id: int | None = Field(default=None, ge=1)
    account_code: str | None = Field(default=None, min_length=1, max_length=40)


class AdminFieldValidationError(ValueError):
    """A correctable field/reference error that can be returned through a chat draft."""

    def __init__(self, field: str, detail: str):
        super().__init__(detail)
        self.field = field
        self.detail = detail


REPORT_PATHS = {
    "journal": "/api/admin/accounting/reports/journal",
    "ledger": "/api/admin/accounting/reports/ledger",
    "trial_balance": "/api/admin/accounting/reports/trial-balance",
}

READ_ACTIONS = {
    "customers.list", "customers.get", "tickets.list", "tickets.get",
    "inventory.list", "suppliers.list", "suppliers.get", "purchases.list",
    "purchases.get", "purchase_orders.list", "purchase_orders.get",
    "sales_quotes.list", "sales_quotes.get", "sales_orders.list", "sales_orders.get",
    "payments.list", "accounting.entries.list", "accounting.entries.get",
    "accounting.categories.list", "accounting.reports.export",
}

WRITE_ACTIONS = {
    "customers.create", "customers.update", "tickets.create", "tickets.update",
    "inventory.create", "inventory.update", "inventory.adjust_stock",
    "suppliers.create", "suppliers.update", "purchases.create", "purchases.update",
    "purchases.cancel", "purchases.receive", "purchase_orders.create",
    "purchase_orders.update", "purchase_orders.issue", "purchase_orders.cancel",
    "purchase_orders.receive", "sales_quotes.create", "sales_quotes.accept",
    "sales_quotes.cancel", "sales_quotes.confirm_payment",
    "accounting.entries.create", "accounting.entries.reverse",
}


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, BaseModel):
        return json_safe(value.model_dump(mode="python"))
    if is_dataclass(value):
        return json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _normalize_entry_lines(arguments: dict[str, Any]) -> dict[str, Any]:
    """Normaliza las líneas de un asiento propuesto por lenguaje natural.

    - Con `account_code`, se descartan `account_id`/`account_name` sugeridos por el
      modelo: el catálogo resuelve la cuenta por código y un id inventado podría
      apuntar a otra cuenta.
    - Los importes se expresan con dos decimales ("150" -> "150.00"). Un valor no
      numérico se deja igual para que la validación lo rechace.
    """
    from decimal import InvalidOperation

    lines = arguments.get("lines")
    if not isinstance(lines, list):
        return arguments
    normalized = []
    for line in lines:
        if not isinstance(line, dict):
            normalized.append(line)
            continue
        line = dict(line)
        if line.get("account_code"):
            line["account_code"] = str(line["account_code"]).strip()
            line.pop("account_id", None)
            line.pop("account_name", None)
        for side in ("debit", "credit"):
            value = line.get(side)
            if value is None or isinstance(value, bool):
                continue
            try:
                amount = Decimal(str(value).strip())
            except InvalidOperation:
                continue
            if amount.is_finite() and amount >= 0:
                line[side] = format(amount.quantize(Decimal("0.01")), "f")
        normalized.append(line)
    return {**arguments, "lines": normalized}


class AdminCapabilityService:
    def __init__(self, *, customer_repository_factory=None, ticket_repository_factory=None,
                 inventory_repository_factory=None, purchase_repository_factory=None,
                 purchase_order_repository_factory=None, sales_repository_factory=None,
                 accounting_repository_factory=None, accounting_catalog_repository_factory=None):
        self.customer_repository_factory = customer_repository_factory
        self.ticket_repository_factory = ticket_repository_factory
        self.inventory_repository_factory = inventory_repository_factory
        self.purchase_repository_factory = purchase_repository_factory
        self.purchase_order_repository_factory = purchase_order_repository_factory
        self.sales_repository_factory = sales_repository_factory
        self.accounting_repository_factory = accounting_repository_factory
        self.accounting_catalog_repository_factory = accounting_catalog_repository_factory

    def _service(self, domain: str):
        if domain == "customers":
            from app.adapters.persistence.customers import CustomerRepositoryAdapter
            from app.application.customer_profiles import CustomerProfileService
            return CustomerProfileService((self.customer_repository_factory or CustomerRepositoryAdapter)())
        if domain == "tickets":
            from app.adapters.persistence.admin_tickets import AdminTicketRepositoryAdapter
            from app.application.admin_tickets import AdminTicketService
            return AdminTicketService((self.ticket_repository_factory or AdminTicketRepositoryAdapter)())
        if domain == "inventory":
            from app.adapters.persistence.inventory import InventoryRepositoryAdapter
            from app.application.inventory import InventoryService
            return InventoryService((self.inventory_repository_factory or InventoryRepositoryAdapter)())
        if domain in {"suppliers", "purchases"}:
            from app.adapters.persistence.purchases import SupplierPurchaseRepositoryAdapter
            from app.application.purchases import SupplierPurchaseService
            return SupplierPurchaseService((self.purchase_repository_factory or SupplierPurchaseRepositoryAdapter)())
        if domain == "purchase_orders":
            from app.adapters.persistence.purchase_orders import PurchaseOrderRepositoryAdapter
            from app.application.purchase_orders import PurchaseOrderService
            return PurchaseOrderService((self.purchase_order_repository_factory or PurchaseOrderRepositoryAdapter)())
        if domain in {"sales_quotes", "sales_orders", "payments"}:
            from app.adapters.persistence.sales_quotes import SalesQuoteRepositoryAdapter
            return (self.sales_repository_factory or SalesQuoteRepositoryAdapter)()
        if domain == "accounting":
            from app.adapters.persistence.accounting import AccountingRepositoryAdapter
            from app.application.accounting import AccountingService
            return AccountingService((self.accounting_repository_factory or AccountingRepositoryAdapter)())
        if domain == "accounting_catalog":
            from app.adapters.persistence.accounting_catalog import AccountingCatalogRepository
            from app.application.accounting_catalog import AccountingCatalogService
            return AccountingCatalogService(
                (self.accounting_catalog_repository_factory or AccountingCatalogRepository)()
            )
        if domain == "accounting.categories":
            from app.adapters.persistence.accounting import AccountingRepositoryAdapter
            repo_factory = self.accounting_repository_factory or AccountingRepositoryAdapter
            return repo_factory()
        raise ValueError("La capacidad no existe.")

    def read(self, action: str, arguments: dict[str, Any]) -> dict[str, Any]:
        list_fields = {
            "customers.list": {"search", "limit", "offset"},
            "tickets.list": {"search", "status", "limit", "offset"},
            "inventory.list": {"search", "limit", "offset"},
            "suppliers.list": {"search", "limit", "offset"},
            "purchases.list": {"supplier_id", "search", "status", "limit", "offset"},
            "purchase_orders.list": {"supplier_id", "status", "limit", "offset"},
            "sales_quotes.list": {"customer_id", "status", "limit", "offset"},
            "sales_orders.list": {"customer_id", "limit", "offset"},
            "payments.list": {"customer_id", "status", "limit", "offset"},
            "accounting.entries.list": {"status", "limit", "offset"},
            "accounting.categories.list": set(),
        }
        if action not in READ_ACTIONS:
            raise ValueError("Esa consulta no está disponible.")
        if action == "accounting.reports.export":
            return self._report_export(arguments)
        if action.endswith(".get"):
            args: PageQuery | None = None
            RecordId.model_validate(arguments)
        else:
            unknown = set(arguments) - list_fields[action]
            if unknown:
                raise ValueError("La consulta incluye filtros no admitidos.")
            args = PageQuery.model_validate(arguments)
        if action == "customers.list":
            from app.adapters.persistence.customers import CustomerRepositoryAdapter
            repo = (self.customer_repository_factory or CustomerRepositoryAdapter)()
            result = repo.list_customers(search=args.search, limit=args.limit, offset=args.offset)
        elif action == "customers.get":
            result = self._service("customers").get_customer(RecordId.model_validate(arguments).id)
        elif action == "tickets.list":
            result = self._service("tickets").list_tickets(
                limit=args.limit, offset=args.offset, search=args.search, status=args.status)
        elif action == "tickets.get":
            result = self._service("tickets").get_ticket(RecordId.model_validate(arguments).id)
        elif action == "inventory.list":
            items = self._service("inventory").list_parts()
            if args.search:
                needle = args.search.casefold()
                items = [item for item in items if needle in item.name.casefold()
                         or needle in item.code.casefold()
                         or needle in (item.category or "").casefold()]
            total = len(items)
            result = {"items": items[args.offset:args.offset + args.limit], "total": total,
                      "limit": args.limit, "offset": args.offset}
        elif action == "suppliers.list":
            result = self._service("suppliers").list_suppliers(
                active=True, search=args.search, limit=args.limit, offset=args.offset)
        elif action == "suppliers.get":
            result = self._service("suppliers").get_supplier(RecordId.model_validate(arguments).id)
        elif action == "purchases.list":
            service = self._service("purchases")
            result = service.list_purchases(supplier_id=args.supplier_id, from_date=None, to_date=None,
                status=args.status, payment_status=None, document_number=args.search,
                limit=args.limit, offset=args.offset)
        elif action == "purchases.get":
            result = self._service("purchases").get_purchase(RecordId.model_validate(arguments).id)
        elif action == "purchase_orders.list":
            result = self._service("purchase_orders").list_orders(supplier_id=args.supplier_id,
                status=args.status, limit=args.limit, offset=args.offset)
        elif action == "purchase_orders.get":
            result = self._service("purchase_orders").get_order(RecordId.model_validate(arguments).id)
        elif action == "sales_quotes.list":
            result = self._service("sales_quotes").list_sales_quotes(customer_id=args.customer_id,
                status=args.status, limit=args.limit, offset=args.offset)
        elif action == "sales_quotes.get":
            result = self._service("sales_quotes").get_sales_quote(RecordId.model_validate(arguments).id)
        elif action == "sales_orders.list":
            result = self._service("sales_orders").list_sales_orders(customer_id=args.customer_id,
                limit=args.limit, offset=args.offset)
        elif action == "sales_orders.get":
            result = self._service("sales_orders").get_sales_order(RecordId.model_validate(arguments).id)
        elif action == "payments.list":
            result = self._service("payments").list_admin_payments(customer_id=args.customer_id,
                status=args.status, limit=args.limit, offset=args.offset)
        elif action == "accounting.entries.list":
            result = self._service("accounting").list_entries(status=args.status, limit=args.limit, offset=args.offset)
        elif action == "accounting.entries.get":
            result = self._service("accounting").get_entry(RecordId.model_validate(arguments).id)
        elif action == "accounting.categories.list":
            result = self._service("accounting.categories").list_categories()
        else:
            raise ValueError("Esa consulta no está disponible.")
        if action.endswith(".get") and result is None:
            raise LookupError("No se encontró el registro solicitado.")
        safe = json_safe(result)
        if isinstance(safe, dict):
            return safe
        return {"items": safe}

    @staticmethod
    def _report_export(arguments: dict[str, Any]) -> dict[str, Any]:
        """Devuelve el enlace de descarga del endpoint de reportes ya existente.

        El archivo lo genera `GET /api/admin/accounting/reports/...` con la misma
        sesión ADMIN; el chat no construye ni guarda el archivo.
        """
        from urllib.parse import urlencode

        body = ReportExport.model_validate(arguments)
        if body.from_date > body.to_date:
            raise ValueError("La fecha inicial no puede ser posterior a la final.")
        if body.report != "ledger" and body.account_code is not None:
            raise ValueError("El filtro de cuenta solo aplica al libro mayor.")
        query = {"from_date": body.from_date.isoformat(), "to_date": body.to_date.isoformat(),
                 "format": body.format}
        for key in ("status", "plan_id", "account_code"):
            value = getattr(body, key)
            if value is not None:
                query[key] = value
        return {"report": body.report, "format": body.format,
                "from_date": body.from_date.isoformat(), "to_date": body.to_date.isoformat(),
                "download_url": f"{REPORT_PATHS[body.report]}?{urlencode(query)}"}

    @staticmethod
    def values_schema(action: str) -> Type[BaseModel] | None:
        """Esquema del objeto `values` de las escrituras de actualización."""
        from app.adapters.api.admin_tickets import TicketPatch
        from app.adapters.api.customers import CustomerPatch
        from app.adapters.api.inventory import InventoryPartWrite
        from app.adapters.api.purchase_orders import PurchaseOrderPatch
        from app.adapters.api.purchases import PurchasePatch, SupplierPatch
        return {
            "customers.update": CustomerPatch,
            "tickets.update": TicketPatch,
            "inventory.update": InventoryPartWrite,
            "suppliers.update": SupplierPatch,
            "purchases.update": PurchasePatch,
            "purchase_orders.update": PurchaseOrderPatch,
        }.get(action)

    @staticmethod
    def _schema(action: str) -> Type[BaseModel]:
        from app.adapters.api.accounting import CreateEntryIn
        from app.adapters.api.admin_tickets import TicketCreate, TicketPatch
        from app.adapters.api.customers import CustomerPatch, CustomerWrite
        from app.adapters.api.inventory import InventoryPartWrite
        from app.adapters.api.purchase_orders import (
            PurchaseOrderPatch, PurchaseOrderReceiptWrite, PurchaseOrderWrite,
        )
        from app.adapters.api.purchases import (
            PurchasePatch, PurchaseWrite, ReceiptWrite, SupplierPatch, SupplierWrite,
        )
        from app.adapters.api.sales_quotes import (
            ManualAcceptance, PaymentConfirmation, QuoteCancellation, SalesQuoteWrite,
        )
        schemas = {
            "customers.create": CustomerWrite,
            "customers.update": CustomerUpdate,
            "tickets.create": TicketCreate,
            "tickets.update": TicketUpdate,
            "inventory.create": InventoryPartWrite,
            "inventory.update": InventoryUpdate,
            "inventory.adjust_stock": StockAdjust,
            "suppliers.create": SupplierWrite,
            "suppliers.update": SupplierUpdate,
            "purchases.create": PurchaseWrite,
            "purchases.update": PurchaseUpdate,
            "purchases.cancel": RecordId,
            "purchases.receive": PurchaseReceipt,
            "purchase_orders.create": PurchaseOrderWrite,
            "purchase_orders.update": OrderUpdate,
            "purchase_orders.issue": RecordId,
            "purchase_orders.cancel": OrderCancel,
            "purchase_orders.receive": OrderReceipt,
            "sales_quotes.create": SalesQuoteWrite,
            "sales_quotes.accept": QuoteAction,
            "sales_quotes.cancel": QuoteAction,
            "sales_quotes.confirm_payment": PaymentAction,
            "accounting.entries.create": CreateEntryIn,
            "accounting.entries.reverse": EntryReverse,
        }
        return schemas[action]

    def _validate_references(self, action: str, values: dict[str, Any]) -> None:
        """Reject stale/nonexistent references before a proposal is shown."""
        def repo(domain: str):
            service = self._service(domain)
            return getattr(service, "repository", service)

        def existing(domain: str, method: str, identifier: int, field: str, label: str,
                     *, require_active: bool = True):
            record = getattr(repo(domain), method)(identifier)
            if record is None:
                raise AdminFieldValidationError(field, f"no se encontró {label}; revisa el identificador")
            if require_active and isinstance(record, dict) and record.get("active") is False:
                raise AdminFieldValidationError(field, f"{label.capitalize()} está inactivo")
            return record

        customer_id = values.get("customer_id")
        if customer_id is not None and action in {"tickets.create", "sales_quotes.create"}:
            existing("customers", "get_customer", customer_id, "customer_id", "el cliente")

        supplier_id = values.get("supplier_id")
        if action == "purchase_orders.update":
            supplier_id = values.get("values", {}).get("supplier_id", supplier_id)
        if supplier_id is not None and action in {
            "purchases.create", "purchase_orders.create", "purchase_orders.update",
        }:
            existing("suppliers", "get_supplier", supplier_id, "supplier_id", "el proveedor")

        part_lines = []
        if action == "sales_quotes.create":
            part_lines = values.get("lines", [])
        elif action in {"purchases.create", "purchase_orders.create"}:
            part_lines = values.get("items", [])
        elif action == "purchase_orders.update":
            part_lines = values.get("values", {}).get("items") or []
        requested_parts = {
            line.get("spare_part_id") for line in part_lines
            if isinstance(line, dict) and line.get("spare_part_id") is not None
        }
        if requested_parts:
            active_parts = {part.id for part in self._service("inventory").list_parts()}
            for part_id in sorted(requested_parts):
                if part_id not in active_parts:
                    raise AdminFieldValidationError(
                        "spare_part_id", f"el repuesto {part_id} no existe o está inactivo; consulta el inventario y elige uno activo"
                    )

        if action == "inventory.update":
            code = values.get("code")
            active_parts = self._service("inventory").list_parts()
            if not any(part.code == code for part in active_parts):
                raise AdminFieldValidationError(
                    "code", "no existe un repuesto activo con ese código; consulta el inventario y corrígelo"
                )
        elif action == "inventory.adjust_stock":
            part_id = values.get("part_id")
            active_parts = self._service("inventory").list_parts()
            if not any(part.id == part_id for part in active_parts):
                raise AdminFieldValidationError(
                    "part_id", "el repuesto no existe o está inactivo; consulta el inventario y corrige el ID"
                )

        if action == "purchases.create" and values.get("purchase_order_id") is not None:
            order = existing("purchase_orders", "get_order", values["purchase_order_id"],
                             "purchase_order_id", "la orden de compra")
            if order.get("supplier_id") != values.get("supplier_id"):
                raise AdminFieldValidationError(
                    "purchase_order_id", "la orden pertenece a otro proveedor; elige una orden del proveedor indicado"
                )

        item_list: list[dict[str, Any]] = []
        if action == "purchases.receive" and values.get("purchase_id") is not None:
            purchase = existing("purchases", "get_purchase", values["purchase_id"],
                                "purchase_id", "la compra")
            item_list = purchase.get("items", [])
            valid_ids = {int(item["id"]) for item in item_list if isinstance(item, dict) and item.get("id") is not None}
            for line in values.get("items", []):
                if line.get("purchase_item_id") not in valid_ids:
                    raise AdminFieldValidationError(
                        "purchase_item_id", "esa línea no pertenece a la compra indicada; revisa el ID de la línea"
                    )

        order_id = values.get("order_id")
        if action == "purchase_orders.receive" and order_id is not None:
            order = existing("purchase_orders", "get_order", order_id, "order_id", "la orden de compra")
            valid_ids = {int(item["id"]) for item in order.get("items", []) if item.get("id") is not None}
            for line in values.get("items", []):
                if line.get("purchase_order_item_id") not in valid_ids:
                    raise AdminFieldValidationError(
                        "purchase_order_item_id", "esa línea no pertenece a la orden indicada; revisa el ID de la línea"
                    )

        id_references = {
            "customers.update": ("customers", "get_customer", "customer_id", "el cliente"),
            "tickets.update": ("tickets", "get_ticket", "ticket_id", "el ticket"),
            "suppliers.update": ("suppliers", "get_supplier", "supplier_id", "el proveedor"),
            "purchases.update": ("purchases", "get_purchase", "purchase_id", "la compra"),
            "purchases.cancel": ("purchases", "get_purchase", "id", "la compra"),
            "purchase_orders.update": ("purchase_orders", "get_order", "order_id", "la orden de compra"),
            "purchase_orders.issue": ("purchase_orders", "get_order", "id", "la orden de compra"),
            "purchase_orders.cancel": ("purchase_orders", "get_order", "order_id", "la orden de compra"),
            "sales_quotes.accept": ("sales_quotes", "get_sales_quote", "quote_id", "la cotización"),
            "sales_quotes.cancel": ("sales_quotes", "get_sales_quote", "quote_id", "la cotización"),
            "sales_quotes.confirm_payment": ("sales_quotes", "get_sales_quote", "quote_id", "la cotización"),
            "accounting.entries.reverse": ("accounting", "get_entry", "entry_id", "el asiento contable"),
        }
        reference = id_references.get(action)
        if reference:
            domain, method, key, label = reference
            existing(domain, method, values[key], key, label,
                     require_active=action not in {"customers.update", "suppliers.update"})

        if action == "accounting.entries.create":
            categories = repo("accounting").list_categories()
            if values.get("category_id") not in {int(item["id"]) for item in categories}:
                raise AdminFieldValidationError(
                    "category_id", "la categoría contable no existe o está inactiva; consulta las categorías disponibles"
                )
            catalog = self._service("accounting_catalog")
            plans = catalog.list_plans()
            plan_id = values.get("plan_id")
            if plan_id is None:
                default_plan = next((plan for plan in plans
                                     if plan.get("is_default") and plan.get("status") == "ACTIVE"), None)
                if default_plan is None:
                    raise AdminFieldValidationError(
                        "plan_id", "no hay un plan contable predeterminado activo; configura uno antes de crear el asiento"
                    )
                plan_id = int(default_plan["id"])
            else:
                selected_plan = next((plan for plan in plans if int(plan["id"]) == int(plan_id)), None)
                if selected_plan is None or selected_plan.get("status") != "ACTIVE":
                    raise AdminFieldValidationError(
                        "plan_id", "el plan contable no existe o está inactivo; selecciona un plan activo"
                    )
            operation_date = values["operation_date"]
            for index, line in enumerate(values.get("lines", []), start=1):
                account = catalog.get_postable_account(
                    plan_id=plan_id,
                    operation_date=operation_date,
                    account_id=line.get("account_id"),
                    account_code=line.get("account_code"),
                )
                if account is None:
                    account_ref = "account_code" if line.get("account_code") else "account_id"
                    raise AdminFieldValidationError(
                        account_ref,
                        f"la línea {index} debe usar una cuenta activa, imputable y vigente del plan contable seleccionado",
                    )

    def prepare(self, action: str, arguments: dict[str, Any], *, actor_id: int) -> tuple[dict[str, Any], dict[str, Any]]:
        if action not in WRITE_ACTIONS:
            raise ValueError("Esa escritura no está disponible.")
        if action == "accounting.entries.create":
            arguments = _normalize_entry_lines(arguments)
        schema = self._schema(action)
        values = schema.model_validate(arguments).model_dump(mode="python", exclude_unset=True)
        if action == "customers.update":
            from app.adapters.api.customers import CustomerPatch
            values["values"] = CustomerPatch.model_validate(values["values"]).model_dump(exclude_unset=True)
        elif action == "tickets.update":
            from app.adapters.api.admin_tickets import TicketPatch
            values["values"] = TicketPatch.model_validate(values["values"]).model_dump(exclude_unset=True)
        elif action == "inventory.update":
            part_values = {**values["values"], "code": values["code"]}
            values["values"] = InventoryPartWrite.model_validate(part_values).values()
        elif action == "suppliers.update":
            from app.adapters.api.purchases import SupplierPatch
            values["values"] = SupplierPatch.model_validate(values["values"]).model_dump(exclude_unset=True)
        elif action == "purchases.update":
            from app.adapters.api.purchases import PurchasePatch
            values["values"] = PurchasePatch.model_validate(values["values"]).model_dump(exclude_unset=True, mode="python")
        elif action == "purchase_orders.update":
            from app.adapters.api.purchase_orders import PurchaseOrderPatch
            values["values"] = PurchaseOrderPatch.model_validate(values["values"]).model_dump(exclude_unset=True, mode="python")
        elif action == "sales_quotes.create":
            if values.get("customer_id") is None:
                raise ValueError("Selecciona el cliente comercial para la cotización.")
        elif action == "sales_quotes.accept":
            from app.adapters.api.sales_quotes import ManualAcceptance
            ManualAcceptance.model_validate({key: value for key, value in values.items() if key != "quote_id"})
        elif action == "sales_quotes.cancel":
            from app.adapters.api.sales_quotes import QuoteCancellation
            QuoteCancellation.model_validate({key: value for key, value in values.items() if key != "quote_id"})
        elif action == "sales_quotes.confirm_payment":
            from app.adapters.api.sales_quotes import PaymentConfirmation
            PaymentConfirmation.model_validate({key: value for key, value in values.items() if key != "quote_id"})
        elif action == "purchases.receive":
            from app.adapters.api.purchases import ReceiptWrite
            body = ReceiptWrite.model_validate({"notes": values.get("notes"), "items": values["items"]})
            values["notes"] = body.notes
            values["items"] = [line.model_dump() for line in body.items]
        elif action == "purchase_orders.receive":
            from app.adapters.api.purchase_orders import PurchaseOrderReceiptWrite
            body = PurchaseOrderReceiptWrite.model_validate({"notes": values.get("notes"), "items": values["items"]})
            values["notes"] = body.notes
            values["items"] = [line.model_dump() for line in body.items]
        self._validate_references(action, values)
        precondition: dict[str, Any] = {}
        if action == "inventory.adjust_stock":
            parts = self._service("inventory").list_parts()
            part = next((item for item in parts if item.id == values["part_id"]), None)
            if part is None:
                raise LookupError("Repuesto no encontrado.")
            if part.current_stock != values["expected_stock"]:
                raise ValueError("El stock cambió desde la consulta; vuelve a formular la operación.")
            precondition["expected_stock"] = part.current_stock
            preview = {"part_id": part.id, "code": part.code, "name": part.name,
                       "stock_actual": part.current_stock, "stock_final": values["counted_stock"],
                       "reason": values["reason"]}
        elif action == "sales_quotes.accept":
            quote = self._service("sales_quotes").get_sales_quote(values["quote_id"])
            if quote is None:
                raise LookupError("Cotización no encontrada.")
            preview = {"quote_id": values["quote_id"], "estado_actual": quote.get("status"),
                       "cliente": quote.get("customer_name_snapshot"), "total": quote.get("total_amount"),
                       "accion": "registrar aceptación presencial y reservar inventario"}
        elif action == "sales_quotes.confirm_payment":
            quote = self._service("sales_quotes").get_sales_quote(values["quote_id"])
            if quote is None:
                raise LookupError("Cotización no encontrada.")
            preview = {"quote_id": values["quote_id"], "estado_actual": quote.get("status"),
                       "total": quote.get("total_amount"), "payment_status": quote.get("payment_status"),
                       "metodo": values["method"], "accion": "confirmar pago recibido"}
        else:
            preview = {"accion": action, "datos": values}
            if "actor_id" in preview["datos"] or "user_id" in preview["datos"]:
                raise ValueError("No se permite proporcionar un actor; se toma de la sesión ADMIN.")
        return values, {"action": action, "values": json_safe(preview), "precondition": precondition}

    def execute(self, action: str, values: dict[str, Any], *, actor_id: int, idempotency_key: UUID,
                precondition: dict[str, Any] | None = None) -> dict[str, Any]:
        from app.adapters.api.admin_tickets import TicketCreate, TicketPatch
        from app.adapters.api.customers import CustomerPatch
        from app.adapters.api.inventory import InventoryPartWrite, StockCountWrite
        from app.adapters.api.purchase_orders import PurchaseOrderWrite, PurchaseOrderPatch
        from app.adapters.api.purchases import PurchaseWrite, PurchasePatch, SupplierWrite, SupplierPatch, ReceiptWrite
        from app.adapters.api.accounting import CreateEntryIn

        if action == "customers.create":
            result = self._service("customers").create_manual(values=values, actor_id=actor_id)
        elif action == "customers.update":
            patch = CustomerPatch.model_validate(values["values"]).model_dump(exclude_unset=True)
            result = self._service("customers").update_customer(customer_id=values["customer_id"], values=patch, actor_id=actor_id)
        elif action == "tickets.create":
            body = TicketCreate.model_validate(values)
            ticket_values = body.model_dump()
            ticket_values.update(origin="MANUAL", status="NEW", diagnosis_type="NONE", technician_id=None,
                estimated_labor_hours=Decimal("0.0"), is_remote_service=False,
                hardware_diagnosis=None, software_diagnosis=None)
            from uuid import uuid4
            result = self._service("tickets").create_manual_ticket(
                values=ticket_values, code=f"TCK-{uuid4().hex[:12].upper()}", actor_id=actor_id)
            result = {"ticket_id": result, "status": "NEW"}
        elif action == "tickets.update":
            patch = TicketPatch.model_validate(values["values"]).model_dump(exclude_unset=True)
            result = self._service("tickets").update_ticket(ticket_id=values["ticket_id"], values=patch, actor_id=actor_id)
        elif action == "inventory.create":
            result = self._service("inventory").create_part(InventoryPartWrite.model_validate(values).values(), actor_id=actor_id)
        elif action == "inventory.update":
            body = InventoryPartWrite.model_validate(values["values"])
            result = self._service("inventory").update_part(values["code"], body.values(), actor_id=actor_id)
        elif action == "inventory.adjust_stock":
            service = self._service("inventory")
            payload = {"operation": "ADJUSTMENT", "part_id": values["part_id"],
                       "counted_stock": values["counted_stock"], "reason": values["reason"]}
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            result = service.adjust_stock(part_id=values["part_id"], count=values["counted_stock"],
                actor_id=actor_id, reason=values["reason"], idempotency_key=idempotency_key, request_hash=digest,
                expected_stock=(precondition or {}).get("expected_stock"))
        elif action == "suppliers.create":
            result = self._service("suppliers").create_supplier(
                SupplierWrite.model_validate(values).model_dump(), actor_id=actor_id
            )
        elif action == "suppliers.update":
            patch = SupplierPatch.model_validate(values["values"]).model_dump(exclude_unset=True)
            result = self._service("suppliers").update_supplier(
                values["supplier_id"], patch, actor_id=actor_id
            )
        elif action == "purchases.create":
            body = PurchaseWrite.model_validate(values)
            result = self._service("purchases").create_purchase(actor_id=actor_id, values=body.model_dump(mode="python"))
        elif action == "purchases.update":
            patch = PurchasePatch.model_validate(values["values"]).model_dump(exclude_unset=True)
            result = self._service("purchases").update_purchase(actor_id=actor_id, purchase_id=values["purchase_id"], values=patch)
        elif action == "purchases.cancel":
            result = self._service("purchases").cancel_purchase(actor_id=actor_id, purchase_id=values["id"])
        elif action == "purchases.receive":
            body = ReceiptWrite.model_validate({"notes": values.get("notes"), "items": values["items"]})
            result = self._service("purchases").receive_purchase(actor_id=actor_id,
                purchase_id=values["purchase_id"], idempotency_key=idempotency_key,
                items=[line.model_dump() for line in body.items], notes=body.notes)
        elif action == "purchase_orders.create":
            body = PurchaseOrderWrite.model_validate(values)
            result = self._service("purchase_orders").create_order(actor_id=actor_id, values=body.model_dump(mode="python"))
        elif action == "purchase_orders.update":
            patch = PurchaseOrderPatch.model_validate(values["values"]).model_dump(exclude_unset=True, mode="python")
            result = self._service("purchase_orders").update_draft_order(actor_id=actor_id, order_id=values["order_id"], values=patch)
        elif action == "purchase_orders.issue":
            result = self._service("purchase_orders").issue_order(actor_id=actor_id, order_id=values["id"])
        elif action == "purchase_orders.cancel":
            result = self._service("purchase_orders").cancel_order(actor_id=actor_id, order_id=values["order_id"], reason=values["reason"])
        elif action == "purchase_orders.receive":
            from app.adapters.api.purchase_orders import PurchaseOrderReceiptWrite
            body = PurchaseOrderReceiptWrite.model_validate({"notes": values.get("notes"), "items": values["items"]})
            result = self._service("purchase_orders").receive_order(actor_id=actor_id, order_id=values["order_id"],
                idempotency_key=idempotency_key,
                values={"items": [item.model_dump() for item in body.items], "notes": body.notes})
        elif action == "sales_quotes.create":
            from app.adapters.api.sales_quotes import SalesQuoteWrite
            body = SalesQuoteWrite.model_validate(values)
            result = self._service("sales_quotes").create_direct_sales_quote(customer_id=body.customer_id,
                actor_user_id=actor_id, lines=[line.model_dump() for line in body.lines],
                expires_at=body.expires_at, observations=body.observations)
        elif action == "sales_quotes.accept":
            from app.adapters.api.sales_quotes import ManualAcceptance
            body = ManualAcceptance.model_validate({"confirmation_channel": values.get("confirmation_channel", "OTHER"), "notes": values.get("notes")})
            repo = self._service("sales_quotes")
            quote = repo.get_sales_quote(values["quote_id"])
            if quote is None:
                raise LookupError("Cotización no encontrada.")
            result = repo.accept_direct_sales_quote(quote_id=values["quote_id"], customer_id=int(quote["customer_id"]),
                actor_user_id=actor_id, idempotency_key=str(idempotency_key),
                confirmation_channel=body.confirmation_channel, notes=body.notes)
        elif action == "sales_quotes.cancel":
            repo = self._service("sales_quotes")
            result = repo.resolve_direct_sales_quote(quote_id=values["quote_id"], customer_id=None,
                actor_user_id=actor_id, target_status="CANCELLED", notes=values.get("notes"))
        elif action == "sales_quotes.confirm_payment":
            repo = self._service("sales_quotes")
            result = repo.confirm_direct_sales_payment(quote_id=values["quote_id"], actor_user_id=actor_id,
                idempotency_key=str(idempotency_key), method=values["method"],
                transaction_reference=values.get("transaction_reference"), notes=values.get("notes"))
        elif action == "accounting.entries.create":
            from app.application.accounting import AccountingService
            body = CreateEntryIn.model_validate(values)
            result = self._service("accounting").create_entry(actor_id=actor_id, idempotency_key=idempotency_key, draft=body.to_draft())
        elif action == "accounting.entries.reverse":
            body = EntryReverse.model_validate(values)
            result = self._service("accounting").reverse_entry(actor_id=actor_id, entry_id=body.entry_id,
                operation_date=body.operation_date, reason=body.reason)
        else:
            raise ValueError("Esa escritura no está disponible.")
        return json_safe(result)

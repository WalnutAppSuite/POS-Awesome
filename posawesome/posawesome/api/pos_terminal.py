"""
Generic POS Terminal Payment API.

This module provides a provider-agnostic interface for POS terminal payments.
The frontend passes the POS Terminal doc name (physical machine). This module
reads POS Terminal → POS Terminal Provider → imports the provider module.

Architecture:
    Frontend (Payments.vue)
        → pos_terminal.initiate_payment(provider="POS-001-ICICI-12345")
            → POS Terminal (merchant_id, terminal_id)
            → POS Terminal Provider (URLs, client_id, API keys)
            → providers/icici.py  (or hdfc.py, sbi.py in future)
"""

import json

import frappe
from frappe import _
from frappe.utils import now


# =============================================================================
# PROVIDER REGISTRY
# =============================================================================


def get_provider_module(terminal_doc_name):
    """
    Load POS Terminal → POS Terminal Provider and import the provider module.

    Args:
        terminal_doc_name: POS Terminal doc name e.g. "POS-001-ICICI-12345"

    Returns:
        tuple: (provider_module, terminal_doc, provider_doc)
    """
    terminal = frappe.get_doc("POS Terminal", terminal_doc_name)
    if not terminal.enabled:
        frappe.throw(_("POS Terminal '{0}' is disabled").format(terminal_doc_name))

    provider = frappe.get_doc("POS Terminal Provider", terminal.provider)
    if not provider.enabled:
        frappe.throw(_("POS Terminal Provider '{0}' is disabled").format(terminal.provider))
    if not provider.module_path:
        frappe.throw(_("Module Path is not configured for provider '{0}'").format(terminal.provider))

    return frappe.get_module(provider.module_path), terminal, provider


# =============================================================================
# PAYMENT LOG HELPERS (shared across all providers)
# =============================================================================


def create_payment_log(provider, transaction_ref, amount, status,
                       payment_mode=None, request_data=None, initiated_at=None):
    """Create a POS Terminal Payment Log entry."""
    doc = frappe.get_doc({
        "doctype": "POS Terminal Payment Log",
        "provider": provider,
        "transaction_ref": transaction_ref,
        "amount": amount,
        "status": status,
        "payment_mode": payment_mode or "",
        "request_data": request_data or "",
        "initiated_at": initiated_at or now(),
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def update_payment_log(log_name, **kwargs):
    """Update specific fields on a POS Terminal Payment Log entry."""
    updates = {}
    for field in ("status", "transaction_id", "response_data", "error_message", "callback_data"):
        if field in kwargs and kwargs[field] is not None:
            updates[field] = kwargs[field]

    terminal_statuses = {"SUCCESS", "FAILED", "CANCELLED", "TIMEOUT", "ERROR"}
    if updates.get("status") and updates["status"].upper() in terminal_statuses:
        updates["completed_at"] = now()

    if updates:
        frappe.db.set_value(
            "POS Terminal Payment Log", log_name, updates, update_modified=True
        )
        frappe.db.commit()


# =============================================================================
# WHITELISTED API METHODS (called by frontend)
# =============================================================================


@frappe.whitelist()
def initiate_payment(invoice_data):
    """
    Initiate a POS terminal payment. Called by Payments.vue.

    Args:
        invoice_data (str/dict): JSON with amount, invoice_name, customer_name,
                                  payment_mode, provider (doc name)
    """
    if isinstance(invoice_data, str):
        invoice_data = json.loads(invoice_data)

    for field in ("amount", "invoice_name", "provider"):
        if not invoice_data.get(field):
            return {
                "success": False,
                "message": _("Missing required field: {0}").format(field),
            }

    terminal_doc_name = invoice_data["provider"]
    provider_module, terminal, provider = get_provider_module(terminal_doc_name)

    return provider_module.initiate_payment(invoice_data, terminal_doc_name)


@frappe.whitelist()
def check_payment_status(transaction_id, provider):
    """
    Check the status of a POS terminal payment.

    Args:
        transaction_id (str): The transaction ID to check
        provider (str): Provider doc name (e.g., "POS-001-ICICI")
    """
    if not transaction_id:
        return {"success": False, "status": "ERROR", "message": _("Transaction ID is required")}

    provider_module, terminal, provider_doc = get_provider_module(provider)
    return provider_module.check_payment_status(transaction_id, provider)


@frappe.whitelist()
def cancel_payment(transaction_id, provider):
    """
    Cancel a pending POS terminal payment.

    Args:
        transaction_id (str): The transaction ID to cancel
        provider (str): Provider doc name (e.g., "POS-001-ICICI")
    """
    if not transaction_id:
        return {"success": False, "message": _("Transaction ID is required")}

    provider_module, terminal, provider_doc = get_provider_module(provider)
    return provider_module.cancel_payment(transaction_id, provider)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def handle_callback(**kwargs):
    """
    Callback endpoint for POS terminal to POST transaction results.

    URL: /api/method/posawesome.posawesome.api.pos_terminal.handle_callback

    This is allow_guest=True because the terminal cannot authenticate with Frappe.
    """
    callback_data = kwargs
    if not callback_data:
        try:
            callback_data = json.loads(frappe.request.data)
        except Exception:
            callback_data = {}

    erp_tran_id = str(
        callback_data.get("ErpTranId")
        or callback_data.get("erp_tran_id")
        or ""
    ).strip()

    if not erp_tran_id:
        return {"success": False, "message": "Missing ErpTranId"}

    log = frappe.db.get_value(
        "POS Terminal Payment Log",
        {"transaction_ref": erp_tran_id},
        ["name", "provider"],
        as_dict=True,
    )

    if not log:
        return {"success": False, "message": f"Unknown transaction: {erp_tran_id}"}

    # log.provider is the POS Terminal doc name
    provider_module, terminal, provider_doc = get_provider_module(log.provider)
    if hasattr(provider_module, "handle_callback"):
        return provider_module.handle_callback(callback_data, log.provider)

    return {"success": False, "message": "Provider does not support callbacks"}

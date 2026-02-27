"""
ICICI POS Terminal Provider (Lyra Network API).

This module implements the provider interface for ICICI POS terminals.
It is called by the generic pos_terminal.py dispatcher.

Provider interface methods (called by pos_terminal.py):
    initiate_payment(invoice_data, provider_doc)       → dict
    check_payment_status(transaction_id, provider_doc) → dict
    cancel_payment(transaction_id, provider_doc)       → dict
    handle_callback(callback_data, provider_doc)       → dict

Flow:
    1. initiate_payment       → PushTxn API     → returns PENDING (machine shows payment screen)
    2. Frontend polls check_payment_status → CheckStatus API → returns SUCCESS/FAILED/PENDING/CANCELLED/TIMEOUT
    3. User can cancel via cancel_payment  → CancelTxn API (if configured) + updates log
    4. Terminal sends callback (optional)  → handle_callback → updates payment log with full details

API Docs (ICICI Lyra):
    PushTxn     → Initiate transaction on terminal
    CheckStatus → Poll for transaction result (also returns cancel/timeout status)
    CancelTxn   → Cancel ongoing transaction on machine (optional, uses cancel_txn_url)
    Callback    → Terminal POSTs result after transaction completes

ResponseCode mapping (CheckStatus):
    "00" = SUCCESS, "01" = PENDING, "03" = CANCELLED, "04" = PENDING, "05" = TIMEOUT
"""

import json

import frappe
import requests
from frappe import _
from frappe.utils import now

from posawesome.posawesome.api.pos_terminal import (
    create_payment_log,
    update_payment_log,
)

# All terminal statuses that mean "transaction is done, stop polling"
TERMINAL_STATUSES = {"SUCCESS", "FAILED", "DECLINED", "CANCELLED", "TIMEOUT", "ERROR"}


def _get_settings(terminal_doc_name):
    """
    Load settings from POS Terminal + POS Terminal Provider.

    POS Terminal has: merchant_id, terminal_id
    POS Terminal Provider has: client_id, URLs, API keys, timeout, debug_mode
    """
    terminal = frappe.get_doc("POS Terminal", terminal_doc_name)
    if not terminal.enabled:
        frappe.throw(_("POS Terminal '{0}' is not enabled").format(terminal_doc_name))

    provider = frappe.get_doc("POS Terminal Provider", terminal.provider)
    if not provider.enabled:
        frappe.throw(_("POS Terminal Provider '{0}' is not enabled").format(terminal.provider))

    return {
        "merchant_id": terminal.merchant_id,
        "terminal_id": terminal.terminal_id,
        "client_id": provider.client_id,
        "source_id": provider.source_id or "",
        "push_txn_url": provider.push_txn_url,
        "check_status_url": provider.check_status_url,
        "cancel_txn_url": provider.cancel_txn_url or "",
        "timeout": provider.timeout_seconds or 120,
        "debug_mode": provider.debug_mode,
    }


def _debug_log(settings, title, message):
    """Log debug info if debug_mode is enabled."""
    if settings.get("debug_mode"):
        frappe.log_error(title=title, message=message)


def _parse_response(response_data):
    """Extract common fields from ICICI Lyra API response."""
    return {
        "response_code": str(response_data.get("ResponseCode") or "").strip(),
        "response_desc": str(response_data.get("ResponseDesc") or "").strip(),
        "auth_code": response_data.get("AuthCode") or response_data.get("auth_code") or "",
        "rrn": response_data.get("RRN") or "",
        "tran_id": response_data.get("Tran_Id") or response_data.get("TranId") or "",
        "transaction_id": str(
            response_data.get("erp_tran_id")
            or response_data.get("transaction_id")
            or ""
        ),
    }


def _normalize_push_response(response_data):
    """
    Normalize PushTxn response.
    "00" = machine accepted request (PENDING — customer hasn't paid yet).
    Anything else = machine rejected the request (FAILED).
    """
    parsed = _parse_response(response_data)
    rc = parsed["response_code"]
    desc = parsed["response_desc"].upper()

    if rc == "00" or desc in ("SUCCESS", "PENDING", "INITIATED"):
        parsed["status"] = "PENDING"  # Always PENDING for PushTxn — payment not done yet
    else:
        parsed["status"] = "FAILED"

    parsed["message"] = parsed["response_desc"] or parsed["status"]
    return parsed


def _normalize_status_response(response_data):
    """
    Normalize CheckStatus response using ResponseCode + ResponseDesc.

    Confirmed ICICI Lyra CheckStatus ResponseCode values:
        "00" → SUCCESS (payment done, RRN present)
        "01" → "No data found." (transaction not registered yet — PENDING)
        "03" → "Transaction cancelled" (cancelled on machine — CANCELLED)
        "04" → "Please switch to dashboard for ERP transaction." (PENDING)
        "05" → "Transaction Timeout" (machine timed out — TIMEOUT)

    Unknown codes (02, 06, 07+) — logged to Error Log for discovery.
    ResponseCode "01" and "04" = PENDING, keep polling silently.
    """
    parsed = _parse_response(response_data)
    rc = parsed["response_code"]
    desc = parsed["response_desc"]

    # Map ResponseCode to status — only confirmed codes here
    status_map = {
        "00": "SUCCESS",
        "01": "PENDING",     # "No data found." — keep polling silently
        "03": "CANCELLED",   # "Transaction cancelled"
        "04": "PENDING",     # "Please switch to dashboard..." — keep polling
        "05": "TIMEOUT",     # "Transaction Timeout"
    }

    if rc in status_map:
        parsed["status"] = status_map[rc]
    else:
        # Unknown ResponseCode — log it so we can map it later
        frappe.log_error(
            title=f"POS Terminal - Unknown ResponseCode: {rc}",
            message=(
                f"ResponseCode: {rc}\n"
                f"ResponseDesc: {desc}\n"
                f"Full Response: {json.dumps(response_data, indent=2, default=str)}"
            ),
        )
        # Try to guess from ResponseDesc
        desc_upper = desc.upper()
        if "SUCCESS" in desc_upper or "APPROVED" in desc_upper:
            parsed["status"] = "SUCCESS"
        elif "FAIL" in desc_upper or "DECLINE" in desc_upper or "REJECT" in desc_upper:
            parsed["status"] = "FAILED"
        elif "CANCEL" in desc_upper:
            parsed["status"] = "CANCELLED"
        elif "TIMEOUT" in desc_upper or "TIMED OUT" in desc_upper:
            parsed["status"] = "TIMEOUT"
        else:
            parsed["status"] = "PENDING"

    parsed["message"] = desc or parsed["status"]
    return parsed


def _normalize_callback_data(callback_data):
    """
    Normalize the callback response from terminal.
    The callback contains rich transaction details (card type, RRN, auth code, UPI VPA, etc.)
    """
    txn_status = str(callback_data.get("TxnStatus") or "").upper()

    if "APPROVED" in txn_status or "SUCCESS" in txn_status or "COMPLETED" in txn_status:
        status = "SUCCESS"
    elif "FAIL" in txn_status or "DECLINE" in txn_status:
        status = "FAILED"
    elif "CANCEL" in txn_status:
        status = "CANCELLED"
    elif "TIMEOUT" in txn_status or "TIME" in txn_status:
        status = "TIMEOUT"
    else:
        status = "FAILED"

    return {
        "status": status,
        "auth_code": callback_data.get("AuthCode") or "",
        "rrn": callback_data.get("RRN") or "",
        "transaction_id": callback_data.get("ErpTranId") or callback_data.get("TranId") or "",
        "tran_type": callback_data.get("TranType") or "",
        "card_type": callback_data.get("CrdType") or "",
        "message": callback_data.get("TxnStatus") or status,
    }


# =============================================================================
# PROVIDER INTERFACE METHODS
# =============================================================================


def _get_tran_type(payment_mode):
    """
    Map payment mode name to ICICI Lyra tran_type code.

    Tran type list (from ICICI doc):
        1  = Card
        16 = UPI Sale
        0 = Online (Card or QR)
    """
    mode = (payment_mode or "").strip().upper()
    tran_type_map = {
        "UPI": 16,
        "CARD": 1,
        "ONLINE": 0,
    }
    return tran_type_map.get(mode, 0)


def initiate_payment(invoice_data, provider_doc_name):
    """
    Send PushTxn to ICICI POS machine.

    Returns immediately with PENDING status — frontend must poll check_payment_status.
    """
    amount = invoice_data["amount"]
    invoice_name = invoice_data["invoice_name"]
    payment_mode = invoice_data.get("payment_mode", "Card")

    try:
        settings = _get_settings(provider_doc_name)
    except Exception as e:
        return {"success": False, "message": str(e)}

    amount_str = "{:.2f}".format(float(amount))
    erp_tran_id = frappe.generate_hash(length=15)
    tran_type = _get_tran_type(payment_mode)

    payload = {
        "mid": settings["merchant_id"],
        "tid": settings["terminal_id"],
        "tran_type": tran_type,
        "amount": amount_str,
        "bill_no": invoice_name,
        "tip": "0.00",
        "erp_tran_id": erp_tran_id,
        "erp_client_id": settings["client_id"],
        "source_id": settings["source_id"],
    }

    log_entry = create_payment_log(
        provider=provider_doc_name,
        transaction_ref=erp_tran_id,
        amount=float(amount),
        status="INITIATED",
        payment_mode=payment_mode,
        request_data=json.dumps(payload),
        initiated_at=now(),
    )

    try:
        _debug_log(settings, "POS Terminal - PushTxn Request",
                   f"Invoice: {invoice_name}\nURL: {settings['push_txn_url']}\n"
                   f"Payload: {json.dumps(payload, indent=2)}")

        response = requests.post(
            settings["push_txn_url"],
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=settings["timeout"],
        )
        response_data = response.json()

        _debug_log(settings, "POS Terminal - PushTxn Response",
                   f"HTTP {response.status_code}\n"
                   f"Response: {json.dumps(response_data, indent=2)}")

        parsed = _normalize_push_response(response_data)
        transaction_id = parsed["transaction_id"] or erp_tran_id

        # PENDING = machine accepted, customer needs to complete payment
        if parsed["status"] == "PENDING":
            update_payment_log(
                log_entry, status="PENDING", transaction_id=transaction_id,
                response_data=json.dumps(response_data),
            )
            return {
                "success": False,
                "pending": True,
                "transaction_id": transaction_id,
                "log_entry": log_entry,
                "timeout_seconds": settings["timeout"],
                "message": _("Payment request sent to terminal. Waiting for customer..."),
            }

        # Machine rejected the request
        update_payment_log(
            log_entry, status=parsed["status"], transaction_id=transaction_id,
            response_data=json.dumps(response_data),
            error_message=parsed["message"],
        )
        return {"success": False, "message": parsed["message"]}

    except requests.Timeout:
        update_payment_log(log_entry, status="TIMEOUT",
                           error_message="PushTxn request timed out")
        return {"success": False, "message": _("Could not reach POS machine. Check if it is powered on.")}
    except requests.ConnectionError:
        update_payment_log(log_entry, status="ERROR",
                           error_message="Cannot connect to POS terminal API")
        return {"success": False, "message": _("Cannot connect to POS machine. Check network connection.")}
    except Exception as e:
        update_payment_log(log_entry, status="ERROR", error_message=str(e))
        frappe.log_error(title="POS Terminal - PushTxn Error",
                         message=f"Invoice: {invoice_name}\n{str(e)}\n{frappe.get_traceback()}")
        return {"success": False, "message": _("Error: {0}").format(str(e))}


def check_payment_status(transaction_id, provider_doc_name):
    """
    Check payment status via CheckStatus API. Called by frontend polling.
    """
    try:
        settings = _get_settings(provider_doc_name)
    except Exception as e:
        return {"success": False, "status": "ERROR", "message": str(e)}

    # Look up bill_no and tran_type from the original PushTxn request
    bill_no = ""
    original_tran_type = 0
    request_data_str = frappe.db.get_value(
        "POS Terminal Payment Log",
        {"transaction_ref": transaction_id, "provider": provider_doc_name},
        "request_data",
    )
    if request_data_str:
        try:
            req = json.loads(request_data_str)
            bill_no = req.get("bill_no", "")
            original_tran_type = req.get("tran_type", 0)
        except Exception:
            pass

    payload = {
        "mid": settings["merchant_id"],
        "tid": settings["terminal_id"],
        "tran_type": original_tran_type,
        "bill_no": bill_no,
        "erp_tran_id": transaction_id,
        "erp_client_id": settings["client_id"],
    }

    try:
        response = requests.post(
            settings["check_status_url"],
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        response_data = response.json()

        _debug_log(settings, "POS Terminal - CheckStatus",
                   f"erp_tran_id: {transaction_id}\n"
                   f"Response: {json.dumps(response_data, indent=2)}")

        parsed = _normalize_status_response(response_data)

        # Update payment log only when status is terminal (done — not PENDING)
        if parsed["status"] in TERMINAL_STATUSES:
            log_name = frappe.db.get_value(
                "POS Terminal Payment Log",
                {"transaction_ref": transaction_id, "provider": provider_doc_name},
                "name",
            )
            if log_name:
                update_kwargs = {
                    "status": parsed["status"],
                    "response_data": json.dumps(response_data),
                }
                if parsed["status"] != "SUCCESS":
                    update_kwargs["error_message"] = parsed["message"]
                if parsed["transaction_id"]:
                    update_kwargs["transaction_id"] = parsed["transaction_id"]
                update_payment_log(log_name, **update_kwargs)

        return {
            "success": parsed["status"] == "SUCCESS",
            "status": parsed["status"],
            "transaction_id": parsed["transaction_id"] or transaction_id,
            "auth_code": parsed["auth_code"],
            "rrn": parsed["rrn"],
            "tran_id": parsed["tran_id"],
            "message": parsed["message"],
            "response_code": parsed["response_code"],
            "response_desc": parsed["response_desc"],
        }

    except requests.Timeout:
        return {"success": False, "status": "PENDING", "transaction_id": transaction_id,
                "message": _("Status check timed out, will retry...")}
    except requests.ConnectionError:
        return {"success": False, "status": "PENDING", "transaction_id": transaction_id,
                "message": _("Network error, will retry...")}
    except Exception as e:
        frappe.log_error(title="POS Terminal - CheckStatus Error",
                         message=f"erp_tran_id: {transaction_id}\n{str(e)}\n{frappe.get_traceback()}")
        return {"success": False, "status": "ERROR", "transaction_id": transaction_id,
                "message": str(e)}


def cancel_payment(transaction_id, provider_doc_name):
    """
    Cancel from POS UI — sends CancelTxn to the machine and marks log as CANCELLED.
    If cancel_txn_url is not configured, just updates the log.
    """
    try:
        settings = _get_settings(provider_doc_name)
    except Exception as e:
        return {"success": False, "message": str(e)}

    log_name = frappe.db.get_value(
        "POS Terminal Payment Log",
        {"transaction_ref": transaction_id, "provider": provider_doc_name},
        "name",
    )

    # Read bill_no and tran_type from original PushTxn request
    bill_no = ""
    original_tran_type = 0
    if log_name:
        request_data_str = frappe.db.get_value(
            "POS Terminal Payment Log", log_name, "request_data"
        )
        if request_data_str:
            try:
                req = json.loads(request_data_str)
                bill_no = req.get("bill_no", "")
                original_tran_type = req.get("tran_type", 0)
            except Exception:
                pass

    # Send CancelTxn to machine if URL is configured
    if settings.get("cancel_txn_url"):
        payload = {
            "mid": settings["merchant_id"],
            "tid": settings["terminal_id"],
            "tran_type": original_tran_type,
            "bill_no": bill_no,
            "erp_tran_id": transaction_id,
            "erp_client_id": settings["client_id"],
        }
        try:
            response = requests.post(
                settings["cancel_txn_url"],
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
            response_data = response.json()
            _debug_log(settings, "POS Terminal - CancelTxn Response",
                       f"erp_tran_id: {transaction_id}\n"
                       f"Response: {json.dumps(response_data, indent=2)}")
        except Exception as e:
            _debug_log(settings, "POS Terminal - CancelTxn Error",
                       f"erp_tran_id: {transaction_id}\nError: {str(e)}")

    if log_name:
        update_payment_log(log_name, status="CANCELLED",
                           error_message="Cancelled by user from POS app")

    return {"success": True, "message": _("Payment cancelled")}


def handle_callback(callback_data, provider_doc_name):
    """
    Handle callback from ICICI terminal after transaction completes.

    The terminal POSTs a rich response containing card details, RRN, auth code,
    UPI VPA, etc. This is the definitive result of the transaction.
    """
    parsed = _normalize_callback_data(callback_data)

    erp_tran_id = str(
        callback_data.get("ErpTranId")
        or callback_data.get("erp_tran_id")
        or ""
    ).strip()

    if not erp_tran_id:
        frappe.log_error(title="POS Terminal - Callback Missing ErpTranId",
                         message=json.dumps(callback_data, indent=2))
        return {"success": False, "message": "Missing ErpTranId in callback"}

    log_name = frappe.db.get_value(
        "POS Terminal Payment Log",
        {"transaction_ref": erp_tran_id, "provider": provider_doc_name},
        "name",
    )

    if not log_name:
        frappe.log_error(title="POS Terminal - Callback Unknown Transaction",
                         message=f"ErpTranId: {erp_tran_id}\n{json.dumps(callback_data, indent=2)}")
        return {"success": False, "message": f"Unknown transaction: {erp_tran_id}"}

    update_kwargs = {
        "status": parsed["status"],
        "response_data": json.dumps(callback_data),
    }
    if parsed["auth_code"]:
        update_kwargs["transaction_id"] = parsed["transaction_id"]
    if parsed["status"] != "SUCCESS":
        update_kwargs["error_message"] = parsed["message"]

    # Store full callback data in callback_data field
    frappe.db.set_value(
        "POS Terminal Payment Log", log_name,
        "callback_data", json.dumps(callback_data),
        update_modified=True,
    )
    update_payment_log(log_name, **update_kwargs)

    _debug_log(
        {"debug_mode": True},
        "POS Terminal - Callback Received",
        f"ErpTranId: {erp_tran_id}\nStatus: {parsed['status']}\n"
        f"Data: {json.dumps(callback_data, indent=2)}",
    )

    return {"success": True, "status": parsed["status"], "message": parsed["message"]}

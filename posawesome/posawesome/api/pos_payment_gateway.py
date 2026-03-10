import frappe
from frappe import _
from frappe.utils import flt, get_url
import base64
import qrcode
import io


def get_payment_gateway_controller(pos_profile):
	"""
	Get payment gateway controller from POS Profile config.
	Returns the gateway Document (e.g. Easebuzz Settings, GrayQuest Settings, etc.)
	"""
	profile = frappe.get_cached_doc("POS Profile", pos_profile)

	if not profile.posa_enable_online_payment:
		frappe.throw(_("Online payment is not enabled for this POS Profile"))

	gateway_type = profile.posa_payment_gateway
	gateway_name = profile.posa_payment_gateway_controller
	if not gateway_type or not gateway_name:
		frappe.throw(_("Payment gateway not configured in POS Profile"))

	return frappe.get_cached_doc(gateway_type, gateway_name)


def build_payment_payload(invoice, customer, pos_profile, site_url):
	amount = flt(invoice.rounded_total or invoice.grand_total)
	firstname = (customer.customer_name or "Customer").split()[0]
	firstname = "".join(c for c in firstname if c.isalnum()) or "Customer"

	return {
		"amount": amount,
		"student": invoice.customer,
		"firstname": firstname,
		"phone": customer.mobile_no or "9999999999",
		"email": customer.email_id or frappe.db.get_value("User", frappe.session.user, "email") or "pos@example.com",
		"productinfo": f"POS Payment for {invoice.name}",
		"reference_doctype": "Sales Invoice",
		"reference_docname": invoice.name,
		"success_url": f"{site_url}/pos_payment_success",
		"failure_url": f"{site_url}/pos_payment_failure",
		"udf1": "Sales Invoice",
		"udf2": invoice.name,
		"udf3": str(amount),
		"udf4": "POS Profile",
		"udf5": pos_profile,
	}


def generate_qr_base64(data):
	"""Generate QR code as base64 PNG string. Temporary, not stored."""
	qr = qrcode.QRCode(version=1, box_size=10, border=4)
	qr.add_data(data)
	qr.make(fit=True)
	img = qr.make_image(fill_color="black", back_color="white")

	buffer = io.BytesIO()
	img.save(buffer, format="PNG")
	buffer.seek(0)
	return base64.b64encode(buffer.read()).decode("utf-8")


@frappe.whitelist()
def initiate_online_payment(invoice_name, pos_profile):
	"""
	Generate payment URL and QR code for online payment.
	Generic — works with any gateway that implements generate_payment_url(**kwargs).

	Args:
		invoice_name: Sales Invoice name
		pos_profile: POS Profile name

	Returns:
		dict: { payment_url, qr_code_base64 }
	"""
	try:
		controller = get_payment_gateway_controller(pos_profile)

		invoice = frappe.get_doc("Sales Invoice", invoice_name)
		customer = frappe.get_doc("Customer", invoice.customer)
		site_url = get_url()
		amount = flt(invoice.rounded_total or invoice.grand_total)

		if amount <= 0:
			frappe.throw(_("Invoice amount must be greater than zero"))

		current_status = frappe.db.get_value(
			"Sales Invoice", invoice_name, "custom_online_payment_status"
		)
		if current_status == "Success":
			frappe.throw(_("Payment already completed for this invoice"))

		payload = build_payment_payload(invoice, customer, pos_profile, site_url)
		payment_url = controller.generate_payment_url(**payload)

		if not payment_url or not str(payment_url).startswith("http"):
			frappe.log_error(
				"POS Online Payment: Invalid URL from gateway",
				f"Response: {payment_url}\nInvoice: {invoice_name}\nProfile: {pos_profile}",
			)
			frappe.throw(_("Failed to generate payment URL from gateway. Check Error Log."))

		frappe.db.set_value(
			"Sales Invoice",
			invoice_name,
			{
				"custom_online_payment_status": "Pending",
				"custom_online_payment_url": payment_url,
			},
			update_modified=False,
		)

		qr_base64 = generate_qr_base64(payment_url)

		frappe.logger("pos_payment").info(
			f"Payment initiated for {invoice_name}: amount={amount}"
		)

		return {"payment_url": payment_url, "qr_code_base64": qr_base64}

	except frappe.exceptions.ValidationError:
		raise
	except Exception:
		frappe.log_error("POS Online Payment Error", frappe.get_traceback())
		frappe.throw(_("Failed to initiate online payment. Check Error Log."))


def handle_payment_success(data):
	"""
	Process successful payment callback.
	Updates invoice and sends realtime notification to POS user.
	Gateway posts udf1=reference_doctype, udf2=reference_docname (invoice_name).
	"""
	try:
		invoice_name = data.get("udf2")
		txnid = data.get("txnid", "")
		amount = data.get("amount", "")
		status = data.get("status", "")

		frappe.logger("pos_payment").info(
			f"Payment callback received: invoice={invoice_name}, status={status}, txnid={txnid}"
		)

		if status != "success":
			frappe.logger("pos_payment").error(
				f"Payment not successful for {invoice_name}: status={status}"
			)
			return

		if not frappe.db.exists("Sales Invoice", invoice_name):
			frappe.logger("pos_payment").error(f"Sales Invoice {invoice_name} not found")
			return

		current_status = frappe.db.get_value(
			"Sales Invoice", invoice_name, "custom_online_payment_status"
		)
		if current_status == "Success":
			frappe.logger("pos_payment").info(f"Payment already processed for {invoice_name}")
			return

		update_fields = {
			"custom_online_payment_status": "Success",
			"custom_online_payment_txnid": txnid,
		}
		if txnid and frappe.get_meta("Sales Invoice").has_field("custom_utr"):
			update_fields["custom_utr"] = txnid

		frappe.db.set_value(
			"Sales Invoice",
			invoice_name,
			update_fields,
			update_modified=False,
		)
		frappe.db.commit()

		pos_user = frappe.db.get_value("Sales Invoice", invoice_name, "owner")

		frappe.publish_realtime(
			"pos_payment_success",
			{
				"invoice_name": invoice_name,
				"txnid": txnid,
				"amount": amount,
			},
			user=pos_user,
		)

		frappe.logger("pos_payment").info(
			f"Payment success for {invoice_name}: txnid={txnid}, amount={amount}, notified={pos_user}"
		)

	except Exception:
		frappe.log_error("POS Payment Success Handler Error", frappe.get_traceback())


def handle_payment_failure(data):
	"""
	Process failed payment callback.
	Updates invoice and notifies POS user.
	"""
	try:
		invoice_name = data.get("udf2")

		frappe.logger("pos_payment").info(f"Payment failure callback: invoice={invoice_name}")

		if not invoice_name or not frappe.db.exists("Sales Invoice", invoice_name):
			frappe.logger("pos_payment").warning(
				f"Payment failure for unknown invoice: {invoice_name}"
			)
			return

		frappe.db.set_value(
			"Sales Invoice",
			invoice_name,
			{"custom_online_payment_status": "Failed"},
			update_modified=False,
		)
		frappe.db.commit()

		pos_user = frappe.db.get_value("Sales Invoice", invoice_name, "owner")

		frappe.publish_realtime(
			"pos_payment_failure",
			{"invoice_name": invoice_name},
			user=pos_user,
		)

		frappe.logger("pos_payment").warning(
			f"Payment failed for {invoice_name}, notified={pos_user}"
		)

	except Exception:
		frappe.log_error("POS Payment Failure Handler Error", frappe.get_traceback())

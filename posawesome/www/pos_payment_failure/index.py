import frappe

no_cache = 1


def get_context(context):
	"""Handle gateway failure callback POST for POS payments."""
	try:
		data = frappe.form_dict

		if frappe.session.user == "Guest":
			frappe.set_user("Administrator")

		from posawesome.posawesome.api.pos_payment_gateway import (
			handle_payment_failure,
		)

		handle_payment_failure(data)
		context.show_message = True
		context.message = "Payment Failed. You can close this page and retry from the POS."

	except Exception:
		frappe.log_error(
			"POS Payment Failure Callback Error", frappe.get_traceback()
		)
		context.show_message = True
		context.message = "An error occurred."
	finally:
		if frappe.session.user == "Administrator":
			frappe.set_user("Guest")

import frappe
from frappe import _
from frappe.model.document import Document


class POSTerminal(Document):
	def validate(self):
		if not self.terminal_id:
			frappe.throw(_("Terminal ID is required"))
		if not self.merchant_id:
			frappe.throw(_("Merchant ID is required"))

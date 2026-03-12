import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_url


class POSTerminalProvider(Document):
	def validate(self):
		if self.enabled:
			required_fields = {
				"client_id": "Client ID",
				"push_txn_url": "Push Transaction URL",
				"check_status_url": "Check Status URL",
			}
			for field, label in required_fields.items():
				if not self.get(field):
					frappe.throw(_("{0} is required when provider is enabled").format(label))

		for url_field in ("push_txn_url", "check_status_url", "cancel_txn_url"):
			if self.get(url_field):
				self.set(url_field, self.get(url_field).rstrip("/"))

	def get_callback_url(self):
		if not self.callback_url:
			return ""
		return get_url(f"/api/method/{self.callback_url}")

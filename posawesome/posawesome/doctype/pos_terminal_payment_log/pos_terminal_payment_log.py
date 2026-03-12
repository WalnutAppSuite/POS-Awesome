import frappe
from frappe.model.document import Document


class POSTerminalPaymentLog(Document):
    def before_save(self):
        if self.invoice and not self.customer:
            customer = frappe.db.get_value("Sales Invoice", self.invoice, "customer")
            if customer:
                self.customer = customer

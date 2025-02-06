<template>
  <div>
    <!-- Customer Name Input -->
    <v-text-field 
      density="compact"
      clearable
      variant="outlined"
      color="primary"
      :label="frappe._('Reference Number')"
      v-model="customer"
      bg-color="white"
      :disabled="readonly"
      append-inner-icon="mdi-arrow-right"
      @click:append-inner="new_customer" 
      @click:prepend-inner="go_back"
    ></v-text-field>

    <!-- Student Name Input (Auto-filled and Read-Only after selection) -->
    <v-text-field 
      density="compact"
      clearable
      variant="outlined"
      color="primary"
      :label="frappe._('Student Name')"
      v-model="customer_code"
      bg-color="white"
      :disabled="student_readonly"
    ></v-text-field>
    
    <div class="mb-8">
      <UpdateCustomer></UpdateCustomer>
    </div>
  </div>
</template>

<script>
import UpdateCustomer from './UpdateCustomer.vue';

export default {
  data: () => ({
    pos_profile: '',
    customers: [],
    customer: '',
    customer_code: '', // Student Name field
    readonly: false,
    student_readonly: false, // Make Student Name readonly after autofill
    customer_info: {},
  }),

  components: {
    UpdateCustomer,
  },

  methods: {
    get_customer_names() {
      var vm = this;
      if (this.customers.length > 0) return;

      if (vm.pos_profile.posa_local_storage && localStorage.customer_storage) {
        vm.customers = JSON.parse(localStorage.getItem('customer_storage'));
      }

      frappe.call({
        method: 'posawesome.posawesome.api.posapp.get_customer_names',
        args: { pos_profile: this.pos_profile.pos_profile },
        callback: function (r) {
          if (r.message) {
            vm.customers = r.message;
            if (vm.pos_profile.posa_local_storage) {
              localStorage.setItem('customer_storage', JSON.stringify(r.message));
            }
          }
        },
      });
    },

    async new_customer() {
      if (!this.customer) {
        frappe.msgprint(__('Please enter a customer name first.'));
        return;
      }

      let vm = this;

      // Step 1: Check if customer exists in 'Customer' doctype
      frappe.call({
        method: 'frappe.client.get_list',
        args: {
          doctype: 'Customer',
          filters: { 'customer_name': this.customer },
          fields: ['name']
        },
        callback: function (response) {
          if (response.message.length === 0) {
            // Step 2: If customer doesn't exist, insert a new record
            frappe.call({
              method: 'frappe.client.insert',
              args: {
                doc: {
                  doctype: 'Customer',
                  customer_name: vm.customer,
                  customer_type: 'Individual', // Adjust as needed
                  customer_group: 'Student', // Adjust as needed
                }
              },
              callback: function (insertResponse) {
                if (insertResponse.message) {
                  frappe.msgprint(__('Customer created successfully: ' + vm.customer));
                }
              },
              error: function (err) {
                console.error('Error inserting customer:', err);
                frappe.msgprint(__('Failed to create customer.'));
              }
            });
          }
        }
      });

      // Step 3: Fetch the student name from 'Student' Doctype and auto-fill
      frappe.call({
        method: 'frappe.client.get_list',
        args: {
          doctype: 'Student',
          filters: { 'name': this.customer },
          fields: ['name', 'student_name']
        },
        callback: function (r) {
          if (r.message && r.message.length > 0) {
            let student = r.message[0]; // Assuming first match
            vm.customer_code = student.student_name; // Auto-fill Student Name
            vm.student_readonly = true; // Make Student Name read-only
          } else {
            frappe.msgprint(__('No student found for this customer.'));
            vm.student_readonly = false; // Keep editable if no match
          }
        },
        error: function (err) {
          console.error('Error fetching student details:', err);
        }
      });
    },

    edit_customer() {
      this.eventBus.emit('open_update_customer', this.customer_info);
    },

    customFilter(itemText, queryText, itemRow) {
      const item = itemRow.raw;
      const textOne = item.customer_name ? item.customer_name.toLowerCase() : '';
      const textTwo = item.tax_id ? item.tax_id.toLowerCase() : '';
      const textThree = item.email_id ? item.email_id.toLowerCase() : '';
      const textFour = item.mobile_no ? item.mobile_no.toLowerCase() : '';
      const textFifth = item.name.toLowerCase();
      const searchText = queryText.toLowerCase();

      return (
        textOne.includes(searchText) ||
        textTwo.includes(searchText) ||
        textThree.includes(searchText) ||
        textFour.includes(searchText) ||
        textFifth.includes(searchText)
      );
    }
  },

  created: function () {
    this.$nextTick(function () {
      this.eventBus.on('register_pos_profile', (pos_profile) => {
        this.pos_profile = pos_profile;
        this.get_customer_names();
      });
      this.eventBus.on('payments_register_pos_profile', (pos_profile) => {
        this.pos_profile = pos_profile;
        this.get_customer_names();
      });
      this.eventBus.on('set_customer', (customer) => {
        this.customer = customer;
      });
      this.eventBus.on('add_customer_to_list', (customer) => {
        this.customers.push(customer);
      });
      this.eventBus.on('set_customer_readonly', (value) => {
        this.readonly = value;
      });
      this.eventBus.on('set_customer_info_to_edit', (data) => {
        this.customer_info = data;
      });
      this.eventBus.on('fetch_customer_details', () => {
        this.get_customer_names();
      });
    });
  },

  watch: {
    customer() {
      this.eventBus.emit('update_customer', this.customer);
    },
  },
};
</script>

<template>
  <div>
    <v-text-field
      density="compact"
      clearable
      variant="outlined"
      color="primary"
      :label="frappe._('Reference Number')"
      v-model.lazy="customer"
      bg-color="white"
      :disabled="readonly"
      append-inner-icon="mdi-arrow-right"
      @click:append-inner="new_customer"
      @keyup.enter="new_customer"
      @click:prepend-inner="go_back"
      @input="customer = customer.toUpperCase()"
    ></v-text-field>


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
import { debounce } from "lodash";

export default {
  data: () => ({
    pos_profile: '',
    customer: '',
    customer_code: '',
    readonly: false,
    student_readonly: false,
    customer_info: {},
  }),

  components: {
    UpdateCustomer,
  },

  methods: {
    async new_customer() {
      if (!this.customer) {
        frappe.msgprint(__('Please enter a customer name first.'));
        return;
      }

      let vm = this;
      const profiles = [
        { name: "Uniform Fursungi", prefix: "FU" },
        { name: "Uniform Shivane", prefix: "SH" },
        { name: "Uniform Wakad", prefix: "WA" }
      ];

      if (profiles.some(profile =>
          this.pos_profile.pos_profile.name === profile.name &&
          this.customer.startsWith(profile.prefix)
        )){
        frappe.call({
          method: 'frappe.client.get_list',
          args: {
            doctype: 'Customer',
            filters: { 'customer_name': this.customer },
            fields: ['name']
          },
          callback: function (response) {
            if (response.message.length === 0) {
              frappe.call({
                method: 'frappe.client.insert',
                args: {
                  doc: {
                    doctype: 'Customer',
                    customer_name: vm.customer,
                    customer_type: 'Individual',
                    customer_group: 'Student',
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

        frappe.call({
        method: 'frappe.client.get_list',
        args: {
          doctype: 'Student',
          filters: { 'name': this.customer },
          fields: ['name', 'student_name']
        },
        callback: function (r) {
          if (r.message && r.message.length > 0) {
            let student = r.message[0];
            vm.customer_code = student.student_name;
            vm.student_readonly = true;
          } else {
            frappe.msgprint(__('No student found for this customer.'));
            vm.student_readonly = false;
          }
        },
        error: function (err) {
          console.error('Error fetching student details:', err);
        }
      });
      }else{
        this.customer = ""
        frappe.msgprint({
          title: __('Validation Error'),
          message: __('Student doesn\'t belong to this branch'),
          indicator: 'red'
        });
      }
    },

    edit_customer() {
      this.eventBus.emit('open_update_customer', this.customer_info);
    },
  },

  created: function () {
    this.debouncedEmitCustomer = debounce((customer) => {
      this.eventBus.emit('update_customer', customer);
    }, 600);
    this.$nextTick(function () {
      this.eventBus.on('register_pos_profile', (pos_profile) => {
        this.pos_profile = pos_profile;
      });
      this.eventBus.on('payments_register_pos_profile', (pos_profile) => {
        this.pos_profile = pos_profile;
      });
      this.eventBus.on('set_customer', (customer) => {
        this.customer = customer;
      });
      this.eventBus.on('set_customer_readonly', (value) => {
        this.readonly = value;
      });
      this.eventBus.on('set_customer_info_to_edit', (data) => {
        this.customer_info = data;
      });
    });
  },

  watch: {
    customer() {
      this.debouncedEmitCustomer?.(this.customer);
    },
  },
};
</script>

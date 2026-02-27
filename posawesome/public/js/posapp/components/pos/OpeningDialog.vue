<template>
  <v-row justify="center">
    <v-dialog v-model="isOpen" persistent max-width="600px">
      <!-- <template v-slot:activator="{ on, attrs }">
        <v-btn color="primary" theme="dark" v-bind="attrs" v-on="on">Open Dialog</v-btn>
      </template>-->
      <v-card>
        <v-card-title>
          <span class="text-h5 text-primary">{{
            __('Create POS Opening Shift')
          }}</span>
        </v-card-title>
        <v-card-text>
          <v-container>
            <v-row>
              <v-col cols="12">
                <v-autocomplete :items="companies" :label="frappe._('Company')" v-model="company"
                  required></v-autocomplete>
              </v-col>
              <v-col cols="12">
                <v-autocomplete :items="pos_profiles" :label="frappe._('POS Profile')" v-model="pos_profile"
                  required></v-autocomplete>
              </v-col>
              <v-col cols="12" v-if="show_terminal_select">
                <v-autocomplete
                  :items="terminals"
                  item-title="label"
                  item-value="name"
                  :label="frappe._('POS Terminal')"
                  v-model="selected_terminal"
                  :loading="loading_terminals"
                  required
                ></v-autocomplete>
              </v-col>
              <v-col cols="12">
                <v-data-table :headers="payments_methods_headers" :items="payments_methods" item-key="mode_of_payment"
                  class="elevation-1" :items-per-page="itemsPerPage" hide-default-footer>
                  <template v-slot:item.amount="props">
                    <v-confirm-edit v-model:return-value="props.item.amount">
                      {{ currencySymbol(props.item.currency) }}
                      {{ formatCurrency(props.item.amount) }}
                      <v-text-field v-model="props.item.amount" :rules="[max25chars]" :label="frappe._('Edit')"
                        single-line counter type="number"></v-text-field>
                    </v-confirm-edit>
                  </template>
                </v-data-table>
              </v-col>
            </v-row>
          </v-container>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="error" theme="dark" @click="go_desk">Cancel</v-btn>
          <v-btn color="success" :disabled="is_loading" theme="dark" @click="submit_dialog">Submit</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-row>
</template>

<script>

import format from '../../format';
export default {
  mixins: [format],
  props: ['dialog'],
  data() {
    return {
      isOpen: this.dialog ? this.dialog : false,
      dialog_data: {},
      is_loading: false,
      companies: [],
      company: '',
      pos_profiles_data: [],
      pos_profiles: [],
      pos_profile: '',
      payments_method_data: [],
      payments_methods: [],
      payments_methods_headers: [
        {
          title: __('Mode of Payment'),
          align: 'start',
          sortable: false,
          value: 'mode_of_payment',
        },
        {
          title: __('Opening Amount'),
          value: 'amount',
          align: 'center',
          sortable: false,
        },
      ],
      itemsPerPage: 100,
      max25chars: (v) => v.length <= 12 || 'Input too long!', // TODO : should validate as number
      pagination: {},
      snack: false, // TODO : need to remove
      snackColor: '', // TODO : need to remove
      snackText: '', // TODO : need to remove
      terminals: [],
      selected_terminal: null,
      loading_terminals: false,
      show_terminal_select: false,
    };
  },
  watch: {
    company(val) {
      this.pos_profiles = [];
      this.pos_profiles_data.forEach((element) => {
        if (element.company === val) {
          this.pos_profiles.push(element.name);
        }
        if (this.pos_profiles.length) {
          this.pos_profile = this.pos_profiles[0];
        } else {
          this.pos_profile = '';
        }
      });
    },
    pos_profile(val) {
      this.payments_methods = [];
      this.payments_method_data.forEach((element) => {
        if (element.parent === val) {
          this.payments_methods.push({
            mode_of_payment: element.mode_of_payment,
            amount: 0,
            currency: element.currency,
          });
        }
      });
      this.fetch_terminals(val);
    },
  },
  methods: {
    close_opening_dialog() {
      this.eventBus.emit('close_opening_dialog');
    },
    get_opening_dialog_data() {
      const vm = this;
      frappe.call({
        method: 'posawesome.posawesome.api.posapp.get_opening_dialog_data',
        args: {},
        callback: function (r) {
          if (r.message) {
            r.message.companies.forEach((element) => {
              vm.companies.push(element.name);
            });
            vm.company = vm.companies[0];
            vm.pos_profiles_data = r.message.pos_profiles_data;
            vm.payments_method_data = r.message.payments_method;
          }
        },
      });
    },
    fetch_terminals(pos_profile) {
      this.terminals = [];
      this.selected_terminal = null;
      this.show_terminal_select = false;
      if (!pos_profile) return;

      const profile_data = this.pos_profiles_data.find(p => p.name === pos_profile);
      if (!profile_data || !profile_data.posa_enable_pos_terminal) return;

      this.loading_terminals = true;
      frappe.call({
        method: 'posawesome.posawesome.api.posapp.get_terminals_for_profile',
        args: { pos_profile },
        callback: (r) => {
          this.loading_terminals = false;
          if (r.message && r.message.length) {
            this.terminals = r.message.map(t => ({
              name: t.name,
              label: `${t.terminal_id} (${t.provider})`,
            }));
            this.show_terminal_select = true;
            if (this.terminals.length === 1) {
              this.selected_terminal = this.terminals[0].name;
            }
          }
        },
      });
    },
    submit_dialog() {
      if (!this.payments_methods.length || !this.company || !this.pos_profile) {
        return;
      }
      if (this.show_terminal_select && !this.selected_terminal) {
        frappe.show_alert({ message: __('Please select a POS Terminal'), indicator: 'orange' });
        return;
      }
      this.is_loading = true;
      var vm = this;
      return frappe
        .call('posawesome.posawesome.api.posapp.create_opening_voucher', {
          pos_profile: this.pos_profile,
          company: this.company,
          balance_details: this.payments_methods,
          pos_terminal: this.selected_terminal || '',
        })
        .then((r) => {
          if (r.message) {
            vm.eventBus.emit('register_pos_data', r.message);
            vm.eventBus.emit('set_company', r.message.company);
            vm.close_opening_dialog();
            is_loading = false;
          }
        });
    },
    go_desk() {
      frappe.set_route('/');
      location.reload();
    },
  },
  created: function () {
    this.$nextTick(function () {
      this.get_opening_dialog_data();
    });
  },
};
</script>

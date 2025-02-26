<template>
  <nav>
    <v-app-bar height="40" class="elevation-2">
      <v-app-bar-nav-icon @click.stop="drawer = !drawer" class="text-grey"></v-app-bar-nav-icon>
      <v-img src="/assets/posawesome/js/posapp/components/pos/pos.png" alt="POS Awesome" max-width="32" class="mr-2"
        color="primary"></v-img>
      <v-toolbar-title @click="go_desk" style="cursor: pointer" class="text-uppercase text-primary">
        <span class="font-weight-light">POS</span>
        <span>Awesome</span>
      </v-toolbar-title>

      <v-spacer></v-spacer>
      <v-btn style="cursor: unset" variant="text" color="primary">
        <span>{{ pos_profile.name || "No Profile" }}</span>
      </v-btn>
      <v-btn style="cursor: pointer" variant="text" color="primary" @click="openSalesHistory">
        <span>Sales History</span>
      </v-btn>

      <v-menu>
        <template v-slot:activator="{ props }">
          <v-btn color="primary" theme="dark" variant="text" v-bind="props">Menu</v-btn>
        </template>
        <v-card class="mx-auto" max-width="300">
          <v-list density="compact" v-model="menu_item" color="primary">
            <v-list-item @click="close_shift_dialog" v-if="showCloseShift">
              <v-icon icon="mdi-content-save-move-outline"></v-icon>
              <v-list-item-title>Close Shift</v-list-item-title>
            </v-list-item>
            <v-divider class="my-0"></v-divider>

            <v-list-item @click="logOut">
              <v-icon icon="mdi-logout"></v-icon>
              <v-list-item-title>Logout</v-list-item-title>
            </v-list-item>

            <v-list-item @click="go_about">
              <v-icon icon="mdi-information-outline"></v-icon>
              <v-list-item-title>About</v-list-item-title>
            </v-list-item>
          </v-list>
        </v-card>
      </v-menu>
    </v-app-bar>

    <v-navigation-drawer v-model="drawer" v-model:mini-variant="mini" class="bg-primary margen-top" width="170">
      <v-list theme="dark">
        <v-list-item class="px-2">
          <template v-slot:prepend>
            <v-avatar>
              <v-img :src="company_img"></v-img>
            </v-avatar>
          </template>
          <v-list-item-title>{{ company }}</v-list-item-title>
          <v-btn icon @click.stop="mini = !mini">
            <v-icon icon="mdi-chevron-left"></v-icon>
          </v-btn>
        </v-list-item>

        <v-list v-model="item" color="white">
          <v-list-item v-for="item in items" :key="item.text" @click="changePage(item.text)">
            <v-icon :icon="item.icon"></v-icon>
            <v-list-item-title>{{ item.text }}</v-list-item-title>
          </v-list-item>
        </v-list>
      </v-list>
    </v-navigation-drawer>

    <v-snackbar v-model="snack" :timeout="5000" :color="snackColor" location="top right">
      {{ snackText }}
    </v-snackbar>

    <v-dialog v-model="freeze" persistent max-width="290">
      <v-card>
        <v-card-title class="text-h5">{{ freezeTitle }}</v-card-title>
        <v-card-text>{{ freezeMsg }}</v-card-text>
      </v-card>
    </v-dialog>

    
    <v-dialog v-model="salesHistoryDialog" max-width="800">
      <v-card>
        <v-card-title class="text-h5">Sales History</v-card-title>
        <v-card-text>
          <v-data-table v-if="salesInvoices.length" :headers="tableHeaders" :items="salesInvoices" dense>
            <template v-slot:item="{ item, index }">
              <tr>
                <td>{{ index + 1 }}</td>
                <td>{{ item.customer || "Walk-in Customer" }}</td>
                <td>{{ item.name }}</td>
                <td>${{ item.grand_total.toFixed(2) }}</td>
                <td>
                  <v-btn small color="primary" @click="printInvoice(item)">Print</v-btn>
                </td>
              </tr>
            </template>
          </v-data-table>
          <v-alert v-else type="info">No sales found for today.</v-alert>
        </v-card-text>
        <v-card-actions>
          <v-btn color="red" @click="salesHistoryDialog = false">Close</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </nav>
</template>

<script>
export default {
  data() {
    return {
      drawer: false,
      mini: true,
      item: 0,
      items: [{ text: 'POS', icon: 'mdi-network-pos' }],
      pos_profile: {},
      menu_item: 0,
      snack: false,
      snackColor: '',
      snackText: '',
      company: 'POS Awesome',
      company_img: '/assets/erpnext/images/erpnext-logo.svg',
      freeze: false,
      freezeTitle: '',
      freezeMsg: '',
      salesInvoices: [],
      salesHistoryDialog: false,
      tableHeaders: [
        { text: "Sr. No", value: "index", sortable: false },
        { text: "Customer Name", value: "customer" },
        { text: "Invoice Number", value: "name" },
        { text: "Amount", value: "grand_total" },
        { text: "Actions", value: "actions", sortable: false },
      ],
    };
  },
  computed: {
    showCloseShift() {
      return this.pos_profile && !this.pos_profile.posa_hide_closing_shift;
    },
  },
  methods: {
    openSalesHistory() {
      console.log("Fetching sales history for POS Profile:", this.pos_profile.name);

      frappe.call({
        method: 'frappe.client.get_list',
        args: {
          doctype: 'Sales Invoice',
          filters: {
            pos_profile: this.pos_profile.name || '',
            posting_date: frappe.datetime.nowdate(),
          },
          fields: ['name', 'customer', 'grand_total'],
          order_by: 'creation desc',
        },
        callback: (r) => {
          console.log("Sales History Response:", r);
          this.salesInvoices = r.message || [];
          this.salesHistoryDialog = true;
        },
        error: (err) => {
          console.error("Error fetching sales history:", err);
          this.show_message({ color: 'red', title: 'Failed to fetch sales history.' });
        }
      });
    },
    close_shift_dialog() {
      this.eventBus.emit('open_closing_dialog');
    },
    show_message(data) {
      this.snack = true;
      this.snackColor = data.color;
      this.snackText = data.title;
    },
    go_desk() {
      frappe.set_route('/');
      location.reload();
    },
    changePage(key) {
      this.$emit('changePage', key);
    },
    go_about() {
      const win = window.open(
        'https://walnut.school/',
        '_blank'
      );
      win.focus();
    },
    printInvoice(invoice) {
      const print_format = this.pos_profile.print_format_for_online || this.pos_profile.print_format;
      const letter_head = this.pos_profile.letter_head || 0;
      const url = `${frappe.urllib.get_base_url()}/printview?doctype=Sales%20Invoice&name=${invoice.name}&trigger_print=1&format=${print_format}&no_letterhead=${letter_head}`;
      window.open(url, '_blank');
      setTimeout(() => {
        window.open(url, '_blank');
      }, 1000);
    },
    logOut() {
      var me = this;
      me.logged_out = true;
      return frappe.call({
        method: 'logout',
        callback: function (r) {
          if (r.exc) {
            return;
          }
          frappe.set_route('/login');
          location.reload();
        },
      });
    },
  },
  created() {
    this.$nextTick(() => {
      this.eventBus.on('register_pos_profile', (data) => {
        this.pos_profile = data.pos_profile || { name: '' };
        console.log("POS Profile Registered:", this.pos_profile);
      });
    });
  }
};
</script>

<style scoped>
.margen-top {
  margin-top: 0px;
}
</style>

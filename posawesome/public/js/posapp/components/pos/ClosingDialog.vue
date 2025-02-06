<template>
  <v-row justify="center">
    <v-dialog v-model="closingDialog" max-width="900px">
      <v-card>
        <v-card-title>
          <span class="text-h5 text-primary">{{ __('Closing POS Shift') }}</span>
        </v-card-title>
        <v-card-text class="pa-0">
          <v-container>
            <v-row>
              <v-col cols="12" class="pa-1">
                <v-data-table
                  :headers="headers"
                  :items="dialog_data.payment_reconciliation"
                  item-key="mode_of_payment"
                  class="elevation-1"
                  :items-per-page="itemsPerPage"
                  hide-default-footer
                >
                  <!-- Opening Amount -->
                  <template v-slot:item.opening_amount="{ item }">
                    {{ currencySymbol(pos_profile.currency) }}
                    {{ formatCurrency(item.opening_amount) }}
                  </template>

                  <!-- Sales -->
                  <template v-slot:item.sales="{ item }">
                    {{ currencySymbol(pos_profile.currency) }}
                    {{ formatCurrency(item.sales) }}
                  </template>

                  <!-- Returns (New Column) -->
                  <template v-slot:item.returns="{ item }">
                    {{ currencySymbol(pos_profile.currency) }}
                    {{ formatCurrency(item.returns) }}
                  </template>

                  <!-- Editable Closing Amount -->
                  <template v-slot:item.closing_amount="{ item }">
                    <v-text-field
                      v-model.number="item.closing_amount"
                      type="number"
                      label="Edit Closing Amount"
                      @input="updateDifference(item)"
                      dense
                      outlined
                    ></v-text-field>
                  </template>

                  <!-- Expected Amount -->
                  <template v-slot:item.expected_amount="{ item }">
                    {{ currencySymbol(pos_profile.currency) }}
                    {{ formatCurrency(item.expected_amount) }}
                  </template>

                  <!-- Difference -->
                  <template v-slot:item.difference="{ item }">
                    {{ currencySymbol(pos_profile.currency) }}
                    {{ formatCurrency(item.difference) }}
                  </template>
                </v-data-table>
              </v-col>
            </v-row>
          </v-container>
        </v-card-text>

        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="error" theme="dark" @click="close_dialog">{{ __('Close') }}</v-btn>
          <v-btn color="success" theme="dark" @click="submit_dialog">{{ __('Submit') }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-row>
</template>

<script>
import format from '../../format';

export default {
  mixins: [format],
  data() {
    return {
      closingDialog: false,
      itemsPerPage: 20,
      dialog_data: { payment_reconciliation: [] },
      pos_profile: '',
      headers: [
        { title: __('Mode of Payment'), value: 'mode_of_payment', align: 'start', sortable: true },
        { title: __('Opening Amount'), value: 'opening_amount', align: 'end', sortable: true },
        { title: __('Sales'), value: 'sales', align: 'end', sortable: true },
        { title: __('Returns'), value: 'returns', align: 'end', sortable: true }, // New column for returns
        { title: __('Closing Amount'), value: 'closing_amount', align: 'end', sortable: true },
        { title: __('Expected Amount'), value: 'expected_amount', align: 'end', sortable: false },
        { title: __('Difference'), value: 'difference', align: 'end', sortable: false },
      ],
    };
  },
  methods: {
    close_dialog() {
      this.closingDialog = false;
    },

    submit_dialog() {
      this.eventBus.emit('submit_closing_pos', this.dialog_data);
      this.closingDialog = false;
    },

    updateDifference(item) {
      if (!item.expected_amount) return;
      item.difference = item.expected_amount - item.closing_amount;
    },
  },

  created() {
  this.eventBus.on('open_ClosingDialog', (data) => {
    this.closingDialog = true;


  
    let totalSales = 0;
    let totalReturns = 0;

    data.pos_transactions.forEach((txn) => {
      if (txn.grand_total > 0) {
        totalSales += txn.grand_total; 
      } else {
        totalReturns += Math.abs(txn.grand_total);
      }
    });

    
    const updatedPaymentReconciliation = data.payment_reconciliation.map((item) => {
      const sales = totalSales;
      const returns = totalReturns;
      const closing_amount = item.opening_amount + sales - returns; 
      const difference = item.expected_amount - closing_amount;

      return {
        ...item,
        sales,
        returns,
        closing_amount,
        difference,
      };
    });

    this.dialog_data = {
      ...data,
      payment_reconciliation: updatedPaymentReconciliation,
    };
  });
  }

};
</script>

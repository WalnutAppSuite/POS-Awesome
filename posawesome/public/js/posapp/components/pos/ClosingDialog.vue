<template>
  <v-row justify="center">
    <v-dialog v-model="closingDialog" max-width="900px">
      <v-card>
        <v-card-title>
          <span class="text-h5 text-primary font-weight-bold">{{ __('Closing POS Shift') }}</span>
        </v-card-title>

        
        <v-card-text class="pa-4">
          <v-container>
            <v-row>
              <v-col 
                v-for="(item, index) in dialog_data.payment_reconciliation" 
                :key="index" 
                cols="12"
              >
               
                <v-card 
                  :class="{ 'hover-effect': isHovered[index] }"
                  :elevation="isHovered[index] ? 10 : 2"
                  class="pa-4 mb-3 rounded-lg transition-all"
                  @mouseover="isHovered[index] = true"
                  @mouseleave="isHovered[index] = false"
                >
                  <v-card-title class="text-h6 font-weight-bold">
                    {{ item.mode_of_payment }}
                  </v-card-title>
                  <v-divider></v-divider>

                  <v-card-text>
                    <v-row>
                     
                      <v-col cols="6">
                        <span class="font-weight-bold">Sale via Mode</span>
                      </v-col>
                      <v-col cols="6" class="text-right text-h6">
                        {{ currencySymbol(pos_profile.currency) }} {{ formatCurrency(item.sales) }}
                      </v-col>

                      
                      <v-col cols="6">
                        <span class="font-weight-bold">Opening Amount</span>
                      </v-col>
                      <v-col cols="6" class="text-right text-h6">
                        {{ currencySymbol(pos_profile.currency) }} {{ formatCurrency(item.opening_amount) }}
                      </v-col>

                     
                      <v-col cols="6">
                        <span class="font-weight-bold">Returns</span>
                      </v-col>
                      <v-col cols="6" class="text-right text-h6">
                        {{ currencySymbol(pos_profile.currency) }} {{ formatCurrency(item.returns) }}
                      </v-col>

                      <v-col cols="6">
                        <span class="font-weight-bold">Closing Amount</span>
                      </v-col>
                      <v-col cols="6">
                        <v-text-field
                          v-model.number="item.closing_amount"
                          type="number"
                          label="Edit Closing Amount"
                          @input="updateDifference(item)"
                          dense
                          outlined
                          class="text-h6"
                        ></v-text-field>
                      </v-col>

                      <v-col cols="6">
                        <span class="font-weight-bold">Expected Amount</span>
                      </v-col>
                      <v-col cols="6" class="text-right text-h6">
                        {{ currencySymbol(pos_profile.currency) }} {{ formatCurrency(item.expected_amount) }}
                      </v-col>

                      
                      <v-col cols="6">
                        <span class="font-weight-bold">Difference</span>
                      </v-col>
                      <v-col cols="6" 
                        class="text-right text-h6" 
                        :class="item.difference !== 0 ? 'text-error' : 'text-success'"
                      >
                        {{ currencySymbol(pos_profile.currency) }} {{ formatCurrency(item.difference) }}
                      </v-col>
                    </v-row>
                  </v-card-text>
                </v-card>
              </v-col>
            </v-row>
          </v-container>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="error" theme="dark" class="font-weight-bold" @click="close_dialog">
            {{ __('Close') }}
          </v-btn>
          <v-btn color="success" theme="dark" class="font-weight-bold" @click="submit_dialog">
            {{ __('Submit') }}
          </v-btn>
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
      cash_register: 0,
      upi_register: 0,
      dialog_data: { payment_reconciliation: [] },
      pos_profile: '',
      isHovered: {} 
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

      frappe.call({
        method: "posawesome.posawesome.api.posapp.get_payment_summary",
        args: {
          pos_transactions: JSON.stringify(data.pos_transactions)
        },
        callback: (response) => {

          if (response.message) {
            this.cash_register = response.message.total_cash || 0;
            this.upi_register = response.message.total_upi || 0;

            const updatedPaymentReconciliation = (data.payment_reconciliation || []).map((item) => {
              let sale_via_mode_of_payment = 0;

              if (item.mode_of_payment === "Cash") {
                sale_via_mode_of_payment = this.cash_register;
              } else if (item.mode_of_payment === "UPI") {
                sale_via_mode_of_payment = this.upi_register;
              }

              const opening_amount = item.opening_amount || 0;
              const returns = item.returns || 0;
              const closing_amount = opening_amount + sale_via_mode_of_payment - returns;
              const expected_amount = opening_amount + sale_via_mode_of_payment - returns;
              const difference = closing_amount - expected_amount;

              return {
                ...item,
                sales: sale_via_mode_of_payment,
                closing_amount,
                expected_amount,
                difference,
              };
            });

            this.dialog_data = {
              ...data,
              payment_reconciliation: updatedPaymentReconciliation,
            };
          }
        },
        error: (err) => {
          console.error("API Call Failed:", err);
        }
      });
    });
  }
};
</script>

<style scoped>
.hover-effect {
  background-color: #e3f2fd !important; 
  transition: background-color 0.3s ease, box-shadow 0.3s ease;
  box-shadow: 0px 4px 10px rgba(0, 0, 0, 0.2);
}
.transition-all {
  transition: all 0.3s ease-in-out;
}
.text-error {
  color: red !important;
  font-weight: bold;
}
.text-success {
  color: green !important;
  font-weight: bold;
}
</style>

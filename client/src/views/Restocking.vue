<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <!-- The slider stays mounted during loads so a drag is never interrupted -->
    <div class="card budget-card">
      <div class="budget-header">
        <span class="budget-label">{{ t('restocking.budget') }}</span>
        <span class="budget-value">{{ formatMoney(budget) }}</span>
      </div>
      <input
        v-model.number="budget"
        type="range"
        class="budget-slider"
        :min="MIN_BUDGET"
        :max="MAX_BUDGET"
        :step="BUDGET_STEP"
        :aria-label="t('restocking.budget')"
        :aria-valuetext="formatMoney(budget)"
      />
      <div class="budget-scale">
        <span>{{ formatMoney(MIN_BUDGET) }}</span>
        <span>{{ formatMoney(MAX_BUDGET) }}</span>
      </div>
    </div>

    <div class="stats-grid">
      <div class="stat-card info">
        <div class="stat-label">{{ t('restocking.budget') }}</div>
        <div class="stat-value">{{ formatMoney(budget) }}</div>
      </div>
      <div class="stat-card warning">
        <div class="stat-label">{{ t('restocking.plannedSpend') }}</div>
        <div class="stat-value">{{ plannedSpend }}</div>
      </div>
      <div class="stat-card success">
        <div class="stat-label">{{ t('restocking.remaining') }}</div>
        <div class="stat-value">{{ remaining }}</div>
      </div>
    </div>

    <div v-if="lastOrder" class="confirmation" role="status">
      <span>{{ t('restocking.success', {
        orderNumber: lastOrder.order_number,
        total: formatPrecise(lastOrder.total_value),
        days: lastOrder.lead_time_days
      }) }}</span>
      <router-link to="/orders" class="confirmation-link">{{ t('restocking.viewOrders') }}</router-link>
    </div>

    <div class="card">
      <div class="card-header restocking-card-header">
        <h3 class="card-title">{{ t('restocking.recommendations') }} ({{ items.length }})</h3>
        <button
          type="button"
          class="po-button create"
          :disabled="!canPlaceOrder"
          @click="placeOrder"
        >
          {{ submitting ? t('restocking.submitting') : t('restocking.placeOrder') }}
        </button>
      </div>

      <div v-if="orderError" class="error">
        {{ t('restocking.orderError', { message: orderError }) }}
      </div>

      <div v-if="loadError" class="error">
        {{ t('restocking.loadError', { message: loadError }) }}
      </div>
      <div v-else-if="loading && items.length === 0" class="loading">{{ t('common.loading') }}</div>
      <div v-else-if="items.length === 0" class="restocking-empty">{{ t('restocking.empty') }}</div>
      <div v-else class="table-container" :class="{ refreshing: loading }">
        <table>
          <thead>
            <tr>
              <th>{{ t('restocking.table.sku') }}</th>
              <th>{{ t('restocking.table.item') }}</th>
              <th>{{ t('restocking.table.category') }}</th>
              <th>{{ t('restocking.table.trend') }}</th>
              <th>{{ t('restocking.table.shortfall') }}</th>
              <th>{{ t('restocking.table.unitCost') }}</th>
              <th>{{ t('restocking.table.lineCost') }}</th>
              <th>{{ t('restocking.table.leadTime') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in items" :key="item.sku">
              <td><strong>{{ item.sku }}</strong></td>
              <td>{{ item.name }}</td>
              <td>{{ item.category || '-' }}</td>
              <td>
                <span :class="['badge', item.trend]">{{ t(`trends.${item.trend}`) }}</span>
              </td>
              <td>{{ item.recommended_qty.toLocaleString() }}</td>
              <td>{{ formatPrecise(item.unit_cost) }}</td>
              <td><strong>{{ formatPrecise(item.line_cost) }}</strong></td>
              <td>{{ t('orders.leadTimeDays', { count: item.lead_time_days }) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency, formatCurrencyWithDecimals } from '../utils/currency'

// Slider bounds are in USD; the server works in USD too
const MIN_BUDGET = 0
const MAX_BUDGET = 500000
const BUDGET_STEP = 5000
const DEFAULT_BUDGET = 100000
// Wait for the slider to stop moving before calling the API
const DEBOUNCE_MS = 250

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency } = useI18n()

    const budget = ref(DEFAULT_BUDGET)
    const items = ref([])
    // null until the first successful load, so the stats show a dash instead of a misleading $0
    const summary = ref(null)
    const loading = ref(true)
    const loadError = ref(null)
    const orderError = ref(null)
    const submitting = ref(false)
    const lastOrder = ref(null)
    // The budget the displayed list was built for. It lags behind `budget` (the live slider
    // value) until the debounced request returns, and orders must be validated against it.
    const listBudget = ref(DEFAULT_BUDGET)
    // True from a slider move until the debounced request fires
    const debouncePending = ref(false)

    // Every request gets an id. Only the newest response is applied. Without this, a slow
    // response for an earlier slider position could overwrite the list for the current one.
    let requestId = 0

    const loadRecommendations = async () => {
      const id = ++requestId
      debouncePending.value = false
      loading.value = true
      loadError.value = null
      // Capture now: the slider may move again while this request is in flight
      const requestedBudget = budget.value
      try {
        const data = await api.getRestockRecommendations(requestedBudget)
        if (id !== requestId) return
        items.value = data.items
        listBudget.value = requestedBudget
        summary.value = { total_cost: data.total_cost, remaining_budget: data.remaining_budget }
      } catch (err) {
        if (id !== requestId) return
        items.value = []
        summary.value = null
        loadError.value = err.message
      } finally {
        if (id === requestId) loading.value = false
      }
    }

    // Dragging the slider fires many input events. Restart the timer on each change so
    // only the final value triggers a request.
    let debounceTimer = null
    watch(budget, () => {
      debouncePending.value = true
      clearTimeout(debounceTimer)
      debounceTimer = setTimeout(loadRecommendations, DEBOUNCE_MS)
    })
    onUnmounted(() => clearTimeout(debounceTimer))

    const formatMoney = (amount) => formatCurrency(amount, currentCurrency.value)
    // Two decimals for line items, since unit costs and line totals carry cents
    const formatPrecise = (amount) => formatCurrencyWithDecimals(amount, currentCurrency.value, 2)

    // Show cents here: rounding both to whole dollars can make spend + remaining differ from the budget by $1
    const plannedSpend = computed(() => (summary.value ? formatPrecise(summary.value.total_cost) : '-'))
    const remaining = computed(() => (summary.value ? formatPrecise(summary.value.remaining_budget) : '-'))

    // Disabled while a recommendation request is pending or in flight: until it lands, the
    // visible list does not match the slider, and the server rejects orders whose lines or
    // total do not match the budget they were built for.
    const canPlaceOrder = computed(() =>
      items.value.length > 0 && !loading.value && !debouncePending.value &&
      !loadError.value && !submitting.value
    )

    const placeOrder = async () => {
      if (!canPlaceOrder.value) return
      submitting.value = true
      orderError.value = null
      lastOrder.value = null
      try {
        // Send only SKU and quantity. The server re-prices every line itself.
        const order = await api.placeRestockOrder({
          // The list's budget, not the live slider value, so the order matches what the user sees
          budget: listBudget.value,
          items: items.value.map(item => ({ sku: item.sku, quantity: item.recommended_qty }))
        })
        lastOrder.value = order
        // Reload so the list reflects the budget after this order
        await loadRecommendations()
      } catch (err) {
        // FastAPI returns 400 errors as { detail: string }; fall back to the network message otherwise
        const detail = err.response?.data?.detail
        orderError.value = typeof detail === 'string' ? detail : err.message
      } finally {
        submitting.value = false
      }
    }

    onMounted(loadRecommendations)

    return {
      t,
      MIN_BUDGET,
      MAX_BUDGET,
      BUDGET_STEP,
      budget,
      items,
      loading,
      loadError,
      orderError,
      submitting,
      lastOrder,
      plannedSpend,
      remaining,
      canPlaceOrder,
      placeOrder,
      formatMoney,
      formatPrecise
    }
  }
}
</script>

<style scoped>
.budget-card {
  margin-bottom: 1.25rem;
}

.budget-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 0.75rem;
}

.budget-label {
  color: #64748b;
  font-size: 0.875rem;
  font-weight: 500;
}

.budget-value {
  color: #0f172a;
  font-size: 1.5rem;
  font-weight: 700;
}

.budget-slider {
  width: 100%;
  margin: 0.25rem 0;
  accent-color: #3b82f6;
  cursor: pointer;
}

.budget-slider:focus-visible {
  outline: 2px solid #3b82f6;
  outline-offset: 4px;
}

.budget-scale {
  display: flex;
  justify-content: space-between;
  color: #64748b;
  font-size: 0.75rem;
  margin-top: 0.25rem;
}

.restocking-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 1rem;
}

.table-container.refreshing {
  opacity: 0.55;
  transition: opacity 0.15s ease;
}

.restocking-empty {
  padding: 2rem 1rem;
  text-align: center;
  color: #64748b;
  font-size: 0.875rem;
}

.confirmation {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1rem;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  color: #166534;
  border-radius: 8px;
  padding: 0.75rem 1rem;
  margin-bottom: 1.25rem;
  font-size: 0.875rem;
}

.confirmation-link {
  color: #2563eb;
  font-weight: 600;
  text-decoration: none;
}

.confirmation-link:hover {
  text-decoration: underline;
}

/* Same look as the Dashboard "Create" button */
.po-button {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 6px;
  font-size: 0.813rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.po-button.create {
  background: #3b82f6;
  color: white;
}

.po-button.create:hover:not(:disabled) {
  background: #2563eb;
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(59, 130, 246, 0.3);
}

.po-button:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}
</style>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="isOpen && backlogItem" class="modal-overlay" @click="close">
        <div
          class="modal-container"
          role="dialog"
          aria-modal="true"
          aria-labelledby="po-modal-title"
          @click.stop
        >
          <div class="modal-header">
            <h3 id="po-modal-title" class="modal-title">
              {{ mode === 'view' ? 'Purchase Order' : 'Create Purchase Order' }}
            </h3>
            <button class="close-button" aria-label="Close" @click="close">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M15 5L5 15M5 5L15 15" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
              </svg>
            </button>
          </div>

          <div class="modal-body">
            <div class="item-summary">
              <div class="item-summary-main">
                <h4 class="item-name">{{ translateProductName(backlogItem.item_name) }}</h4>
                <div class="item-sku">SKU: {{ backlogItem.item_sku }}</div>
              </div>
              <div class="item-summary-meta">
                <div class="info-item">
                  <div class="info-label">Order ID</div>
                  <div class="info-value mono">{{ backlogItem.order_id }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">Shortage</div>
                  <div class="info-value shortage">{{ shortage }} units</div>
                </div>
              </div>
            </div>

            <!-- View mode -->
            <template v-if="mode === 'view'">
              <div v-if="loadingPO" class="state-message">Loading purchase order...</div>
              <div v-else-if="loadError" class="error-message" role="alert">{{ loadError }}</div>
              <div v-else-if="existingPO" class="info-grid">
                <div class="info-item">
                  <div class="info-label">PO Number</div>
                  <div class="info-value mono">{{ existingPO.id }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">Status</div>
                  <div class="info-value">
                    <span class="badge" :class="statusClass(existingPO.status)">{{ existingPO.status }}</span>
                  </div>
                </div>
                <div class="info-item">
                  <div class="info-label">Supplier</div>
                  <div class="info-value">{{ existingPO.supplier_name }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">Quantity</div>
                  <div class="info-value">{{ existingPO.quantity.toLocaleString('en-US') }} units</div>
                </div>
                <div class="info-item">
                  <div class="info-label">Unit Cost</div>
                  <div class="info-value">{{ formatCurrencyWithDecimals(existingPO.unit_cost, 'USD', 2) }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">Total</div>
                  <div class="info-value strong">{{ formatCurrency(existingPO.quantity * existingPO.unit_cost) }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">Expected Delivery</div>
                  <div class="info-value">{{ formatDate(existingPO.expected_delivery_date) }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">Created</div>
                  <div class="info-value">{{ formatDate(existingPO.created_date) }}</div>
                </div>
                <div class="info-item full-row">
                  <div class="info-label">Notes</div>
                  <div class="info-value notes-text">{{ existingPO.notes || 'None' }}</div>
                </div>
              </div>
            </template>

            <!-- Create mode -->
            <form v-else id="po-form" class="po-form" novalidate @submit.prevent="submit">
              <div class="form-group">
                <label for="po-supplier">Supplier name</label>
                <input
                  id="po-supplier"
                  v-model="form.supplier"
                  type="text"
                  maxlength="100"
                  class="po-input"
                  :class="{ invalid: showError('supplier') }"
                  placeholder="e.g. Acme Components"
                  autocomplete="off"
                  @blur="touched.supplier = true"
                />
                <div v-if="showError('supplier')" class="field-error">{{ errors.supplier }}</div>
              </div>

              <div class="form-row">
                <div class="form-group">
                  <label for="po-quantity">Quantity</label>
                  <input
                    id="po-quantity"
                    v-model.number="form.quantity"
                    type="number"
                    min="1"
                    max="1000000"
                    step="1"
                    class="po-input"
                    :class="{ invalid: showError('quantity') }"
                    @blur="touched.quantity = true"
                  />
                  <div v-if="showError('quantity')" class="field-error">{{ errors.quantity }}</div>
                </div>

                <div class="form-group">
                  <label for="po-unit-cost">Unit cost (USD)</label>
                  <input
                    id="po-unit-cost"
                    v-model.number="form.unitCost"
                    type="number"
                    min="0"
                    step="0.01"
                    class="po-input"
                    :class="{ invalid: showError('unitCost') }"
                    placeholder="0.00"
                    @blur="touched.unitCost = true"
                  />
                  <div v-if="showError('unitCost')" class="field-error">{{ errors.unitCost }}</div>
                </div>
              </div>

              <div class="form-group">
                <label for="po-delivery">Expected delivery date</label>
                <input
                  id="po-delivery"
                  v-model="form.deliveryDate"
                  type="date"
                  :min="today"
                  class="po-input"
                  :class="{ invalid: showError('deliveryDate') }"
                  @blur="touched.deliveryDate = true"
                />
                <div v-if="showError('deliveryDate')" class="field-error">{{ errors.deliveryDate }}</div>
              </div>

              <div class="form-group">
                <label for="po-notes">Notes (optional)</label>
                <textarea
                  id="po-notes"
                  v-model="form.notes"
                  rows="3"
                  maxlength="500"
                  class="po-input po-textarea"
                  :class="{ invalid: showError('notes') }"
                  @blur="touched.notes = true"
                ></textarea>
                <div class="char-count">{{ form.notes.length }} / 500</div>
                <div v-if="showError('notes')" class="field-error">{{ errors.notes }}</div>
              </div>

              <div class="total-row">
                <span class="total-label">Order total</span>
                <span class="total-value">{{ formatCurrency(orderTotal) }}</span>
              </div>

              <div v-if="submitError" class="error-message" role="alert">{{ submitError }}</div>
            </form>
          </div>

          <div class="modal-footer">
            <button type="button" class="btn-secondary" @click="close">
              {{ mode === 'view' ? 'Close' : 'Cancel' }}
            </button>
            <button
              v-if="mode !== 'view'"
              type="submit"
              form="po-form"
              class="btn-primary"
              :disabled="!isValid || submitting"
            >
              {{ submitting ? 'Creating...' : 'Create Purchase Order' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency, formatCurrencyWithDecimals } from '../utils/currency'

const { translateProductName } = useI18n()

const props = defineProps({
  isOpen: {
    type: Boolean,
    required: true
  },
  backlogItem: {
    type: Object,
    default: null
  },
  mode: {
    type: String,
    default: 'create',
    validator: (value) => ['create', 'view'].includes(value)
  }
})

const emit = defineEmits(['close', 'po-created'])

// Limits mirror CreatePurchaseOrderRequest on the server
const MAX_QUANTITY = 1_000_000
const MAX_SUPPLIER_LENGTH = 100
const MAX_NOTES_LENGTH = 500

// Local calendar date as YYYY-MM-DD. toISOString() would give the UTC date,
// which is "tomorrow" or "yesterday" for part of every day in most time zones.
const getToday = () => {
  const now = new Date()
  const mm = String(now.getMonth() + 1).padStart(2, '0')
  const dd = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${mm}-${dd}`
}

const today = ref(getToday())

const emptyForm = () => ({
  supplier: '',
  quantity: '',
  unitCost: '',
  deliveryDate: '',
  notes: ''
})

const form = reactive(emptyForm())
const touched = reactive({})
const submitting = ref(false)
const submitError = ref('')
const existingPO = ref(null)
const loadingPO = ref(false)
const loadError = ref('')

// Incremented on every open/close/item switch. Async results compare against the
// value captured when they started and are dropped if it has moved on.
let session = 0

const shortage = computed(() => {
  if (!props.backlogItem) return 0
  return props.backlogItem.quantity_needed - props.backlogItem.quantity_available
})

const errors = computed(() => {
  const result = {}
  const supplier = form.supplier.trim()
  if (!supplier) {
    result.supplier = 'Supplier name is required.'
  } else if (supplier.length > MAX_SUPPLIER_LENGTH) {
    result.supplier = `Supplier name must be ${MAX_SUPPLIER_LENGTH} characters or fewer.`
  }

  // v-model.number leaves '' (not a number) when the input is empty or unparseable
  if (typeof form.quantity !== 'number' || !Number.isInteger(form.quantity)) {
    result.quantity = 'Enter a whole number of units.'
  } else if (form.quantity < 1 || form.quantity > MAX_QUANTITY) {
    result.quantity = `Quantity must be between 1 and ${MAX_QUANTITY.toLocaleString('en-US')}.`
  }

  if (typeof form.unitCost !== 'number' || !Number.isFinite(form.unitCost)) {
    result.unitCost = 'Enter a unit cost.'
  } else if (form.unitCost < 0) {
    result.unitCost = 'Unit cost cannot be negative.'
  }

  // The date input yields '' for an incomplete date; the regex also rejects
  // years beyond 4 digits, which the server's date parsing would refuse.
  if (!/^\d{4}-\d{2}-\d{2}$/.test(form.deliveryDate)) {
    result.deliveryDate = 'Choose an expected delivery date.'
  } else if (form.deliveryDate < today.value) {
    // Same-format ISO strings compare correctly as plain strings
    result.deliveryDate = 'Delivery date cannot be in the past.'
  }

  if (form.notes.trim().length > MAX_NOTES_LENGTH) {
    result.notes = `Notes must be ${MAX_NOTES_LENGTH} characters or fewer.`
  }
  return result
})

const isValid = computed(() => Object.keys(errors.value).length === 0)

const showError = (field) => touched[field] && errors.value[field]

const orderTotal = computed(() => {
  if (errors.value.quantity || errors.value.unitCost) return 0
  return form.quantity * form.unitCost
})

const resetState = () => {
  Object.assign(form, emptyForm())
  Object.keys(touched).forEach((key) => delete touched[key])
  submitting.value = false
  submitError.value = ''
  existingPO.value = null
  loadingPO.value = false
  loadError.value = ''
}

// Turn an axios error into a single readable string. FastAPI returns `detail` as a
// string for HTTPException (400/404/409) but as an array of {msg, loc} for 422.
const describeError = (err, fallback) => {
  const response = err && err.response
  if (!response) return 'Could not reach the server. Check your connection and try again.'

  const detail = response.data && response.data.detail
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((entry) => {
        // loc looks like ['body', 'quantity']; drop the leading 'body'
        const field = Array.isArray(entry.loc) ? entry.loc.filter((part) => part !== 'body').join('.') : ''
        return field ? `${field}: ${entry.msg}` : entry.msg
      })
      .join('; ')
  }
  return fallback
}

const loadPO = async (item, currentSession) => {
  loadingPO.value = true
  loadError.value = ''
  try {
    // The endpoint is keyed by backlog item id, not by PO id
    const po = await api.getPurchaseOrderByBacklogItem(item.id)
    if (currentSession !== session) return
    existingPO.value = po
  } catch (err) {
    if (currentSession !== session) return
    console.error('Failed to load purchase order:', err)
    loadError.value = describeError(err, 'Failed to load the purchase order.')
  } finally {
    if (currentSession === session) loadingPO.value = false
  }
}

// Reset whenever the modal opens or is pointed at another item. Dashboard keeps this
// component mounted, so without this the previous item's form values and PO would
// still be there on the next open.
watch(
  [() => props.isOpen, () => props.backlogItem?.id, () => props.mode],
  () => {
    session += 1
    resetState()
    if (!props.isOpen || !props.backlogItem) return

    today.value = getToday()
    if (props.mode === 'view') {
      loadPO(props.backlogItem, session)
    } else {
      form.quantity = shortage.value > 0 ? shortage.value : 1
    }
  },
  { immediate: true }
)

const submit = async () => {
  // Enter key in a text field submits the form even though the button is disabled
  if (!isValid.value || submitting.value || !props.backlogItem) return

  const currentSession = session
  const notes = form.notes.trim()
  const payload = {
    backlog_item_id: props.backlogItem.id,
    supplier_name: form.supplier.trim(),
    quantity: form.quantity,
    unit_cost: form.unitCost,
    expected_delivery_date: form.deliveryDate
  }
  if (notes) payload.notes = notes

  submitting.value = true
  submitError.value = ''
  try {
    const po = await api.createPurchaseOrder(payload)
    // Emitted even if the modal was closed meanwhile: the PO exists server-side, and
    // the parent needs it to flip the row to "View PO" (it finds the row by id).
    emit('po-created', po)
  } catch (err) {
    if (currentSession !== session) return
    console.error('Failed to create purchase order:', err)
    submitError.value = err.response?.status === 409
      ? 'A purchase order already exists for this item.'
      : describeError(err, 'Failed to create the purchase order.')
  } finally {
    if (currentSession === session) submitting.value = false
  }
}

const close = () => {
  emit('close')
}

const onKeydown = (event) => {
  if (event.key === 'Escape' && props.isOpen) close()
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))

const STATUS_CLASSES = {
  ordered: 'info',
  shipped: 'warning',
  delivered: 'success',
  received: 'success',
  cancelled: 'danger'
}

const statusClass = (status) => STATUS_CLASSES[String(status).toLowerCase()] || 'neutral'

const formatDate = (dateString) => {
  if (!dateString) return 'N/A'
  // Build from parts: new Date('YYYY-MM-DD') is parsed as UTC midnight and would
  // display as the previous day in time zones behind UTC.
  const [year, month, day] = String(dateString).split('-').map(Number)
  const date = new Date(year, month - 1, day)
  if (isNaN(date.getTime())) return dateString
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  })
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  padding: 1rem;
}

.modal-container {
  background: white;
  border-radius: 12px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.15);
  max-width: 640px;
  width: 100%;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.5rem;
  border-bottom: 1px solid #e2e8f0;
}

.modal-title {
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.025em;
}

.close-button {
  background: none;
  border: none;
  color: #64748b;
  cursor: pointer;
  padding: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  transition: all 0.15s ease;
}

.close-button:hover {
  background: #f1f5f9;
  color: #0f172a;
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem 2rem;
}

.item-summary {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1.5rem;
  padding-bottom: 1.25rem;
  border-bottom: 1px solid #e2e8f0;
  margin-bottom: 1.5rem;
}

.item-summary-main {
  min-width: 0;
}

.item-name {
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
  margin: 0 0 0.375rem 0;
}

.item-sku {
  font-size: 0.875rem;
  color: #64748b;
  font-family: 'Monaco', 'Courier New', monospace;
}

.item-summary-meta {
  display: flex;
  gap: 1.5rem;
  flex-shrink: 0;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1.25rem 1.5rem;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.info-item.full-row {
  grid-column: 1 / -1;
}

.info-label {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
}

.info-value {
  font-size: 0.938rem;
  color: #0f172a;
  font-weight: 500;
}

.info-value.mono {
  font-family: 'Monaco', 'Courier New', monospace;
  color: #2563eb;
}

.info-value.shortage {
  color: #dc2626;
  font-weight: 700;
}

.info-value.strong {
  font-weight: 700;
}

.notes-text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.badge {
  display: inline-block;
  padding: 0.25rem 0.625rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.025em;
}

.badge.info {
  background: #dbeafe;
  color: #1e40af;
}

.badge.warning {
  background: #fef3c7;
  color: #92400e;
}

.badge.success {
  background: #d1fae5;
  color: #065f46;
}

.badge.danger {
  background: #fecaca;
  color: #991b1b;
}

.badge.neutral {
  background: #f1f5f9;
  color: #475569;
}

.state-message {
  text-align: center;
  padding: 2rem 0;
  color: #64748b;
}

.error-message {
  padding: 0.75rem 1rem;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  color: #991b1b;
  font-size: 0.875rem;
}

/* Form */
.po-form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.form-row {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #475569;
}

.po-input {
  padding: 0.625rem 0.75rem;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  font-size: 0.938rem;
  color: #0f172a;
  background: white;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
  font-family: inherit;
  width: 100%;
  box-sizing: border-box;
}

.po-input:focus {
  outline: none;
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15);
}

.po-input.invalid {
  border-color: #dc2626;
}

.po-textarea {
  resize: vertical;
}

.char-count {
  align-self: flex-end;
  font-size: 0.75rem;
  color: #94a3b8;
}

.field-error {
  font-size: 0.813rem;
  color: #dc2626;
}

.total-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.875rem 1rem;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}

.total-label {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
}

.total-value {
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
}

.modal-footer {
  padding: 1.25rem 1.5rem;
  border-top: 1px solid #e2e8f0;
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}

.btn-secondary {
  padding: 0.625rem 1.25rem;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-weight: 500;
  font-size: 0.875rem;
  color: #334155;
  cursor: pointer;
  transition: all 0.15s ease;
  font-family: inherit;
}

.btn-secondary:hover {
  background: #e2e8f0;
  border-color: #cbd5e1;
}

.btn-primary {
  padding: 0.625rem 1.25rem;
  background: #2563eb;
  border: 1px solid #2563eb;
  border-radius: 8px;
  font-weight: 600;
  font-size: 0.875rem;
  color: white;
  cursor: pointer;
  transition: all 0.15s ease;
  font-family: inherit;
}

.btn-primary:hover:not(:disabled) {
  background: #1d4ed8;
  border-color: #1d4ed8;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

@media (max-width: 560px) {
  .item-summary {
    flex-direction: column;
  }

  .form-row,
  .info-grid {
    grid-template-columns: 1fr;
  }
}

/* Modal transition animations */
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-active .modal-container,
.modal-leave-active .modal-container {
  transition: transform 0.2s ease;
}

.modal-enter-from .modal-container,
.modal-leave-to .modal-container {
  transform: scale(0.95);
}
</style>

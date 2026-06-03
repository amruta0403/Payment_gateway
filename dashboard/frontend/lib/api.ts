import axios from 'axios'
import { getSession } from 'next-auth/react'

const BFF = process.env.NEXT_PUBLIC_BFF_URL || 'http://localhost:8099'

export const api = axios.create({ baseURL: BFF })

// Attach Keycloak access token to every request
api.interceptors.request.use(async (config) => {
  const session = await getSession() as any
  if (session?.accessToken) {
    config.headers.Authorization = `Bearer ${session.accessToken}`
  }
  return config
})

// ── Dashboard ─────────────────────────────────────────────────────────────────
export const getDashboardStats = () => api.get('/api/dashboard/stats').then(r => r.data)
export const getVolumeChart    = (days = 30) => api.get(`/api/dashboard/volume?days=${days}`).then(r => r.data)

// ── Transactions ──────────────────────────────────────────────────────────────
export const getTransactions = (params = {}) => api.get('/api/transactions', { params }).then(r => r.data)
export const getTransaction  = (id: string)  => api.get(`/api/transactions/${id}`).then(r => r.data)

// ── Payments ──────────────────────────────────────────────────────────────────
export const getPayments   = (params = {})  => api.get('/api/payments', { params }).then(r => r.data)
export const getPayment    = (id: string)   => api.get(`/api/payments/${id}`).then(r => r.data)
export const createPayment = (body: object) => api.post('/api/payments', body).then(r => r.data)
export const getPaymentEvents = (id: string) => api.get(`/api/payments/${id}/events`).then(r => r.data)

// ── Refunds ───────────────────────────────────────────────────────────────────
export const getRefunds      = (params = {})  => api.get('/api/refunds', { params }).then(r => r.data)
export const createRefund    = (body: object) => api.post('/api/refunds', body).then(r => r.data)
export const getPaymentRefunds = (paymentId: string) => api.get(`/api/payments/${paymentId}/refunds`).then(r => r.data)

// ── Settlements ───────────────────────────────────────────────────────────────
export const getSettlements = (params = {})  => api.get('/api/settlements', { params }).then(r => r.data)
export const getSettlement  = (id: string)   => api.get(`/api/settlements/${id}`).then(r => r.data)

// ── Merchant ──────────────────────────────────────────────────────────────────
export const getMyMerchant  = ()  => api.get('/api/merchants/me').then(r => r.data)
export const getChecklist   = (merchantId: string) => api.get(`/api/merchants/${merchantId}/checklist`).then(r => r.data)
export const getBankAccounts = (merchantId: string) => api.get(`/api/merchants/${merchantId}/bank-accounts`).then(r => r.data)
export const addBankAccount = (merchantId: string, body: object) => api.post(`/api/merchants/${merchantId}/bank-accounts`, body).then(r => r.data)

// ── API Keys ──────────────────────────────────────────────────────────────────
export const getApiKeys    = (merchantId: string) => api.get(`/api/merchants/${merchantId}/api-keys`).then(r => r.data)
export const createApiKey  = (merchantId: string, body: object) => api.post(`/api/merchants/${merchantId}/api-keys`, body).then(r => r.data)
export const revokeApiKey  = (merchantId: string, keyId: string) => api.delete(`/api/merchants/${merchantId}/api-keys/${keyId}`).then(r => r.data)

// ── Webhooks ──────────────────────────────────────────────────────────────────
export const getWebhooks   = (merchantId: string) => api.get(`/api/merchants/${merchantId}/webhooks`).then(r => r.data)
export const createWebhook = (merchantId: string, body: object) => api.post(`/api/merchants/${merchantId}/webhooks`, body).then(r => r.data)
export const deleteWebhook = (merchantId: string, whId: string) => api.delete(`/api/merchants/${merchantId}/webhooks/${whId}`).then(r => r.data)
export const testWebhook   = (merchantId: string, whId: string) => api.post(`/api/merchants/${merchantId}/webhooks/${whId}/test`).then(r => r.data)

// ── Reports ───────────────────────────────────────────────────────────────────
export const getDailyReport = (startDate: string, endDate: string) =>
  api.get('/api/reports/daily', { params: { start_date: startDate, end_date: endDate } }).then(r => r.data)

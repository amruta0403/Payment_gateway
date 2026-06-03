'use client'
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getPayments, createPayment, getMyMerchant } from '@/lib/api'
import { formatCurrency, formatDate } from '@/lib/utils'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { PageHeader } from '@/components/ui/PageHeader'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { EmptyState } from '@/components/ui/EmptyState'
import { CreditCard, Plus, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { v4 as uuidv4 } from 'uuid'

export default function PaymentsPage() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [page, setPage] = useState(1)
  const [form, setForm] = useState({
    amount: '500', method: 'CARD',
    card_number: '4111111111111111', expiry_month: '12', expiry_year: '2026', cvv: '123',
    cardholder_name: 'Test User',
    customer_email: 'test@example.com', customer_phone: '+919876543210',
  })

  const { data: merchant } = useQuery({ queryKey: ['merchant-me'], queryFn: getMyMerchant })
  const { data, isLoading } = useQuery({
    queryKey: ['payments', page],
    queryFn: () => getPayments({ page, page_size: 20 }),
  })

  const mutation = useMutation({
    mutationFn: createPayment,
    onSuccess: () => {
      toast.success('Payment initiated!')
      qc.invalidateQueries({ queryKey: ['payments'] })
      setShowForm(false)
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail || 'Payment failed'),
  })

  const handleSubmit = () => {
    if (!merchant?.id) { toast.error('Merchant not loaded'); return }
    mutation.mutate({
      merchant_id: merchant.id,
      amount: parseInt(form.amount) * 100,
      currency: 'INR',
      payment_method: form.method,
      ...(form.method === 'CARD' ? {
        card: {
          number: form.card_number, expiry_month: parseInt(form.expiry_month),
          expiry_year: parseInt(form.expiry_year), cvv: form.cvv, cardholder_name: form.cardholder_name,
        }
      } : {}),
      customer: { email: form.customer_email, phone: form.customer_phone },
      order_id: `order-${Date.now()}`,
    } as any)
  }

  const items = data?.items || []

  return (
    <div>
      <PageHeader
        title="Payments"
        description="Create and manage payment transactions"
        action={
          <button onClick={() => setShowForm(true)}
            className="flex items-center gap-2 bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-4 py-2.5 rounded-xl transition-colors">
            <Plus className="w-4 h-4" /> New Payment
          </button>
        }
      />

      {/* Create payment modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="font-bold text-gray-900">Create Test Payment</h2>
              <button onClick={() => setShowForm(false)} className="p-1 hover:bg-gray-100 rounded-lg">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Amount (₹)</label>
                  <input value={form.amount} onChange={e => setForm({...form, amount: e.target.value})}
                    className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Method</label>
                  <select value={form.method} onChange={e => setForm({...form, method: e.target.value})}
                    className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-brand-500">
                    {['CARD','UPI','NETBANKING'].map(m => <option key={m}>{m}</option>)}
                  </select>
                </div>
              </div>

              {form.method === 'CARD' && (
                <>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Card Number</label>
                    <input value={form.card_number} onChange={e => setForm({...form, card_number: e.target.value})}
                      className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-brand-500" />
                  </div>
                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-700 mb-1">Expiry Mo</label>
                      <input value={form.expiry_month} onChange={e => setForm({...form, expiry_month: e.target.value})}
                        className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-700 mb-1">Expiry Yr</label>
                      <input value={form.expiry_year} onChange={e => setForm({...form, expiry_year: e.target.value})}
                        className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-700 mb-1">CVV</label>
                      <input value={form.cvv} onChange={e => setForm({...form, cvv: e.target.value})}
                        className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
                    </div>
                  </div>
                </>
              )}

              <div className="p-3 bg-blue-50 rounded-xl text-xs text-blue-700">
                💡 Use <code className="font-mono">4111111111111111</code> for success, <code className="font-mono">4000000000000002</code> for decline
              </div>

              <button onClick={handleSubmit} disabled={mutation.isPending}
                className="w-full bg-brand-600 hover:bg-brand-700 disabled:bg-brand-400 text-white font-medium py-2.5 rounded-xl transition-colors text-sm">
                {mutation.isPending ? 'Processing…' : `Pay ${form.amount ? `₹${form.amount}` : ''}`}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        {isLoading ? <LoadingSpinner /> : items.length === 0 ? (
          <EmptyState icon={CreditCard} title="No payments yet" description="Create your first test payment using the button above." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100 text-left">
                  {['ID', 'Amount', 'Method', 'Status', 'Fraud Score', 'Order ID', 'Created'].map(h => (
                    <th key={h} className="px-4 py-3 text-xs font-medium text-gray-500">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {items.map((p: any) => (
                  <tr key={p.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3 font-mono text-xs text-gray-400">{p.id?.slice(0,8)}…</td>
                    <td className="px-4 py-3 font-semibold">{formatCurrency(p.amount)}</td>
                    <td className="px-4 py-3"><span className="px-2 py-0.5 bg-gray-100 rounded text-xs">{p.payment_method}</span></td>
                    <td className="px-4 py-3"><StatusBadge status={p.status} /></td>
                    <td className="px-4 py-3">
                      {p.fraud_score !== null && p.fraud_score !== undefined ? (
                        <span className={`text-xs font-medium ${p.fraud_score < 0.3 ? 'text-green-600' : p.fraud_score < 0.7 ? 'text-yellow-600' : 'text-red-600'}`}>
                          {(p.fraud_score * 100).toFixed(0)}%
                        </span>
                      ) : '—'}
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{p.order_id || '—'}</td>
                    <td className="px-4 py-3 text-gray-400 text-xs">{formatDate(p.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

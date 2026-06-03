'use client'
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getRefunds, createRefund } from '@/lib/api'
import { formatCurrency, formatDate } from '@/lib/utils'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { PageHeader } from '@/components/ui/PageHeader'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { EmptyState } from '@/components/ui/EmptyState'
import { RefreshCw, Plus, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { v4 as uuidv4 } from 'uuid'

export default function RefundsPage() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ transaction_id: '', amount: '', reason: '' })

  const { data, isLoading } = useQuery({
    queryKey: ['refunds'],
    queryFn: () => getRefunds({ page: 1, page_size: 50 }),
  })

  const mutation = useMutation({
    mutationFn: createRefund,
    onSuccess: () => {
      toast.success('Refund initiated!')
      qc.invalidateQueries({ queryKey: ['refunds'] })
      setShowForm(false)
      setForm({ transaction_id: '', amount: '', reason: '' })
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail || 'Refund failed'),
  })

  const handleSubmit = () => {
    if (!form.transaction_id || !form.amount) { toast.error('Fill all required fields'); return }
    mutation.mutate({
      transaction_id: form.transaction_id,
      amount: parseInt(form.amount) * 100,
      reason: form.reason || 'Customer request',
      idempotency_key: uuidv4(),
    })
  }

  const items = data?.items || []

  return (
    <div>
      <PageHeader
        title="Refunds"
        description="Initiate and track refunds"
        action={
          <button onClick={() => setShowForm(true)}
            className="flex items-center gap-2 bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-4 py-2.5 rounded-xl transition-colors">
            <Plus className="w-4 h-4" /> New Refund
          </button>
        }
      />

      {showForm && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="font-bold text-gray-900">Initiate Refund</h2>
              <button onClick={() => setShowForm(false)} className="p-1 hover:bg-gray-100 rounded-lg">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Transaction ID *</label>
                <input value={form.transaction_id} onChange={e => setForm({...form, transaction_id: e.target.value})}
                  placeholder="Paste transaction UUID"
                  className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-brand-500" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Amount (₹) *</label>
                <input value={form.amount} onChange={e => setForm({...form, amount: e.target.value})}
                  type="number" min="1"
                  className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Reason</label>
                <input value={form.reason} onChange={e => setForm({...form, reason: e.target.value})}
                  placeholder="Customer requested refund"
                  className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
              </div>
              <button onClick={handleSubmit} disabled={mutation.isPending}
                className="w-full bg-brand-600 hover:bg-brand-700 disabled:bg-brand-400 text-white font-medium py-2.5 rounded-xl transition-colors text-sm">
                {mutation.isPending ? 'Processing…' : 'Initiate Refund'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        {isLoading ? <LoadingSpinner /> : items.length === 0 ? (
          <EmptyState icon={RefreshCw} title="No refunds" description="Refunds you initiate will appear here." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100 text-left">
                  {['Refund ID', 'Transaction', 'Amount', 'Type', 'Status', 'UTR', 'Created'].map(h => (
                    <th key={h} className="px-4 py-3 text-xs font-medium text-gray-500">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {items.map((r: any) => (
                  <tr key={r.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-mono text-xs text-gray-400">{r.id?.slice(0,8)}…</td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-400">{r.transaction_id?.slice(0,8)}…</td>
                    <td className="px-4 py-3 font-semibold">{formatCurrency(r.amount)}</td>
                    <td className="px-4 py-3"><span className="px-2 py-0.5 bg-gray-100 rounded text-xs">{r.refund_type}</span></td>
                    <td className="px-4 py-3"><StatusBadge status={r.status} /></td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-500">{r.utr_number || '—'}</td>
                    <td className="px-4 py-3 text-gray-400 text-xs">{formatDate(r.created_at)}</td>
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

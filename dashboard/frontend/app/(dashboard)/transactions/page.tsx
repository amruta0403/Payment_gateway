'use client'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getTransactions } from '@/lib/api'
import { formatCurrency, formatDate } from '@/lib/utils'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { PageHeader } from '@/components/ui/PageHeader'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { EmptyState } from '@/components/ui/EmptyState'
import { ArrowLeftRight, ChevronLeft, ChevronRight, Search } from 'lucide-react'

const METHODS  = ['', 'CARD', 'UPI', 'NETBANKING']
const STATUSES = ['', 'CAPTURED', 'SETTLED', 'FAILED', 'PENDING', 'REFUNDED', 'CANCELLED']

export default function TransactionsPage() {
  const [page, setPage]     = useState(1)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [method, setMethod] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['transactions', page, status, method],
    queryFn: () => getTransactions({ page, page_size: 20, status: status || undefined, payment_method: method || undefined }),
  })

  const items  = data?.items || []
  const total  = data?.total || 0
  const hasMore = data?.has_more

  return (
    <div>
      <PageHeader title="Transactions" description={`${total} total transactions`} />

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-5">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search order ID…"
            className="pl-9 pr-4 py-2 text-sm border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-500 bg-white"
          />
        </div>
        <select value={status} onChange={e => { setStatus(e.target.value); setPage(1) }}
          className="px-3 py-2 text-sm border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-500 bg-white">
          <option value="">All Statuses</option>
          {STATUSES.slice(1).map(s => <option key={s}>{s}</option>)}
        </select>
        <select value={method} onChange={e => { setMethod(e.target.value); setPage(1) }}
          className="px-3 py-2 text-sm border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-500 bg-white">
          <option value="">All Methods</option>
          {METHODS.slice(1).map(m => <option key={m}>{m}</option>)}
        </select>
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        {isLoading ? <LoadingSpinner /> : items.length === 0 ? (
          <EmptyState icon={ArrowLeftRight} title="No transactions found" description="Transactions will appear here once you start processing payments." />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-100 text-left">
                    {['ID', 'Amount', 'Method', 'Status', 'Card / VPA', 'Order ID', 'Created'].map(h => (
                      <th key={h} className="px-4 py-3 text-xs font-medium text-gray-500">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {items.map((txn: any) => (
                    <tr key={txn.id} className="hover:bg-gray-50 transition-colors">
                      <td className="px-4 py-3 font-mono text-xs text-gray-400">{txn.id?.slice(0, 8)}…</td>
                      <td className="px-4 py-3 font-semibold text-gray-900">{formatCurrency(txn.amount)}</td>
                      <td className="px-4 py-3">
                        <span className="px-2 py-0.5 bg-gray-100 rounded-md text-xs font-medium text-gray-700">{txn.payment_method}</span>
                      </td>
                      <td className="px-4 py-3"><StatusBadge status={txn.status} /></td>
                      <td className="px-4 py-3 text-gray-500 text-xs">
                        {txn.card_last4 ? `•••• ${txn.card_last4}` : txn.upi_vpa ? txn.upi_vpa : '—'}
                      </td>
                      <td className="px-4 py-3 text-gray-500 text-xs">{txn.order_id || '—'}</td>
                      <td className="px-4 py-3 text-gray-400 text-xs">{formatDate(txn.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100">
              <p className="text-xs text-gray-500">Page {page} · {total} total</p>
              <div className="flex gap-2">
                <button disabled={page === 1} onClick={() => setPage(p => p - 1)}
                  className="p-1.5 rounded-lg border border-gray-200 disabled:opacity-40 hover:bg-gray-50">
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button disabled={!hasMore} onClick={() => setPage(p => p + 1)}
                  className="p-1.5 rounded-lg border border-gray-200 disabled:opacity-40 hover:bg-gray-50">
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

'use client'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getSettlements } from '@/lib/api'
import { formatCurrency, formatDateShort } from '@/lib/utils'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { PageHeader } from '@/components/ui/PageHeader'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { EmptyState } from '@/components/ui/EmptyState'
import { Landmark, ChevronLeft, ChevronRight } from 'lucide-react'

export default function SettlementsPage() {
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['settlements', page, status],
    queryFn: () => getSettlements({ page, page_size: 20, status: status || undefined }),
  })

  const items  = data?.items || []
  const total  = data?.total || 0

  return (
    <div>
      <PageHeader title="Settlements" description={`${total} settlement batches`} />

      <div className="flex gap-3 mb-5">
        <select value={status} onChange={e => { setStatus(e.target.value); setPage(1) }}
          className="px-3 py-2 text-sm border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-500 bg-white">
          <option value="">All Statuses</option>
          {['PENDING','PROCESSING','COMPLETED','FAILED','RECONCILED'].map(s => <option key={s}>{s}</option>)}
        </select>
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        {isLoading ? <LoadingSpinner /> : items.length === 0 ? (
          <EmptyState icon={Landmark} title="No settlements" description="Settlement batches are created automatically at 23:00 IST every day." />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-100 text-left">
                    {['Batch ID', 'Date', 'Gross', 'Fee', 'GST', 'Net Amount', 'Txns', 'Status'].map(h => (
                      <th key={h} className="px-4 py-3 text-xs font-medium text-gray-500">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {items.map((s: any) => (
                    <tr key={s.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-mono text-xs text-gray-400">{s.id?.slice(0,8)}…</td>
                      <td className="px-4 py-3 text-gray-700">{s.settlement_date}</td>
                      <td className="px-4 py-3 text-gray-700">{formatCurrency(s.gross_amount)}</td>
                      <td className="px-4 py-3 text-red-500 text-xs">-{formatCurrency(s.fee_amount)}</td>
                      <td className="px-4 py-3 text-red-400 text-xs">-{formatCurrency(s.gst_on_fee)}</td>
                      <td className="px-4 py-3 font-bold text-green-700">{formatCurrency(s.net_amount)}</td>
                      <td className="px-4 py-3 text-gray-500">{s.transaction_count}</td>
                      <td className="px-4 py-3"><StatusBadge status={s.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100">
              <p className="text-xs text-gray-500">Page {page} · {total} total</p>
              <div className="flex gap-2">
                <button disabled={page === 1} onClick={() => setPage(p => p - 1)}
                  className="p-1.5 rounded-lg border border-gray-200 disabled:opacity-40 hover:bg-gray-50">
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button disabled={!data?.has_more} onClick={() => setPage(p => p + 1)}
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

'use client'
import { useQuery } from '@tanstack/react-query'
import { getDashboardStats, getVolumeChart } from '@/lib/api'
import { formatCurrency, formatDate } from '@/lib/utils'
import { StatsCard } from '@/components/dashboard/StatsCard'
import { VolumeChart } from '@/components/dashboard/VolumeChart'
import { PaymentMethodChart } from '@/components/dashboard/PaymentMethodChart'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { ArrowLeftRight, TrendingUp, CheckCircle, Landmark } from 'lucide-react'

export default function DashboardPage() {
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['dashboard-stats'],
    queryFn: getDashboardStats,
    refetchInterval: 30_000,
  })

  const { data: volume } = useQuery({
    queryKey: ['volume-chart'],
    queryFn: () => getVolumeChart(30),
  })

  if (statsLoading) return <LoadingSpinner />

  const today = stats?.today || {}
  const week  = stats?.week  || {}

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-gray-900">Overview</h1>
        <p className="text-sm text-gray-500">Today's payment activity</p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatsCard
          title="Transactions Today"
          value={String(today.transaction_count || 0)}
          subtitle={`${today.success_count || 0} successful`}
          icon={ArrowLeftRight}
          iconColor="text-brand-600"
          iconBg="bg-brand-50"
        />
        <StatsCard
          title="Volume Today"
          value={formatCurrency(today.volume_paise || 0)}
          icon={TrendingUp}
          iconColor="text-green-600"
          iconBg="bg-green-50"
        />
        <StatsCard
          title="Success Rate"
          value={`${today.success_rate_pct || 0}%`}
          subtitle="Today"
          icon={CheckCircle}
          iconColor="text-emerald-600"
          iconBg="bg-emerald-50"
        />
        <StatsCard
          title="Pending Settlements"
          value={String(stats?.pending_settlements || 0)}
          icon={Landmark}
          iconColor="text-amber-600"
          iconBg="bg-amber-50"
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <VolumeChart data={volume?.data || []} />
        </div>
        <div>
          <PaymentMethodChart data={today.by_method || week.by_method || {}} />
        </div>
      </div>

      {/* Recent transactions */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
          <h3 className="font-semibold text-gray-900">Recent Transactions</h3>
          <a href="/transactions" className="text-xs text-brand-600 hover:underline">View all</a>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left">
                {['Transaction ID', 'Amount', 'Method', 'Status', 'Time'].map(h => (
                  <th key={h} className="px-5 py-3 text-xs font-medium text-gray-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {(stats?.recent_transactions || []).map((txn: any) => (
                <tr key={txn.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-5 py-3 font-mono text-xs text-gray-500">{txn.id?.slice(0,20)}…</td>
                  <td className="px-5 py-3 font-semibold text-gray-900">{formatCurrency(txn.amount)}</td>
                  <td className="px-5 py-3 text-gray-600">{txn.payment_method}</td>
                  <td className="px-5 py-3"><StatusBadge status={txn.status} /></td>
                  <td className="px-5 py-3 text-gray-400 text-xs">{formatDate(txn.created_at)}</td>
                </tr>
              ))}
              {!stats?.recent_transactions?.length && (
                <tr>
                  <td colSpan={5} className="px-5 py-8 text-center text-sm text-gray-400">
                    No transactions yet
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

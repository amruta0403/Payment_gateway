'use client'
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts'

const COLORS: Record<string, string> = {
  CARD:       '#6366f1',
  UPI:        '#10b981',
  NETBANKING: '#f59e0b',
  WALLET:     '#3b82f6',
  OTHER:      '#94a3b8',
}

interface PaymentMethodChartProps {
  data: Record<string, number>
}

export function PaymentMethodChart({ data }: PaymentMethodChartProps) {
  const chartData = Object.entries(data || {}).map(([name, value]) => ({ name, value }))

  if (chartData.length === 0) {
    return (
      <div className="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
        <h3 className="font-semibold text-gray-900 mb-4">Payment Methods</h3>
        <div className="h-40 flex items-center justify-center text-gray-400 text-sm">No data</div>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
      <h3 className="font-semibold text-gray-900 mb-4">Payment Methods</h3>
      <ResponsiveContainer width="100%" height={180}>
        <PieChart>
          <Pie data={chartData} cx="50%" cy="50%" innerRadius={50} outerRadius={75}
            paddingAngle={3} dataKey="value">
            {chartData.map((entry) => (
              <Cell key={entry.name} fill={COLORS[entry.name] || COLORS.OTHER} />
            ))}
          </Pie>
          <Tooltip formatter={(v: number) => [v, 'Transactions']} />
          <Legend iconType="circle" iconSize={8} formatter={v => (
            <span className="text-xs text-gray-600">{v}</span>
          )} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}

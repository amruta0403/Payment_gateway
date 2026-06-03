'use client'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer
} from 'recharts'
import { format, parseISO } from 'date-fns'

interface VolumeChartProps {
  data: Array<{
    date: string
    gross_paise?: number
    total_gross?: number
    total_count?: number
  }>
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null
  const rupees = ((payload[0]?.value || 0) / 100).toFixed(2)
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-3 shadow-lg text-sm">
      <p className="font-medium text-gray-700">{label}</p>
      <p className="text-brand-600 font-bold">₹{Number(rupees).toLocaleString('en-IN')}</p>
      {payload[1] && <p className="text-gray-500">{payload[1].value} txns</p>}
    </div>
  )
}

export function VolumeChart({ data }: VolumeChartProps) {
  const chartData = data.map(d => ({
    date: (() => { try { return format(parseISO(d.date), 'dd MMM') } catch { return d.date } })(),
    volume: d.gross_paise ?? d.total_gross ?? 0,
    count: d.total_count ?? 0,
  }))

  return (
    <div className="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="font-semibold text-gray-900">Transaction Volume</h3>
          <p className="text-sm text-gray-500">Last 30 days</p>
        </div>
      </div>

      {chartData.length === 0 ? (
        <div className="h-52 flex items-center justify-center text-gray-400 text-sm">
          No data available
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={chartData} margin={{ top: 5, right: 5, bottom: 5, left: 0 }}>
            <defs>
              <linearGradient id="volumeGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#6366f1" stopOpacity={0.15} />
                <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
            <YAxis
              tick={{ fontSize: 11, fill: '#9ca3af' }}
              tickLine={false}
              axisLine={false}
              tickFormatter={v => `₹${(v/100/1000).toFixed(0)}k`}
            />
            <Tooltip content={<CustomTooltip />} />
            <Area
              type="monotone" dataKey="volume" stroke="#6366f1" strokeWidth={2}
              fill="url(#volumeGrad)" dot={false} activeDot={{ r: 4, fill: '#6366f1' }}
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

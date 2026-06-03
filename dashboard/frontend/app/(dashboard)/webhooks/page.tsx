'use client'
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getWebhooks, createWebhook, deleteWebhook, testWebhook, getMyMerchant } from '@/lib/api'
import { formatDate } from '@/lib/utils'
import { PageHeader } from '@/components/ui/PageHeader'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { EmptyState } from '@/components/ui/EmptyState'
import { Webhook, Plus, X, Trash2, Zap, Copy } from 'lucide-react'
import toast from 'react-hot-toast'

const ALL_EVENTS = [
  'payment.captured','payment.failed','refund.initiated','refund.completed',
  'settlement.completed','merchant.kyc_completed','merchant.kyc_rejected',
]

export default function WebhooksPage() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ url: '', events: ['payment.captured'] })
  const [newSecret, setNewSecret] = useState<string | null>(null)

  const { data: merchant } = useQuery({ queryKey: ['merchant-me'], queryFn: getMyMerchant })
  const merchantId = merchant?.id

  const { data, isLoading } = useQuery({
    queryKey: ['webhooks', merchantId],
    queryFn: () => getWebhooks(merchantId!),
    enabled: !!merchantId,
  })

  const createMutation = useMutation({
    mutationFn: (body: object) => createWebhook(merchantId!, body),
    onSuccess: (res) => {
      setNewSecret(res.webhook_secret)
      qc.invalidateQueries({ queryKey: ['webhooks'] })
      setShowForm(false)
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail || 'Failed to create webhook'),
  })

  const deleteMutation = useMutation({
    mutationFn: (whId: string) => deleteWebhook(merchantId!, whId),
    onSuccess: () => { toast.success('Webhook deleted'); qc.invalidateQueries({ queryKey: ['webhooks'] }) },
  })

  const testMutation = useMutation({
    mutationFn: (whId: string) => testWebhook(merchantId!, whId),
    onSuccess: (res) => toast.success(`Test ${res.status}!`),
    onError: () => toast.error('Test failed'),
  })

  const hooks = Array.isArray(data) ? data : []

  const toggleEvent = (evt: string) => {
    setForm(f => ({
      ...f,
      events: f.events.includes(evt) ? f.events.filter(e => e !== evt) : [...f.events, evt],
    }))
  }

  return (
    <div>
      <PageHeader
        title="Webhooks"
        description="Receive real-time payment event notifications"
        action={
          <button onClick={() => setShowForm(true)}
            className="flex items-center gap-2 bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-4 py-2.5 rounded-xl transition-colors">
            <Plus className="w-4 h-4" /> Add Endpoint
          </button>
        }
      />

      {/* New secret reveal */}
      {newSecret && (
        <div className="mb-5 bg-amber-50 border border-amber-200 rounded-2xl p-4">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <p className="text-sm font-semibold text-amber-800 mb-1">⚠️ Webhook Secret — Save it now!</p>
              <p className="text-xs text-amber-700 mb-3">Use this to verify webhook signatures. It will not be shown again.</p>
              <div className="flex items-center gap-2">
                <code className="text-xs bg-white px-3 py-2 rounded-lg border border-amber-200 font-mono text-gray-800 break-all">{newSecret}</code>
                <button onClick={() => { navigator.clipboard.writeText(newSecret); toast.success('Copied!') }}
                  className="p-1.5 hover:bg-amber-100 rounded-lg"><Copy className="w-4 h-4 text-amber-700" /></button>
              </div>
            </div>
            <button onClick={() => setNewSecret(null)} className="p-1 hover:bg-amber-100 rounded-lg ml-2">
              <X className="w-4 h-4 text-amber-700" />
            </button>
          </div>
        </div>
      )}

      {showForm && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl w-full max-w-md p-6 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-5">
              <h2 className="font-bold text-gray-900">Add Webhook Endpoint</h2>
              <button onClick={() => setShowForm(false)} className="p-1 hover:bg-gray-100 rounded-lg"><X className="w-4 h-4" /></button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">HTTPS URL *</label>
                <input value={form.url} onChange={e => setForm({...form, url: e.target.value})}
                  placeholder="https://yourapp.com/webhooks/payment"
                  className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-2">Events to subscribe</label>
                <div className="space-y-2">
                  {ALL_EVENTS.map(evt => (
                    <label key={evt} className="flex items-center gap-2 cursor-pointer">
                      <input type="checkbox" checked={form.events.includes(evt)} onChange={() => toggleEvent(evt)}
                        className="rounded text-brand-600" />
                      <span className="text-sm font-mono text-gray-700">{evt}</span>
                    </label>
                  ))}
                </div>
              </div>
              <button onClick={() => createMutation.mutate({ url: form.url, events: form.events })}
                disabled={createMutation.isPending || !form.url || form.events.length === 0}
                className="w-full bg-brand-600 hover:bg-brand-700 disabled:bg-brand-400 text-white font-medium py-2.5 rounded-xl transition-colors text-sm">
                {createMutation.isPending ? 'Creating…' : 'Register Endpoint'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="space-y-3">
        {isLoading ? <LoadingSpinner /> : hooks.length === 0 ? (
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100">
            <EmptyState icon={Webhook} title="No webhook endpoints" description="Register an HTTPS endpoint to receive real-time payment events." />
          </div>
        ) : hooks.map((wh: any) => (
          <div key={wh.id} className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
            <div className="flex items-start justify-between">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`w-2 h-2 rounded-full ${wh.is_active ? 'bg-green-500' : 'bg-gray-300'}`} />
                  <code className="text-sm font-medium text-gray-900 truncate">{wh.url}</code>
                </div>
                <div className="flex flex-wrap gap-1 mt-2">
                  {(wh.events || []).map((e: string) => (
                    <span key={e} className="text-xs px-2 py-0.5 bg-gray-100 rounded-md text-gray-600 font-mono">{e}</span>
                  ))}
                </div>
                <p className="text-xs text-gray-400 mt-2">
                  {wh.failure_count > 0 ? `⚠️ ${wh.failure_count} failures` : '✅ No failures'} · Created {formatDate(wh.created_at)}
                </p>
              </div>
              <div className="flex gap-2 ml-4">
                <button onClick={() => testMutation.mutate(wh.id)} disabled={testMutation.isPending}
                  className="p-2 text-brand-600 hover:bg-brand-50 rounded-xl transition-colors" title="Send test event">
                  <Zap className="w-4 h-4" />
                </button>
                <button onClick={() => { if (confirm('Delete this endpoint?')) deleteMutation.mutate(wh.id) }}
                  className="p-2 text-red-500 hover:bg-red-50 rounded-xl transition-colors">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

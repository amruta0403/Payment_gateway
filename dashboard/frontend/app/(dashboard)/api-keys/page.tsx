'use client'
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getApiKeys, createApiKey, revokeApiKey, getMyMerchant } from '@/lib/api'
import { formatDate } from '@/lib/utils'
import { PageHeader } from '@/components/ui/PageHeader'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { EmptyState } from '@/components/ui/EmptyState'
import { Key, Plus, X, Copy, Eye, EyeOff, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'

export default function ApiKeysPage() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ name: '', environment: 'SANDBOX' })
  const [newKey, setNewKey] = useState<string | null>(null)
  const [showKey, setShowKey] = useState(false)

  const { data: merchant } = useQuery({ queryKey: ['merchant-me'], queryFn: getMyMerchant })
  const merchantId = merchant?.id

  const { data, isLoading } = useQuery({
    queryKey: ['api-keys', merchantId],
    queryFn: () => getApiKeys(merchantId!),
    enabled: !!merchantId,
  })

  const createMutation = useMutation({
    mutationFn: (body: object) => createApiKey(merchantId!, body),
    onSuccess: (res) => {
      setNewKey(res.full_key)
      qc.invalidateQueries({ queryKey: ['api-keys'] })
      setShowForm(false)
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail || 'Failed to create key'),
  })

  const revokeMutation = useMutation({
    mutationFn: (keyId: string) => revokeApiKey(merchantId!, keyId),
    onSuccess: () => { toast.success('Key revoked'); qc.invalidateQueries({ queryKey: ['api-keys'] }) },
  })

  const keys = Array.isArray(data) ? data : []

  return (
    <div>
      <PageHeader
        title="API Keys"
        description="Manage your payment integration keys"
        action={
          <button onClick={() => setShowForm(true)}
            className="flex items-center gap-2 bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium px-4 py-2.5 rounded-xl transition-colors">
            <Plus className="w-4 h-4" /> New Key
          </button>
        }
      />

      {/* Newly created key — show ONCE */}
      {newKey && (
        <div className="mb-5 bg-green-50 border border-green-200 rounded-2xl p-4">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <p className="text-sm font-semibold text-green-800 mb-1">✅ API Key Created — Save it now!</p>
              <p className="text-xs text-green-700 mb-3">This key will NOT be shown again. Store it in your secrets manager immediately.</p>
              <div className="flex items-center gap-2">
                <code className="text-xs bg-white px-3 py-2 rounded-lg border border-green-200 text-gray-800 font-mono break-all">
                  {showKey ? newKey : `${newKey.slice(0, 20)}${'•'.repeat(20)}`}
                </code>
                <button onClick={() => setShowKey(!showKey)} className="p-1.5 hover:bg-green-100 rounded-lg">
                  {showKey ? <EyeOff className="w-4 h-4 text-green-700" /> : <Eye className="w-4 h-4 text-green-700" />}
                </button>
                <button onClick={() => { navigator.clipboard.writeText(newKey); toast.success('Copied!') }}
                  className="p-1.5 hover:bg-green-100 rounded-lg">
                  <Copy className="w-4 h-4 text-green-700" />
                </button>
              </div>
            </div>
            <button onClick={() => setNewKey(null)} className="p-1 hover:bg-green-100 rounded-lg ml-2">
              <X className="w-4 h-4 text-green-700" />
            </button>
          </div>
        </div>
      )}

      {showForm && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl w-full max-w-sm p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="font-bold text-gray-900">Create API Key</h2>
              <button onClick={() => setShowForm(false)} className="p-1 hover:bg-gray-100 rounded-lg"><X className="w-4 h-4" /></button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Key Name *</label>
                <input value={form.name} onChange={e => setForm({...form, name: e.target.value})}
                  placeholder="e.g. Production Integration"
                  className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Environment</label>
                <select value={form.environment} onChange={e => setForm({...form, environment: e.target.value})}
                  className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-brand-500">
                  <option>SANDBOX</option>
                  <option>LIVE</option>
                </select>
              </div>
              <button onClick={() => createMutation.mutate({ name: form.name, environment: form.environment, permissions: ['payments:read','payments:write'] })}
                disabled={createMutation.isPending || !form.name}
                className="w-full bg-brand-600 hover:bg-brand-700 disabled:bg-brand-400 text-white font-medium py-2.5 rounded-xl transition-colors text-sm">
                {createMutation.isPending ? 'Creating…' : 'Create Key'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        {isLoading ? <LoadingSpinner /> : keys.length === 0 ? (
          <EmptyState icon={Key} title="No API keys" description="Create an API key to start integrating with the payment gateway." />
        ) : (
          <div className="divide-y divide-gray-50">
            {keys.map((k: any) => (
              <div key={k.id} className="flex items-center justify-between px-5 py-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm text-gray-900">{k.name}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${k.environment === 'LIVE' ? 'bg-green-100 text-green-700' : 'bg-blue-100 text-blue-700'}`}>
                      {k.environment}
                    </span>
                    {!k.is_active && <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-700">Revoked</span>}
                  </div>
                  <p className="font-mono text-xs text-gray-400 mt-1">{k.key_prefix}••••••••</p>
                  <p className="text-xs text-gray-400 mt-0.5">{k.usage_count} uses · Created {formatDate(k.created_at)}</p>
                </div>
                {k.is_active && (
                  <button onClick={() => { if (confirm('Revoke this key?')) revokeMutation.mutate(k.id) }}
                    className="p-2 text-red-500 hover:bg-red-50 rounded-xl transition-colors ml-4">
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

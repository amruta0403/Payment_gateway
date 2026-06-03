'use client'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getMyMerchant, getChecklist, getBankAccounts, addBankAccount } from '@/lib/api'
import { formatDate } from '@/lib/utils'
import { PageHeader } from '@/components/ui/PageHeader'
import { LoadingSpinner } from '@/components/ui/LoadingSpinner'
import { useState } from 'react'
import { Plus, X, CheckCircle, Circle } from 'lucide-react'
import toast from 'react-hot-toast'

export default function SettingsPage() {
  const qc = useQueryClient()
  const [showAddBank, setShowAddBank] = useState(false)
  const [bankForm, setBankForm] = useState({
    account_holder_name: '', account_number: '', ifsc_code: '', account_type: 'CURRENT',
  })

  const { data: merchant, isLoading } = useQuery({ queryKey: ['merchant-me'], queryFn: getMyMerchant })
  const merchantId = merchant?.id

  const { data: checklist } = useQuery({
    queryKey: ['checklist', merchantId],
    queryFn: () => getChecklist(merchantId!),
    enabled: !!merchantId,
  })

  const { data: bankAccounts } = useQuery({
    queryKey: ['bank-accounts', merchantId],
    queryFn: () => getBankAccounts(merchantId!),
    enabled: !!merchantId,
  })

  const addBankMutation = useMutation({
    mutationFn: (body: object) => addBankAccount(merchantId!, body),
    onSuccess: () => {
      toast.success('Bank account added!')
      qc.invalidateQueries({ queryKey: ['bank-accounts'] })
      setShowAddBank(false)
      setBankForm({ account_holder_name: '', account_number: '', ifsc_code: '', account_type: 'CURRENT' })
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail || 'Failed to add bank account'),
  })

  if (isLoading) return <LoadingSpinner />

  const checklistItems = [
    { key: 'pan_verified',        label: 'PAN Verified' },
    { key: 'gstin_verified',      label: 'GSTIN Verified' },
    { key: 'bank_account_added',  label: 'Bank Account Added' },
    { key: 'bank_verified',       label: 'Bank Account Verified' },
    { key: 'kyc_docs_uploaded',   label: 'KYC Documents Uploaded' },
    { key: 'kyc_approved',        label: 'KYC Approved' },
  ]

  const accounts = Array.isArray(bankAccounts) ? bankAccounts : []

  return (
    <div className="space-y-6 max-w-2xl">
      <PageHeader title="Settings" description="Merchant profile and account configuration" />

      {/* Profile card */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
        <h3 className="font-semibold text-gray-900 mb-4">Business Profile</h3>
        <div className="grid grid-cols-2 gap-4 text-sm">
          {[
            ['Business Name', merchant?.business_name],
            ['Business Type', merchant?.business_type],
            ['Status', merchant?.status],
            ['Merchant ID', merchant?.id?.slice(0, 20) + '…'],
            ['Support Email', merchant?.support_email],
            ['Support Phone', merchant?.support_phone],
          ].map(([label, value]) => (
            <div key={label as string}>
              <p className="text-xs text-gray-500 mb-0.5">{label}</p>
              <p className="font-medium text-gray-900">{value || '—'}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Onboarding checklist */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
        <h3 className="font-semibold text-gray-900 mb-4">Onboarding Checklist</h3>
        <div className="space-y-3">
          {checklistItems.map(({ key, label }) => {
            const done = checklist?.[key]
            return (
              <div key={key} className="flex items-center gap-3">
                {done
                  ? <CheckCircle className="w-5 h-5 text-green-500 flex-shrink-0" />
                  : <Circle className="w-5 h-5 text-gray-300 flex-shrink-0" />}
                <span className={`text-sm ${done ? 'text-gray-900' : 'text-gray-400'}`}>{label}</span>
              </div>
            )
          })}
        </div>
        {checklist?.is_complete && (
          <div className="mt-4 p-3 bg-green-50 rounded-xl text-sm text-green-700 font-medium">
            ✅ Onboarding complete! Your account is fully active.
          </div>
        )}
      </div>

      {/* Fee config */}
      {merchant?.fee_config && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <h3 className="font-semibold text-gray-900 mb-4">Fee Configuration</h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div><p className="text-xs text-gray-500">Card MDR</p><p className="font-semibold">{merchant.fee_config.card_mdr_percent}%</p></div>
            <div><p className="text-xs text-gray-500">UPI Fee</p><p className="font-semibold">{merchant.fee_config.upi_flat_fee_paise === 0 ? 'Free (RBI mandate)' : `₹${merchant.fee_config.upi_flat_fee_paise / 100}`}</p></div>
            <div><p className="text-xs text-gray-500">Netbanking Fee</p><p className="font-semibold">₹{(merchant.fee_config.netbanking_flat_fee_paise || 0) / 100}</p></div>
            <div><p className="text-xs text-gray-500">GST on Fee</p><p className="font-semibold">{merchant.fee_config.gst_percent}%</p></div>
          </div>
        </div>
      )}

      {/* Bank accounts */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-gray-900">Bank Accounts</h3>
          <button onClick={() => setShowAddBank(true)}
            className="flex items-center gap-1.5 text-sm text-brand-600 hover:text-brand-700 font-medium">
            <Plus className="w-4 h-4" /> Add
          </button>
        </div>

        {accounts.length === 0 ? (
          <p className="text-sm text-gray-400">No bank accounts yet. Add one to receive settlements.</p>
        ) : (
          <div className="space-y-3">
            {accounts.map((acc: any) => (
              <div key={acc.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-xl">
                <div>
                  <p className="text-sm font-medium text-gray-900">{acc.account_holder_name}</p>
                  <p className="text-xs text-gray-500">{acc.ifsc_code} · ••••{acc.account_number_last4}</p>
                </div>
                <div className="flex items-center gap-2">
                  {acc.is_primary && <span className="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full">Primary</span>}
                  <span className={`text-xs px-2 py-0.5 rounded-full ${acc.is_verified ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'}`}>
                    {acc.is_verified ? 'Verified' : 'Unverified'}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}

        {showAddBank && (
          <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl w-full max-w-sm p-6">
              <div className="flex items-center justify-between mb-5">
                <h2 className="font-bold text-gray-900">Add Bank Account</h2>
                <button onClick={() => setShowAddBank(false)}><X className="w-4 h-4" /></button>
              </div>
              <div className="space-y-4">
                {[
                  { key: 'account_holder_name', label: 'Account Holder Name', placeholder: 'As per bank records' },
                  { key: 'account_number', label: 'Account Number', placeholder: '9876543210', type: 'text' },
                  { key: 'ifsc_code', label: 'IFSC Code', placeholder: 'HDFC0001234' },
                ].map(({ key, label, placeholder, type }) => (
                  <div key={key}>
                    <label className="block text-xs font-medium text-gray-700 mb-1">{label}</label>
                    <input value={(bankForm as any)[key]}
                      onChange={e => setBankForm({...bankForm, [key]: e.target.value})}
                      placeholder={placeholder} type={type || 'text'}
                      className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" />
                  </div>
                ))}
                <button
                  onClick={() => addBankMutation.mutate(bankForm)}
                  disabled={addBankMutation.isPending}
                  className="w-full bg-brand-600 hover:bg-brand-700 disabled:bg-brand-400 text-white font-medium py-2.5 rounded-xl transition-colors text-sm">
                  {addBankMutation.isPending ? 'Adding…' : 'Add Account'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

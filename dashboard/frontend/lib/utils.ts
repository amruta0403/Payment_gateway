import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatCurrency(paise: number): string {
  const rupees = paise / 100
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
  }).format(rupees)
}

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

export function formatDateShort(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleDateString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
  })
}

export function truncate(str: string, n: number): string {
  return str.length > n ? str.slice(0, n) + '…' : str
}

export const STATUS_COLORS: Record<string, string> = {
  // Payment statuses
  CAPTURED:           'bg-green-100 text-green-800',
  SETTLED:            'bg-emerald-100 text-emerald-800',
  AUTHORIZED:         'bg-blue-100 text-blue-800',
  PENDING:            'bg-yellow-100 text-yellow-800',
  PROCESSING:         'bg-blue-100 text-blue-800',
  CREATED:            'bg-gray-100 text-gray-700',
  FAILED:             'bg-red-100 text-red-800',
  CANCELLED:          'bg-gray-100 text-gray-700',
  REFUNDED:           'bg-purple-100 text-purple-800',
  PARTIALLY_REFUNDED: 'bg-purple-100 text-purple-700',
  DISPUTED:           'bg-orange-100 text-orange-800',
  SETTLEMENT_INITIATED: 'bg-teal-100 text-teal-800',
  // Settlement
  COMPLETED:          'bg-green-100 text-green-800',
  // Refund
  SUCCESS:            'bg-green-100 text-green-800',
  INITIATED:          'bg-yellow-100 text-yellow-800',
  // KYC
  ACTIVE:             'bg-green-100 text-green-800',
  DRAFT:              'bg-gray-100 text-gray-700',
  PENDING_KYC:        'bg-yellow-100 text-yellow-800',
  SUSPENDED:          'bg-red-100 text-red-800',
  // Decision
  ALLOW:              'bg-green-100 text-green-800',
  CHALLENGE:          'bg-yellow-100 text-yellow-800',
  BLOCK:              'bg-red-100 text-red-800',
}

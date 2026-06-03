'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils'
import {
  LayoutDashboard, ArrowLeftRight, CreditCard, RefreshCw,
  Landmark, Key, Webhook, Settings, X, TrendingUp,
} from 'lucide-react'

const NAV = [
  { href: '/dashboard',      label: 'Overview',      icon: LayoutDashboard },
  { href: '/transactions',   label: 'Transactions',  icon: ArrowLeftRight },
  { href: '/payments',       label: 'Payments',      icon: CreditCard },
  { href: '/refunds',        label: 'Refunds',       icon: RefreshCw },
  { href: '/settlements',    label: 'Settlements',   icon: Landmark },
  { href: '/api-keys',       label: 'API Keys',      icon: Key },
  { href: '/webhooks',       label: 'Webhooks',      icon: Webhook },
  { href: '/settings',       label: 'Settings',      icon: Settings },
]

interface SidebarProps {
  open: boolean
  onClose: () => void
}

export function Sidebar({ open, onClose }: SidebarProps) {
  const pathname = usePathname()

  return (
    <>
      {/* Mobile overlay */}
      {open && (
        <div className="fixed inset-0 bg-black/50 z-20 lg:hidden" onClick={onClose} />
      )}

      <aside className={cn(
        'fixed top-0 left-0 h-full w-64 bg-white border-r border-gray-100 z-30 transition-transform duration-200',
        'flex flex-col',
        open ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
      )}>
        {/* Logo */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-brand-600 rounded-lg flex items-center justify-center">
              <TrendingUp className="w-4 h-4 text-white" />
            </div>
            <span className="font-bold text-gray-900">PayGateway</span>
          </div>
          <button onClick={onClose} className="lg:hidden p-1 rounded-lg hover:bg-gray-100">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || (href !== '/dashboard' && pathname.startsWith(href))
            return (
              <Link
                key={href}
                href={href}
                onClick={onClose}
                className={cn(
                  'flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-colors',
                  active
                    ? 'bg-brand-50 text-brand-700'
                    : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900',
                )}
              >
                <Icon className={cn('w-4 h-4', active ? 'text-brand-600' : 'text-gray-400')} />
                {label}
              </Link>
            )
          })}
        </nav>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-100">
          <p className="text-xs text-gray-400">Payment Gateway v1.0</p>
        </div>
      </aside>
    </>
  )
}

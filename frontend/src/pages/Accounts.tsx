import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Building2,
  Check,
  DollarSign,
  Eye,
  EyeOff,
  Pencil,
  Plus,
  RefreshCw,
  TrendingUp,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { usePlaidLink } from 'react-plaid-link'
import { useNavigate } from 'react-router-dom'
import { accountsApi } from '../api/accounts'
import { plaidApi } from '../api/plaid'
import type { Account } from '../types'

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount)
}

function formatRelativeTime(isoString: string) {
  const date = new Date(isoString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  if (diffMins < 1) return 'just now'
  if (diffMins < 60) return `${diffMins}m ago`
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  const diffDays = Math.floor(diffHours / 24)
  if (diffDays < 30) return `${diffDays}d ago`
  return date.toLocaleDateString()
}

function PlaidLinkButton() {
  const [linkToken, setLinkToken] = useState<string | null>(null)
  const queryClient = useQueryClient()

  useEffect(() => {
    plaidApi.createLinkToken().then((token) => {
      setLinkToken(token)
      localStorage.setItem('plaid_link_token', token)
    })
  }, [])

  const onSuccess = useCallback(
    async (publicToken: string) => {
      await plaidApi.exchangeToken(publicToken)
      localStorage.removeItem('plaid_link_token')
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
    },
    [queryClient],
  )

  const { open, ready } = usePlaidLink({
    token: linkToken,
    onSuccess,
  })

  return (
    <button
      onClick={() => open()}
      disabled={!ready}
      className="flex items-center gap-2 px-4 py-2.5 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 transition-colors disabled:opacity-50"
    >
      <Plus className="w-4 h-4" />
      Link Bank Account
    </button>
  )
}

function DataSourceBadge({ source }: { source: string }) {
  const config = {
    plaid: { label: 'Plaid', colors: 'bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400' },
    csv: { label: 'CSV', colors: 'bg-amber-50 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400' },
  }[source] || { label: source, colors: 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400' }

  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${config.colors}`}>
      {config.label}
    </span>
  )
}

function FreshnessText({ account }: { account: Account }) {
  if (account.data_source === 'plaid' && account.last_synced) {
    return (
      <span className="text-xs text-slate-400 dark:text-slate-500">
        Synced {formatRelativeTime(account.last_synced)}
      </span>
    )
  }
  if (account.latest_transaction_date) {
    return (
      <span className="text-xs text-slate-400 dark:text-slate-500">
        Latest txn: {account.latest_transaction_date}
      </span>
    )
  }
  return null
}

function InlineBalanceEditor({
  account,
  onSave,
  isPending,
}: {
  account: Account
  onSave: (balance: number) => void
  isPending: boolean
}) {
  const [isEditing, setIsEditing] = useState(false)
  const [value, setValue] = useState('')

  if (!isEditing) {
    return (
      <button
        onClick={(e) => {
          e.stopPropagation()
          setIsEditing(true)
          setValue(String(account.balance_effective ?? account.balance_current ?? 0))
        }}
        className="p-1 opacity-0 group-hover:opacity-100 hover:bg-slate-100 dark:hover:bg-slate-800 rounded transition-all"
        title="Edit balance"
      >
        <DollarSign className="w-3.5 h-3.5 text-slate-400" />
      </button>
    )
  }

  return (
    <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
      <span className="text-sm text-slate-500 dark:text-slate-400">$</span>
      <input
        type="number"
        step="0.01"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        className="w-28 px-2 py-1 text-sm border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
        autoFocus
        onKeyDown={(e) => {
          if (e.key === 'Enter' && value) {
            onSave(parseFloat(value))
            setIsEditing(false)
          }
          if (e.key === 'Escape') setIsEditing(false)
        }}
        disabled={isPending}
      />
      <button
        onClick={() => {
          if (value) onSave(parseFloat(value))
          setIsEditing(false)
        }}
        className="p-1 hover:bg-emerald-50 dark:hover:bg-emerald-900/30 rounded"
        disabled={isPending}
      >
        <Check className="w-3.5 h-3.5 text-emerald-600" />
      </button>
      <button
        onClick={() => setIsEditing(false)}
        className="p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded"
      >
        <X className="w-3.5 h-3.5 text-slate-400" />
      </button>
    </div>
  )
}

function InlineRenameEditor({
  account,
  onSave,
  isPending,
}: {
  account: Account
  onSave: (name: string) => void
  isPending: boolean
}) {
  const [isEditing, setIsEditing] = useState(false)
  const [value, setValue] = useState('')

  if (!isEditing) {
    return (
      <button
        onClick={(e) => {
          e.stopPropagation()
          setIsEditing(true)
          setValue(account.display_name || account.name)
        }}
        className="p-1 opacity-0 group-hover:opacity-100 hover:bg-slate-100 dark:hover:bg-slate-800 rounded transition-all"
        title="Rename account"
      >
        <Pencil className="w-3 h-3 text-slate-400" />
      </button>
    )
  }

  return (
    <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        className="w-48 px-2 py-1 text-sm border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
        autoFocus
        onKeyDown={(e) => {
          if (e.key === 'Enter' && value.trim()) {
            onSave(value.trim())
            setIsEditing(false)
          }
          if (e.key === 'Escape') setIsEditing(false)
        }}
        disabled={isPending}
      />
      <button
        onClick={() => {
          if (value.trim()) onSave(value.trim())
          setIsEditing(false)
        }}
        className="p-1 hover:bg-emerald-50 dark:hover:bg-emerald-900/30 rounded"
        disabled={isPending}
      >
        <Check className="w-3.5 h-3.5 text-emerald-600" />
      </button>
      <button
        onClick={() => setIsEditing(false)}
        className="p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded"
      >
        <X className="w-3.5 h-3.5 text-slate-400" />
      </button>
    </div>
  )
}

export default function Accounts() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [showHidden, setShowHidden] = useState(false)

  const { data: allAccounts = [], isLoading } = useQuery<Account[]>({
    queryKey: ['accounts', 'all'],
    queryFn: accountsApi.listAll,
  })

  const accounts = showHidden ? allAccounts : allAccounts.filter((a) => !a.is_hidden)

  const syncMutation = useMutation({
    mutationFn: accountsApi.sync,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['accounts'] }),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Parameters<typeof accountsApi.update>[1] }) =>
      accountsApi.update(id, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['accounts'] }),
  })

  // Net worth calculation (only visible accounts)
  const hiddenCount = allAccounts.filter((a) => a.is_hidden).length

  const { totalAssets, totalLiabilities, netWorth } = useMemo(() => {
    let assets = 0
    let liabilities = 0

    for (const a of allAccounts) {
      if (a.is_hidden) continue
      const bal = a.balance_effective ?? 0
      if (a.type === 'depository' || a.type === 'investment') {
        assets += bal
      } else if (a.type === 'credit' || a.type === 'loan') {
        liabilities += Math.abs(bal)
      }
    }

    return {
      totalAssets: assets,
      totalLiabilities: liabilities,
      netWorth: assets - liabilities,
    }
  }, [allAccounts])

  // Group visible accounts by institution
  const grouped = useMemo(() => {
    return accounts.reduce(
      (acc, account) => {
        const key = account.institution_name || 'Unknown'
        if (!acc[key]) acc[key] = []
        acc[key].push(account)
        return acc
      },
      {} as Record<string, Account[]>,
    )
  }, [accounts])

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Accounts</h1>
        <div className="flex gap-3">
          <button
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
            className="flex items-center gap-2 px-4 py-2.5 bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-300 rounded-lg text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${syncMutation.isPending ? 'animate-spin' : ''}`} />
            Sync All
          </button>
          <PlaidLinkButton />
        </div>
      </div>

      {isLoading ? (
        <p className="text-slate-500 dark:text-slate-400">Loading accounts...</p>
      ) : accounts.length === 0 && !showHidden ? (
        <div className="text-center py-16 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700">
          <Building2 className="w-12 h-12 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-2">
            No accounts linked
          </h2>
          <p className="text-slate-500 dark:text-slate-400 mb-6">
            Connect your bank accounts to get started.
          </p>
          <PlaidLinkButton />
        </div>
      ) : (
        <>
          {/* Net Worth Summary */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 px-6 py-4">
              <div className="flex items-center gap-2 mb-1">
                <TrendingUp className="w-4 h-4 text-emerald-500" />
                <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Net Worth</p>
              </div>
              <p
                className={`text-2xl font-bold ${netWorth >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}
              >
                {formatCurrency(netWorth)}
              </p>
            </div>
            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 px-6 py-4">
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">
                Total Assets
              </p>
              <p className="text-2xl font-bold text-slate-900 dark:text-slate-100">
                {formatCurrency(totalAssets)}
              </p>
            </div>
            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 px-6 py-4">
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">
                Total Liabilities
              </p>
              <p className="text-2xl font-bold text-slate-900 dark:text-slate-100">
                {formatCurrency(totalLiabilities)}
              </p>
            </div>
          </div>

          {/* Show hidden toggle */}
          {(hiddenCount > 0 || showHidden) && (
            <button
              onClick={() => setShowHidden(!showHidden)}
              className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300 mb-4 transition-colors"
            >
              {showHidden ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              {showHidden
                ? 'Hide hidden accounts'
                : `Show ${hiddenCount} hidden account${hiddenCount !== 1 ? 's' : ''}`}
            </button>
          )}

          {/* Account Groups */}
          <div className="space-y-6">
            {Object.entries(grouped).map(([institution, accts]) => (
              <div
                key={institution}
                className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700"
              >
                <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-800">
                  <div className="flex items-center gap-2">
                    <Building2 className="w-5 h-5 text-slate-400 dark:text-slate-400" />
                    <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                      {institution}
                    </h2>
                  </div>
                </div>
                <div className="divide-y divide-slate-100 dark:divide-slate-800">
                  {accts.map((account) => (
                    <div
                      key={account.id}
                      onClick={() => navigate(`/transactions?account_id=${account.id}`)}
                      className={`group px-6 py-4 flex items-center justify-between cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors ${
                        account.is_hidden ? 'opacity-50' : ''
                      }`}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <p className="font-medium text-slate-900 dark:text-slate-100 truncate">
                              {account.display_name || account.name}
                            </p>
                            <InlineRenameEditor
                              account={account}
                              onSave={(name) =>
                                updateMutation.mutate({
                                  id: account.id,
                                  body: { display_name: name },
                                })
                              }
                              isPending={updateMutation.isPending}
                            />
                          </div>
                          <div className="flex items-center gap-2 mt-0.5">
                            <p className="text-sm text-slate-500 dark:text-slate-400">
                              {account.subtype || account.type} &middot; {account.currency}
                            </p>
                            <DataSourceBadge source={account.data_source} />
                            <FreshnessText account={account} />
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="text-right">
                          <p className="font-semibold text-slate-900 dark:text-slate-100">
                            {account.balance_effective != null
                              ? formatCurrency(account.balance_effective)
                              : '—'}
                          </p>
                          {account.balance_available != null && (
                            <p className="text-sm text-slate-500 dark:text-slate-400">
                              Available: {formatCurrency(account.balance_available)}
                            </p>
                          )}
                        </div>
                        <InlineBalanceEditor
                          account={account}
                          onSave={(balance) =>
                            updateMutation.mutate({
                              id: account.id,
                              body: { balance_manual: balance },
                            })
                          }
                          isPending={updateMutation.isPending}
                        />
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            updateMutation.mutate({
                              id: account.id,
                              body: { is_hidden: !account.is_hidden },
                            })
                          }}
                          className="p-1 opacity-0 group-hover:opacity-100 hover:bg-slate-100 dark:hover:bg-slate-800 rounded transition-all"
                          title={account.is_hidden ? 'Unhide account' : 'Hide account'}
                        >
                          {account.is_hidden ? (
                            <Eye className="w-3.5 h-3.5 text-slate-400" />
                          ) : (
                            <EyeOff className="w-3.5 h-3.5 text-slate-400" />
                          )}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Building2, Plus, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { usePlaidLink } from 'react-plaid-link'
import { accountsApi } from '../api/accounts'
import { plaidApi } from '../api/plaid'
import type { Account } from '../types'

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount)
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

export default function Accounts() {
  const queryClient = useQueryClient()

  const { data: accounts = [], isLoading } = useQuery<Account[]>({
    queryKey: ['accounts'],
    queryFn: accountsApi.list,
  })

  const syncMutation = useMutation({
    mutationFn: accountsApi.sync,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['accounts'] }),
  })

  // Group accounts by institution
  const grouped = accounts.reduce(
    (acc, account) => {
      const key = account.institution_name || 'Unknown'
      if (!acc[key]) acc[key] = []
      acc[key].push(account)
      return acc
    },
    {} as Record<string, Account[]>,
  )

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Accounts</h1>
        <div className="flex gap-3">
          <button
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
            className="flex items-center gap-2 px-4 py-2.5 bg-white border border-slate-300 text-slate-700 rounded-lg text-sm font-medium hover:bg-slate-50 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${syncMutation.isPending ? 'animate-spin' : ''}`} />
            Sync All
          </button>
          <PlaidLinkButton />
        </div>
      </div>

      {isLoading ? (
        <p className="text-slate-500">Loading accounts...</p>
      ) : accounts.length === 0 ? (
        <div className="text-center py-16 bg-white rounded-xl border border-slate-200">
          <Building2 className="w-12 h-12 text-slate-300 mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-slate-900 mb-2">No accounts linked</h2>
          <p className="text-slate-500 mb-6">Connect your bank accounts to get started.</p>
          <PlaidLinkButton />
        </div>
      ) : (
        <div className="space-y-6">
          {Object.entries(grouped).map(([institution, accts]) => (
            <div key={institution} className="bg-white rounded-xl border border-slate-200">
              <div className="px-6 py-4 border-b border-slate-100">
                <div className="flex items-center gap-2">
                  <Building2 className="w-5 h-5 text-slate-400" />
                  <h2 className="text-lg font-semibold text-slate-900">{institution}</h2>
                </div>
              </div>
              <div className="divide-y divide-slate-100">
                {accts.map((account) => (
                  <div key={account.id} className="px-6 py-4 flex items-center justify-between">
                    <div>
                      <p className="font-medium text-slate-900">{account.name}</p>
                      <p className="text-sm text-slate-500">
                        {account.subtype || account.type} &middot; {account.currency}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="font-semibold text-slate-900">
                        {formatCurrency(account.balance_current || 0)}
                      </p>
                      {account.balance_available != null && (
                        <p className="text-sm text-slate-500">
                          Available: {formatCurrency(account.balance_available)}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

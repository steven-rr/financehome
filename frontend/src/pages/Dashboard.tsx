import { useQuery } from '@tanstack/react-query'
import { format, startOfMonth } from 'date-fns'
import { ArrowDownRight, ArrowUpRight, DollarSign, TrendingUp, Wallet } from 'lucide-react'
import { accountsApi } from '../api/accounts'
import { transactionsApi } from '../api/transactions'
import type { Account, Transaction } from '../types'

function StatCard({
  title,
  value,
  icon: Icon,
  color,
}: {
  title: string
  value: string
  icon: React.ElementType
  color: string
}) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-slate-500">{title}</span>
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${color}`}>
          <Icon className="w-5 h-5 text-white" />
        </div>
      </div>
      <p className="text-2xl font-bold text-slate-900">{value}</p>
    </div>
  )
}

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(amount)
}

export default function Dashboard() {
  const today = format(new Date(), 'yyyy-MM-dd')
  const monthStart = format(startOfMonth(new Date()), 'yyyy-MM-dd')

  const { data: accounts = [] } = useQuery<Account[]>({
    queryKey: ['accounts'],
    queryFn: accountsApi.list,
  })

  const { data: categories = [] } = useQuery({
    queryKey: ['categories', monthStart, today],
    queryFn: () => transactionsApi.categories(monthStart, today),
  })

  const { data: recentTxns } = useQuery({
    queryKey: ['transactions', 'recent'],
    queryFn: () => transactionsApi.list({ per_page: 10 }),
  })

  const totalBalance = accounts.reduce((sum, a) => {
    if (a.type === 'depository' || a.type === 'investment') {
      return sum + (a.balance_current || 0)
    }
    return sum
  }, 0)

  const totalDebt = accounts.reduce((sum, a) => {
    if (a.type === 'credit' || a.type === 'loan') {
      return sum + Math.abs(a.balance_current || 0)
    }
    return sum
  }, 0)

  const netWorth = totalBalance - totalDebt
  const monthlySpending = categories.reduce((sum, c) => sum + c.total, 0)

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900 mb-6">Dashboard</h1>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard
          title="Net Worth"
          value={formatCurrency(netWorth)}
          icon={TrendingUp}
          color="bg-emerald-500"
        />
        <StatCard
          title="Total Assets"
          value={formatCurrency(totalBalance)}
          icon={Wallet}
          color="bg-blue-500"
        />
        <StatCard
          title="Total Debt"
          value={formatCurrency(totalDebt)}
          icon={ArrowDownRight}
          color="bg-red-500"
        />
        <StatCard
          title="Spending This Month"
          value={formatCurrency(monthlySpending)}
          icon={DollarSign}
          color="bg-amber-500"
        />
      </div>

      {/* Accounts & Recent Transactions */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Accounts */}
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <h2 className="text-lg font-semibold text-slate-900 mb-4">Accounts</h2>
          {accounts.length === 0 ? (
            <p className="text-slate-500 text-sm">
              No accounts linked yet. Go to the Accounts page to connect your banks.
            </p>
          ) : (
            <div className="space-y-3">
              {accounts.map((account) => (
                <div
                  key={account.id}
                  className="flex items-center justify-between py-2 border-b border-slate-100 last:border-0"
                >
                  <div>
                    <p className="text-sm font-medium text-slate-900">{account.name}</p>
                    <p className="text-xs text-slate-500">
                      {account.institution_name} &middot; {account.subtype || account.type}
                    </p>
                  </div>
                  <p className="text-sm font-semibold text-slate-900">
                    {formatCurrency(account.balance_current || 0)}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Recent Transactions */}
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <h2 className="text-lg font-semibold text-slate-900 mb-4">Recent Transactions</h2>
          {!recentTxns || recentTxns.items.length === 0 ? (
            <p className="text-slate-500 text-sm">No transactions yet. Sync your accounts to see transactions.</p>
          ) : (
            <div className="space-y-3">
              {recentTxns.items.map((txn: Transaction) => (
                <div
                  key={txn.id}
                  className="flex items-center justify-between py-2 border-b border-slate-100 last:border-0"
                >
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-8 h-8 rounded-full flex items-center justify-center ${
                        txn.amount > 0 ? 'bg-red-50' : 'bg-emerald-50'
                      }`}
                    >
                      {txn.amount > 0 ? (
                        <ArrowUpRight className="w-4 h-4 text-red-500" />
                      ) : (
                        <ArrowDownRight className="w-4 h-4 text-emerald-500" />
                      )}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-slate-900">
                        {txn.merchant_name || txn.description}
                      </p>
                      <p className="text-xs text-slate-500">{txn.date}</p>
                    </div>
                  </div>
                  <p
                    className={`text-sm font-semibold ${
                      txn.amount > 0 ? 'text-red-600' : 'text-emerald-600'
                    }`}
                  >
                    {txn.amount > 0 ? '-' : '+'}
                    {formatCurrency(Math.abs(txn.amount))}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format, startOfMonth } from 'date-fns'
import { ArrowDownRight, ArrowUpRight, Check, ChevronDown, ChevronRight, DollarSign, Pencil, Plus, Repeat, Sparkles, Target, Trash2, TrendingUp, Wallet, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useTheme } from '../context/ThemeContext'
import { accountsApi } from '../api/accounts'
import { budgetsApi } from '../api/budgets'
import { insightsApi } from '../api/insights'
import { recurringApi } from '../api/recurring'
import { transactionsApi } from '../api/transactions'
import type { Account, Budget, MonthlyTrend, RecurringItem, RecurringSummary, Transaction } from '../types'

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
    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 p-6">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-slate-500 dark:text-slate-400">{title}</span>
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${color}`}>
          <Icon className="w-5 h-5 text-white" />
        </div>
      </div>
      <p className="text-2xl font-bold text-slate-900 dark:text-slate-100">{value}</p>
    </div>
  )
}

// Category groups: parent category → subcategories it combines
const CATEGORY_GROUPS: Record<string, string[]> = {
  'Food': ['Restaurants', 'Groceries'],
}

// Reverse lookup: subcategory → parent group
const SUBCATEGORY_TO_GROUP: Record<string, string> = {}
for (const [group, subs] of Object.entries(CATEGORY_GROUPS)) {
  for (const sub of subs) {
    SUBCATEGORY_TO_GROUP[sub] = group
  }
}

const CHART_COLORS = [
  '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
  '#ec4899', '#06b6d4', '#84cc16', '#f97316', '#6366f1',
]

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(amount)
}

export default function Dashboard() {
  const { isDark } = useTheme()
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

  const { data: recurring } = useQuery<RecurringSummary>({
    queryKey: ['recurring'],
    queryFn: recurringApi.getSummary,
  })

  const { data: monthlyTrend = [] } = useQuery<MonthlyTrend[]>({
    queryKey: ['monthly-trend'],
    queryFn: () => transactionsApi.monthlyTrend(6),
  })

  const { data: budgets = [] } = useQuery<Budget[]>({
    queryKey: ['budgets'],
    queryFn: budgetsApi.list,
  })

  const { data: spendingInsights, isLoading: insightsLoading } = useQuery({
    queryKey: ['spending-insights'],
    queryFn: insightsApi.spendingInsights,
    staleTime: 1000 * 60 * 60, // 1 hour
  })

  const queryClient = useQueryClient()

  const upsertBudget = useMutation({
    mutationFn: ({ category, monthly_limit }: { category: string; monthly_limit: number }) =>
      budgetsApi.upsert(category, monthly_limit),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['budgets'] }),
  })

  const deleteBudget = useMutation({
    mutationFn: (category: string) => budgetsApi.delete(category),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['budgets'] }),
  })

  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set())

  const toggleCategory = (cat: string) => {
    setExpandedCategories((prev) => {
      const next = new Set(prev)
      if (next.has(cat)) next.delete(cat)
      else next.add(cat)
      return next
    })
  }

  const [editingCategory, setEditingCategory] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const [addingBudget, setAddingBudget] = useState(false)
  const [newBudgetCategory, setNewBudgetCategory] = useState('')
  const [newBudgetLimit, setNewBudgetLimit] = useState('')

  const budgetProgress = useMemo(() => {
    const budgetMap = new Map(budgets.map(b => [b.category, b.monthly_limit]))
    const result: Array<{
      category: string
      spent: number
      limit: number
      percentage: number
      subcategories?: Array<{ name: string; spent: number }>
    }> = []
    for (const [category, limit] of budgetMap) {
      const subs = CATEGORY_GROUPS[category]
      if (subs) {
        // Group budget: sum spending from all subcategories
        const subBreakdown = subs.map(sub => {
          const spending = categories.find(c => c.category === sub)
          return { name: sub, spent: spending?.total ?? 0 }
        }).filter(s => s.spent > 0)
        const spent = subBreakdown.reduce((sum, s) => sum + s.spent, 0)
        result.push({ category, spent, limit, percentage: (spent / limit) * 100, subcategories: subBreakdown })
      } else {
        const spending = categories.find(c => c.category === category)
        const spent = spending?.total ?? 0
        result.push({ category, spent, limit, percentage: (spent / limit) * 100 })
      }
    }
    return result.sort((a, b) => b.percentage - a.percentage)
  }, [budgets, categories])

  const unbudgetedCategories = useMemo(() => {
    const budgeted = new Set(budgets.map(b => b.category))
    // Exclude subcategories that are covered by a budgeted group
    const coveredSubs = new Set<string>()
    for (const b of budgets) {
      const subs = CATEGORY_GROUPS[b.category]
      if (subs) subs.forEach(s => coveredSubs.add(s))
    }
    const individual = categories
      .filter(c => !budgeted.has(c.category) && !coveredSubs.has(c.category))
      .map(c => c.category)
    // Add available group names that aren't budgeted yet
    const availableGroups = Object.keys(CATEGORY_GROUPS).filter(g => !budgeted.has(g))
    return [...availableGroups, ...individual]
  }, [budgets, categories])

  const groupedRecurring = useMemo(() => {
    if (!recurring?.items.length) return []
    const groups: Record<string, { items: RecurringItem[]; total: number }> = {}
    for (const item of recurring.items) {
      if (!groups[item.category]) {
        groups[item.category] = { items: [], total: 0 }
      }
      groups[item.category].items.push(item)
      groups[item.category].total += item.amount
    }
    return Object.entries(groups)
      .map(([category, data]) => ({ category, ...data }))
      .sort((a, b) => b.total - a.total)
  }, [recurring])

  const visibleAccounts = accounts.filter((a) => !a.is_hidden)

  const totalBalance = visibleAccounts.reduce((sum, a) => {
    if (a.type === 'depository' || a.type === 'investment') {
      return sum + (a.balance_effective ?? a.balance_current ?? 0)
    }
    return sum
  }, 0)

  const totalDebt = visibleAccounts.reduce((sum, a) => {
    if (a.type === 'credit' || a.type === 'loan') {
      return sum + Math.abs(a.balance_effective ?? a.balance_current ?? 0)
    }
    return sum
  }, 0)

  const netWorth = totalBalance - totalDebt
  const monthlySpending = categories.reduce((sum, c) => sum + c.total, 0)

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 mb-6">Dashboard</h1>

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

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Spending by Category */}
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 p-6">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-4">Spending by Category</h2>
          {categories.length === 0 ? (
            <p className="text-slate-500 dark:text-slate-400 text-sm">No spending data this month.</p>
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie
                  data={categories}
                  dataKey="total"
                  nameKey="category"
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  paddingAngle={2}
                >
                  {categories.map((_, i) => (
                    <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value: number) => formatCurrency(value)}
                  contentStyle={{ borderRadius: '8px', border: '1px solid', borderColor: isDark ? '#334155' : '#e2e8f0', backgroundColor: isDark ? '#1e293b' : '#fff', color: isDark ? '#e2e8f0' : '#1e293b' }}
                />
                <Legend
                  layout="horizontal"
                  verticalAlign="bottom"
                  wrapperStyle={{ fontSize: '12px', color: isDark ? '#94a3b8' : undefined }}
                />
              </PieChart>
            </ResponsiveContainer>
          )}

          {/* Budget Targets */}
          {(budgetProgress.length > 0 || categories.length > 0) && (
            <div className="mt-6 pt-6 border-t border-slate-200 dark:border-slate-700">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Target className="w-4 h-4 text-slate-400" />
                  <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Budget Targets</h3>
                </div>
                {!addingBudget && unbudgetedCategories.length > 0 && (
                  <button
                    onClick={() => {
                      setAddingBudget(true)
                      setNewBudgetCategory(unbudgetedCategories[0])
                      setNewBudgetLimit('')
                    }}
                    className="flex items-center gap-1 text-xs text-emerald-600 hover:text-emerald-700 font-medium"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    Add Budget
                  </button>
                )}
              </div>

              {addingBudget && (
                <div className="flex items-center gap-2 mb-3 p-2 bg-slate-50 dark:bg-slate-800 rounded-lg">
                  <select
                    value={newBudgetCategory}
                    onChange={(e) => setNewBudgetCategory(e.target.value)}
                    className="text-sm border border-slate-300 dark:border-slate-600 rounded-md px-2 py-1 flex-1 bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100"
                  >
                    {unbudgetedCategories.map(cat => (
                      <option key={cat} value={cat}>{cat}</option>
                    ))}
                  </select>
                  <div className="flex items-center gap-1">
                    <span className="text-sm text-slate-500 dark:text-slate-400">$</span>
                    <input
                      type="number"
                      placeholder="0"
                      value={newBudgetLimit}
                      onChange={(e) => setNewBudgetLimit(e.target.value)}
                      className="w-20 text-sm border border-slate-300 dark:border-slate-600 rounded-md px-2 py-1 bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100"
                      min="1"
                      step="1"
                    />
                  </div>
                  <button
                    onClick={() => {
                      const limit = parseFloat(newBudgetLimit)
                      if (limit > 0 && newBudgetCategory) {
                        upsertBudget.mutate({ category: newBudgetCategory, monthly_limit: limit })
                        setAddingBudget(false)
                      }
                    }}
                    className="p-1 text-emerald-600 hover:text-emerald-700"
                  >
                    <Check className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setAddingBudget(false)}
                    className="p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              )}

              <div className="space-y-3">
                {budgetProgress.map(({ category, spent, limit, percentage, subcategories }) => (
                  <div key={category} className="group">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm text-slate-700 dark:text-slate-300">{category}</span>
                      <div className="flex items-center gap-2">
                        {editingCategory === category ? (
                          <div className="flex items-center gap-1">
                            <span className="text-xs text-slate-500 dark:text-slate-400">$</span>
                            <input
                              type="number"
                              value={editValue}
                              onChange={(e) => setEditValue(e.target.value)}
                              className="w-16 text-xs border border-slate-300 dark:border-slate-600 rounded px-1.5 py-0.5 bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100"
                              min="1"
                              autoFocus
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                  const val = parseFloat(editValue)
                                  if (val > 0) {
                                    upsertBudget.mutate({ category, monthly_limit: val })
                                    setEditingCategory(null)
                                  }
                                }
                                if (e.key === 'Escape') setEditingCategory(null)
                              }}
                            />
                            <button
                              onClick={() => {
                                const val = parseFloat(editValue)
                                if (val > 0) {
                                  upsertBudget.mutate({ category, monthly_limit: val })
                                  setEditingCategory(null)
                                }
                              }}
                              className="p-0.5 text-emerald-600 hover:text-emerald-700"
                            >
                              <Check className="w-3.5 h-3.5" />
                            </button>
                            <button
                              onClick={() => setEditingCategory(null)}
                              className="p-0.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        ) : (
                          <div className="flex items-center gap-1">
                            <span className="text-xs text-slate-500 dark:text-slate-400">
                              {formatCurrency(spent)} / {formatCurrency(limit)}
                            </span>
                            <button
                              onClick={() => {
                                setEditingCategory(category)
                                setEditValue(String(limit))
                              }}
                              className="p-0.5 opacity-0 group-hover:opacity-100 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-opacity"
                            >
                              <Pencil className="w-3 h-3" />
                            </button>
                            <button
                              onClick={() => deleteBudget.mutate(category)}
                              className="p-0.5 opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-500 transition-opacity"
                            >
                              <Trash2 className="w-3 h-3" />
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="w-full bg-slate-100 dark:bg-slate-800 rounded-full h-2">
                      <div
                        className={`h-2 rounded-full transition-all ${
                          percentage > 100
                            ? 'bg-red-500'
                            : percentage >= 75
                              ? 'bg-amber-500'
                              : 'bg-emerald-500'
                        }`}
                        style={{ width: `${Math.min(percentage, 100)}%` }}
                      />
                    </div>
                    {percentage > 100 && (
                      <p className="text-xs text-red-500 mt-0.5">
                        Over budget by {formatCurrency(spent - limit)}
                      </p>
                    )}
                    {subcategories && subcategories.length > 0 && (
                      <div className="flex gap-3 mt-1">
                        {subcategories.map(sub => (
                          <span key={sub.name} className="text-xs text-slate-400">
                            {sub.name}: {formatCurrency(sub.spent)}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {budgetProgress.length === 0 && !addingBudget && (
                <p className="text-xs text-slate-400">
                  No budget targets set. Click "Add Budget" to get started.
                </p>
              )}
            </div>
          )}
        </div>

        {/* Monthly Trend */}
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 p-6">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-4">Monthly Trend</h2>
          {monthlyTrend.length === 0 ? (
            <p className="text-slate-500 dark:text-slate-400 text-sm">Not enough data to show trends yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={monthlyTrend}>
                <XAxis
                  dataKey="month"
                  tick={{ fontSize: 12, fill: isDark ? '#94a3b8' : '#64748b' }}
                  axisLine={{ stroke: isDark ? '#334155' : '#e2e8f0' }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 12, fill: isDark ? '#94a3b8' : '#64748b' }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v) => `$${(v / 1000).toFixed(1)}k`}
                />
                <Tooltip
                  formatter={(value: number) => formatCurrency(value)}
                  contentStyle={{ borderRadius: '8px', border: '1px solid', borderColor: isDark ? '#334155' : '#e2e8f0', backgroundColor: isDark ? '#1e293b' : '#fff', color: isDark ? '#e2e8f0' : '#1e293b' }}
                />
                <Line
                  type="monotone"
                  dataKey="income"
                  stroke="#10b981"
                  strokeWidth={2}
                  dot={{ r: 4, fill: '#10b981' }}
                  name="Income"
                />
                <Line
                  type="monotone"
                  dataKey="expenses"
                  stroke="#ef4444"
                  strokeWidth={2}
                  dot={{ r: 4, fill: '#ef4444' }}
                  name="Expenses"
                />
                <Legend wrapperStyle={{ fontSize: '12px', color: isDark ? '#94a3b8' : undefined }} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Spending Insights */}
      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 p-6 mb-6">
        <div className="flex items-center gap-2 mb-4">
          <Sparkles className="w-5 h-5 text-purple-500" />
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Spending Insights</h2>
        </div>
        {insightsLoading ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">Analyzing your spending patterns...</p>
        ) : spendingInsights && spendingInsights.insights.length > 0 ? (
          <ul className="space-y-2">
            {spendingInsights.insights.map((insight, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-300">
                <span className="text-purple-400 mt-0.5">&#8226;</span>
                {insight}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-500 dark:text-slate-400">Not enough data for insights yet.</p>
        )}
      </div>

      {/* Accounts & Recent Transactions */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Accounts */}
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 p-6">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-4">Accounts</h2>
          {accounts.length === 0 ? (
            <p className="text-slate-500 dark:text-slate-400 text-sm">
              No accounts linked yet. Go to the Accounts page to connect your banks.
            </p>
          ) : (
            <div className="space-y-3">
              {accounts.map((account) => (
                <div
                  key={account.id}
                  className="flex items-center justify-between py-2 border-b border-slate-100 dark:border-slate-800 last:border-0"
                >
                  <div>
                    <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{account.name}</p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      {account.institution_name} &middot; {account.subtype || account.type}
                    </p>
                  </div>
                  <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                    {formatCurrency(account.balance_current || 0)}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Recent Transactions */}
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 p-6">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-4">Recent Transactions</h2>
          {!recentTxns || recentTxns.items.length === 0 ? (
            <p className="text-slate-500 dark:text-slate-400 text-sm">No transactions yet. Sync your accounts to see transactions.</p>
          ) : (
            <div className="space-y-3">
              {recentTxns.items.map((txn: Transaction) => (
                <div
                  key={txn.id}
                  className="flex items-center justify-between py-2 border-b border-slate-100 dark:border-slate-800 last:border-0"
                >
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-8 h-8 rounded-full flex items-center justify-center ${
                        txn.amount > 0 ? 'bg-red-50 dark:bg-red-900/30' : 'bg-emerald-50 dark:bg-emerald-900/30'
                      }`}
                    >
                      {txn.amount > 0 ? (
                        <ArrowUpRight className="w-4 h-4 text-red-500" />
                      ) : (
                        <ArrowDownRight className="w-4 h-4 text-emerald-500" />
                      )}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
                        {txn.merchant_name || txn.description}
                      </p>
                      <p className="text-xs text-slate-500 dark:text-slate-400">{txn.date}</p>
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

      {/* Monthly Autopilot */}
      <div className="mt-6 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Repeat className="w-5 h-5 text-slate-400" />
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Monthly Autopilot</h2>
          </div>
          {recurring && recurring.items.length > 0 && (
            <div className="text-right">
              <p className="text-xs text-slate-500 dark:text-slate-400">Estimated monthly</p>
              <p className="text-lg font-bold text-slate-900 dark:text-slate-100">
                {formatCurrency(recurring.total_monthly_cost)}
              </p>
            </div>
          )}
        </div>

        {groupedRecurring.length === 0 ? (
          <p className="text-slate-500 dark:text-slate-400 text-sm">
            Not enough transaction history to detect recurring expenses yet.
          </p>
        ) : (
          <div className="space-y-1">
            {groupedRecurring.map((group) => {
              const isExpanded = expandedCategories.has(group.category)
              return (
                <div key={group.category}>
                  <button
                    onClick={() => toggleCategory(group.category)}
                    className="w-full flex items-center justify-between py-3 px-2 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      {isExpanded ? (
                        <ChevronDown className="w-4 h-4 text-slate-400" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-slate-400" />
                      )}
                      <span className="text-sm font-medium text-slate-900 dark:text-slate-100">{group.category}</span>
                      <span className="text-xs text-slate-400">{group.items.length}</span>
                    </div>
                    <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                      {formatCurrency(group.total)}
                    </span>
                  </button>
                  {isExpanded && (
                    <div className="ml-7 pl-4 border-l-2 border-slate-100 dark:border-slate-800 space-y-1 pb-2">
                      {group.items.map((item, i) => (
                        <div
                          key={i}
                          className="flex items-center justify-between py-2 px-2"
                        >
                          <div>
                            <p className="text-sm text-slate-700 dark:text-slate-300">{item.merchant}</p>
                            <p className="text-xs text-slate-400">
                              {item.frequency.charAt(0).toUpperCase() + item.frequency.slice(1)}
                            </p>
                          </div>
                          <p className="text-sm text-slate-600 dark:text-slate-400">
                            {formatCurrency(item.amount)}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

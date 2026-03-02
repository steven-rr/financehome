import { useQuery } from '@tanstack/react-query'
import { addMonths, endOfMonth, format, startOfMonth, subMonths } from 'date-fns'
import React, { useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { exportApi } from '../api/export'
import { transactionsApi } from '../api/transactions'
import TransactionDetailModal from '../components/TransactionDetailModal'
import { useTheme } from '../context/ThemeContext'
import type { ExpenseTransaction, Transaction } from '../types'

type MerchantGroup = {
  key: string
  transactions: ExpenseTransaction[]
  total: number
}

function groupByMerchant(txns: ExpenseTransaction[]): MerchantGroup[] {
  const groups = new Map<string, ExpenseTransaction[]>()
  for (const t of txns) {
    const key = t.merchant_name || t.description
    const existing = groups.get(key)
    if (existing) existing.push(t)
    else groups.set(key, [t])
  }
  return Array.from(groups.entries())
    .map(([key, transactions]) => ({
      key,
      transactions,
      total: transactions.reduce((sum, t) => sum + t.amount, 0),
    }))
    .sort((a, b) => b.total - a.total)
}

const COLORS = [
  '#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6',
  '#ec4899', '#06b6d4', '#f97316', '#84cc16', '#6366f1',
]

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount)
}

function DeltaBadge({ current, previous, label, invertColors }: {
  current: number
  previous: number | undefined
  label: string
  invertColors?: boolean // true for expenses: decrease is good
}) {
  if (previous === undefined || previous === 0) return null
  const diff = current - previous
  const absDiff = Math.abs(diff)
  const isPositive = diff > 0
  // For income/net: increase is good (green). For expenses: decrease is good (green).
  const isGood = invertColors ? !isPositive : isPositive
  if (absDiff < 1) return null
  const arrow = isPositive ? '\u2191' : '\u2193'
  const sign = isPositive ? '+' : '-'

  let textColor: string
  if (absDiff >= 200) {
    textColor = isGood ? 'text-emerald-600/80 dark:text-emerald-400/70 font-semibold' : 'text-red-500/80 dark:text-red-400/70 font-semibold'
  } else if (absDiff >= 50) {
    textColor = isGood ? 'text-emerald-500/60 dark:text-emerald-400/50' : 'text-red-400/60 dark:text-red-400/50'
  } else {
    textColor = isGood ? 'text-emerald-400/40 dark:text-emerald-400/30' : 'text-red-300/40 dark:text-red-400/30'
  }

  return (
    <div className="mt-0.5 text-left">
      <span className={`text-xs ${textColor}`}>
        {arrow} {sign}${Math.round(absDiff).toLocaleString()} vs {label}
      </span>
    </div>
  )
}

export default function Analytics() {
  const { isDark } = useTheme()
  const [selectedMonth, setSelectedMonth] = useState(new Date())
  const [useCustomRange, setUseCustomRange] = useState(false)
  const [customStart, setCustomStart] = useState(format(startOfMonth(subMonths(new Date(), 2)), 'yyyy-MM-dd'))
  const [customEnd, setCustomEnd] = useState(format(new Date(), 'yyyy-MM-dd'))

  const startDate = useCustomRange ? customStart : format(startOfMonth(selectedMonth), 'yyyy-MM-dd')
  const endDate = useCustomRange ? customEnd : format(endOfMonth(selectedMonth), 'yyyy-MM-dd')

  // Previous month dates for comparison (only in monthly view)
  const prevMonth = subMonths(selectedMonth, 1)
  const prevStartDate = format(startOfMonth(prevMonth), 'yyyy-MM-dd')
  const prevEndDate = format(endOfMonth(prevMonth), 'yyyy-MM-dd')
  const prevMonthLabel = format(prevMonth, 'MMM')

  const { data: categories = [] } = useQuery({
    queryKey: ['categories', startDate, endDate],
    queryFn: () => transactionsApi.categories(startDate, endDate),
  })

  const { data: incomeExpenses } = useQuery({
    queryKey: ['income-expenses', startDate, endDate],
    queryFn: () => transactionsApi.incomeExpenses(startDate, endDate),
  })

  const { data: prevIncomeExpenses } = useQuery({
    queryKey: ['income-expenses', prevStartDate, prevEndDate],
    queryFn: () => transactionsApi.incomeExpenses(prevStartDate, prevEndDate),
    enabled: !useCustomRange,
  })

  const { data: prevCategories = [] } = useQuery({
    queryKey: ['categories', prevStartDate, prevEndDate],
    queryFn: () => transactionsApi.categories(prevStartDate, prevEndDate),
    enabled: !useCustomRange,
  })

  const prevCategoryMap = new Map(prevCategories.map((c) => [c.category, c.total]))

  const { data: incomeTransactions = [] } = useQuery({
    queryKey: ['income-transactions', startDate, endDate],
    queryFn: () => transactionsApi.incomeTransactions(startDate, endDate),
  })

  const { data: expenseTransactions = [] } = useQuery({
    queryKey: ['expense-transactions', startDate, endDate],
    queryFn: () => transactionsApi.expenseTransactions(startDate, endDate),
  })

  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set())
  const [expandedMerchants, setExpandedMerchants] = useState<Set<string>>(new Set())
  const [selectedTxn, setSelectedTxn] = useState<ExpenseTransaction | null>(null)

  const toggleCategory = (category: string) => {
    setExpandedCategories((prev) => {
      const next = new Set(prev)
      if (next.has(category)) next.delete(category)
      else next.add(category)
      return next
    })
  }

  const toggleMerchant = (category: string, merchantKey: string) => {
    const compositeKey = `${category}::${merchantKey}`
    setExpandedMerchants((prev) => {
      const next = new Set(prev)
      if (next.has(compositeKey)) next.delete(compositeKey)
      else next.add(compositeKey)
      return next
    })
  }

  const totalSpending = categories.reduce((sum, c) => sum + c.total, 0)

  const pieData = categories.slice(0, 8).map((c) => ({
    name: c.category,
    value: c.total,
  }))

  const barData = categories.slice(0, 10).map((c) => ({
    category: c.category.length > 15 ? c.category.slice(0, 15) + '...' : c.category,
    amount: c.total,
  }))

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 mb-6">Analytics</h1>

      {/* Date Filter */}
      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 p-4 mb-6">
        {useCustomRange ? (
          <div className="flex gap-4 items-end">
            <div>
              <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Start Date</label>
              <input
                type="date"
                value={customStart}
                onChange={(e) => setCustomStart(e.target.value)}
                className="px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">End Date</label>
              <input
                type="date"
                value={customEnd}
                onChange={(e) => setCustomEnd(e.target.value)}
                className="px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
              />
            </div>
            <button
              onClick={() => setUseCustomRange(false)}
              className="px-3 py-2 text-sm text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100 border border-slate-300 dark:border-slate-600 rounded-lg"
            >
              Back to monthly
            </button>
            <button
              onClick={() => exportApi.downloadTransactions(startDate, endDate)}
              className="px-3 py-2 text-sm text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg"
            >
              Export CSV
            </button>
          </div>
        ) : (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setSelectedMonth((m) => subMonths(m, 1))}
                className="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg text-slate-600 dark:text-slate-400"
              >
                &larr;
              </button>
              <div className="min-w-[160px] text-center">
                <span className="text-sm font-semibold text-slate-900 dark:text-slate-100 block">
                  {format(selectedMonth, 'MMMM yyyy')}
                </span>
                <span className="text-xs text-slate-400">
                  {format(startOfMonth(selectedMonth), 'MMM d')} – {format(endOfMonth(selectedMonth), 'MMM d, yyyy')}
                </span>
              </div>
              <button
                onClick={() => setSelectedMonth((m) => addMonths(m, 1))}
                className="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg text-slate-600 dark:text-slate-400"
              >
                &rarr;
              </button>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setUseCustomRange(true)}
                className="px-3 py-2 text-sm text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100 border border-slate-300 dark:border-slate-600 rounded-lg"
              >
                Custom range
              </button>
              <button
                onClick={() => exportApi.downloadTransactions(startDate, endDate)}
                className="px-3 py-2 text-sm text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg"
              >
                Export CSV
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Income / Expenses / Net Summary */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 p-4">
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Income</p>
          <p className="text-xl font-semibold text-emerald-600 dark:text-emerald-400/80">
            {formatCurrency(incomeExpenses?.income ?? 0)}
          </p>
          {!useCustomRange && (
            <DeltaBadge current={incomeExpenses?.income ?? 0} previous={prevIncomeExpenses?.income} label={prevMonthLabel} />
          )}
        </div>
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 p-4">
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Expenses</p>
          <p className="text-xl font-semibold text-red-500 dark:text-red-400/80">
            {formatCurrency(incomeExpenses?.expenses ?? 0)}
          </p>
          {!useCustomRange && (
            <DeltaBadge current={incomeExpenses?.expenses ?? 0} previous={prevIncomeExpenses?.expenses} label={prevMonthLabel} invertColors />
          )}
        </div>
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 p-4">
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Net</p>
          <p className={`text-xl font-semibold ${(incomeExpenses?.net ?? 0) >= 0 ? 'text-emerald-600 dark:text-emerald-400/80' : 'text-red-500 dark:text-red-400/80'}`}>
            {formatCurrency(incomeExpenses?.net ?? 0)}
          </p>
          {!useCustomRange && (
            <DeltaBadge current={incomeExpenses?.net ?? 0} previous={prevIncomeExpenses?.net} label={prevMonthLabel} />
          )}
        </div>
      </div>

      {categories.length === 0 ? (
        <div className="text-center py-16 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700">
          <p className="text-slate-500 dark:text-slate-400">No spending data for this period. Sync your accounts first.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Spending by Category - Donut Chart */}
          <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 p-6">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-4">Spending by Category</h2>
            <ResponsiveContainer width="100%" height={350}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={80}
                  outerRadius={140}
                  paddingAngle={2}
                  dataKey="value"
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  label={({ name, percent }: any) => `${name} (${((percent ?? 0) * 100).toFixed(0)}%)`}
                >
                  {pieData.map((_, index) => (
                    <Cell key={index} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value) => formatCurrency(Number(value))}
                  contentStyle={{
                    borderRadius: '8px',
                    border: '1px solid',
                    borderColor: isDark ? '#334155' : '#e2e8f0',
                    backgroundColor: isDark ? '#1e293b' : '#fff',
                    color: isDark ? '#e2e8f0' : '#1e293b',
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>

          {/* Top Categories - Bar Chart */}
          <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 p-6">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-4">Top Spending Categories</h2>
            <ResponsiveContainer width="100%" height={350}>
              <BarChart data={barData} layout="vertical" margin={{ left: 20 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke={isDark ? '#334155' : '#e2e8f0'} />
                <XAxis type="number" tickFormatter={(v) => `$${v}`} tick={{ fill: isDark ? '#94a3b8' : '#64748b' }} />
                <YAxis type="category" dataKey="category" width={120} tick={{ fontSize: 12, fill: isDark ? '#94a3b8' : '#64748b' }} />
                <Tooltip
                  formatter={(value) => formatCurrency(Number(value))}
                  contentStyle={{
                    borderRadius: '8px',
                    border: '1px solid',
                    borderColor: isDark ? '#334155' : '#e2e8f0',
                    backgroundColor: isDark ? '#1e293b' : '#fff',
                    color: isDark ? '#e2e8f0' : '#1e293b',
                  }}
                />
                <Legend />
                <Bar dataKey="amount" fill="#10b981" radius={[0, 4, 4, 0]} name="Spending" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Category Table */}
          <div className="lg:col-span-2 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-700">
              <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Category Breakdown</h2>
            </div>
            <table className="w-full">
              <thead>
                <tr className="bg-slate-50 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700">
                  <th className="text-left px-6 py-3 text-xs font-medium text-slate-500 dark:text-slate-400 uppercase">Category</th>
                  <th className="text-right px-6 py-3 text-xs font-medium text-slate-500 dark:text-slate-400 uppercase">Amount</th>
                  <th className="text-right px-6 py-3 text-xs font-medium text-slate-500 dark:text-slate-400 uppercase">Transactions</th>
                  <th className="text-right px-6 py-3 text-xs font-medium text-slate-500 dark:text-slate-400 uppercase">% of Total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {categories.map((c, i) => {
                  const isExpanded = expandedCategories.has(c.category)
                  const categoryTxns = isExpanded
                    ? expenseTransactions.filter((t) => (t.category || 'Uncategorized') === c.category)
                    : []
                  return (
                    <React.Fragment key={c.category}>
                      <tr
                        className="hover:bg-slate-50 dark:hover:bg-slate-800 cursor-pointer"
                        onClick={() => toggleCategory(c.category)}
                      >
                        <td className="px-6 py-3 text-sm text-slate-900 dark:text-slate-100">
                          <div className="flex items-center gap-2">
                            <span className="text-slate-400 text-xs w-4">
                              {isExpanded ? '\u25BC' : '\u25B6'}
                            </span>
                            <div
                              className="w-3 h-3 rounded-full"
                              style={{ backgroundColor: COLORS[i % COLORS.length] }}
                            />
                            {c.category}
                          </div>
                        </td>
                        <td className="px-6 py-3 text-sm text-right font-medium text-slate-900 dark:text-slate-100">
                          <div>{formatCurrency(c.total)}</div>
                          {!useCustomRange && (
                            <DeltaBadge current={c.total} previous={prevCategoryMap.get(c.category)} label={prevMonthLabel} invertColors />
                          )}
                        </td>
                        <td className="px-6 py-3 text-sm text-right text-slate-500 dark:text-slate-400">{c.count}</td>
                        <td className="px-6 py-3 text-sm text-right text-slate-500 dark:text-slate-400">
                          {totalSpending > 0 ? ((c.total / totalSpending) * 100).toFixed(1) : 0}%
                        </td>
                      </tr>
                      {isExpanded && groupByMerchant(categoryTxns).map((group) => {
                        const isMerchantExpanded = expandedMerchants.has(`${c.category}::${group.key}`)
                        if (group.transactions.length === 1) {
                          const t = group.transactions[0]
                          return (
                            <tr
                              key={group.key}
                              className="bg-slate-50 dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 cursor-pointer"
                              onClick={() => setSelectedTxn(t)}
                            >
                              <td className="pl-14 pr-6 py-2 text-xs text-slate-500 dark:text-slate-400">{t.date}</td>
                              <td className="px-6 py-2 text-xs text-slate-700 dark:text-slate-300">{t.merchant_name || t.description}</td>
                              <td className="px-6 py-2 text-xs text-right text-slate-700 dark:text-slate-300">{formatCurrency(t.amount)}</td>
                              <td></td>
                            </tr>
                          )
                        }
                        return (
                          <React.Fragment key={group.key}>
                            <tr
                              className="bg-slate-50 dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 cursor-pointer"
                              onClick={() => toggleMerchant(c.category, group.key)}
                            >
                              <td className="pl-12 pr-6 py-2 text-xs text-slate-900 dark:text-slate-100">
                                <div className="flex items-center gap-1.5">
                                  <span className="text-slate-400 text-[10px] w-3">
                                    {isMerchantExpanded ? '\u25BC' : '\u25B6'}
                                  </span>
                                  <span className="font-medium">{group.key}</span>
                                  <span className="text-slate-400 dark:text-slate-500 ml-1">
                                    {group.transactions.length} txns
                                  </span>
                                </div>
                              </td>
                              <td className="px-6 py-2 text-xs text-right font-medium text-slate-700 dark:text-slate-300">
                                {formatCurrency(group.total)}
                              </td>
                              <td></td>
                              <td></td>
                            </tr>
                            {isMerchantExpanded && group.transactions.map((t, j) => (
                              <tr
                                key={j}
                                className="bg-slate-100/50 dark:bg-slate-800/50 hover:bg-slate-100 dark:hover:bg-slate-700 cursor-pointer"
                                onClick={() => setSelectedTxn(t)}
                              >
                                <td className="pl-20 pr-6 py-1.5 text-xs text-slate-400 dark:text-slate-500">{t.date}</td>
                                <td className="px-6 py-1.5 text-xs text-slate-600 dark:text-slate-400">{t.merchant_name || t.description}</td>
                                <td className="px-6 py-1.5 text-xs text-right text-slate-600 dark:text-slate-400">{formatCurrency(t.amount)}</td>
                                <td></td>
                              </tr>
                            ))}
                          </React.Fragment>
                        )
                      })}
                    </React.Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Income Sources Table */}
      {incomeTransactions.length > 0 && (
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden mt-6">
          <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-700">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Income Sources</h2>
          </div>
          <table className="w-full">
            <thead>
              <tr className="bg-slate-50 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700">
                <th className="text-left px-6 py-3 text-xs font-medium text-slate-500 dark:text-slate-400 uppercase">Date</th>
                <th className="text-left px-6 py-3 text-xs font-medium text-slate-500 dark:text-slate-400 uppercase">Source</th>
                <th className="text-right px-6 py-3 text-xs font-medium text-slate-500 dark:text-slate-400 uppercase">Amount</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {incomeTransactions.map((t, i) => (
                <tr key={i} className="hover:bg-slate-50 dark:hover:bg-slate-800">
                  <td className="px-6 py-3 text-sm text-slate-500 dark:text-slate-400">{t.date}</td>
                  <td className="px-6 py-3 text-sm text-slate-900 dark:text-slate-100">{t.merchant_name || t.description}</td>
                  <td className="px-6 py-3 text-sm text-right font-medium text-emerald-600">
                    {formatCurrency(t.amount)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selectedTxn && (
        <TransactionDetailModal transaction={selectedTxn as unknown as Transaction} onClose={() => setSelectedTxn(null)} />
      )}
    </div>
  )
}

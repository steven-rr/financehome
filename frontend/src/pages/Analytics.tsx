import { useQuery } from '@tanstack/react-query'
import { format, startOfMonth, subMonths } from 'date-fns'
import { useState } from 'react'
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
import { transactionsApi } from '../api/transactions'

const COLORS = [
  '#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6',
  '#ec4899', '#06b6d4', '#f97316', '#84cc16', '#6366f1',
]

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount)
}

export default function Analytics() {
  const [startDate, setStartDate] = useState(
    format(startOfMonth(subMonths(new Date(), 2)), 'yyyy-MM-dd'),
  )
  const [endDate, setEndDate] = useState(format(new Date(), 'yyyy-MM-dd'))

  const { data: categories = [] } = useQuery({
    queryKey: ['categories', startDate, endDate],
    queryFn: () => transactionsApi.categories(startDate, endDate),
  })

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
      <h1 className="text-2xl font-bold text-slate-900 mb-6">Analytics</h1>

      {/* Date Range */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 mb-6">
        <div className="flex gap-4 items-end">
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">Start Date</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="px-3 py-2 border border-slate-300 rounded-lg text-sm"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">End Date</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="px-3 py-2 border border-slate-300 rounded-lg text-sm"
            />
          </div>
          <div className="text-sm text-slate-500">
            Total spending: <span className="font-semibold text-slate-900">{formatCurrency(totalSpending)}</span>
          </div>
        </div>
      </div>

      {categories.length === 0 ? (
        <div className="text-center py-16 bg-white rounded-xl border border-slate-200">
          <p className="text-slate-500">No spending data for this period. Sync your accounts first.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Spending by Category - Donut Chart */}
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h2 className="text-lg font-semibold text-slate-900 mb-4">Spending by Category</h2>
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
                  label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                >
                  {pieData.map((_, index) => (
                    <Cell key={index} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(value: number) => formatCurrency(value)} />
              </PieChart>
            </ResponsiveContainer>
          </div>

          {/* Top Categories - Bar Chart */}
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h2 className="text-lg font-semibold text-slate-900 mb-4">Top Spending Categories</h2>
            <ResponsiveContainer width="100%" height={350}>
              <BarChart data={barData} layout="vertical" margin={{ left: 20 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" tickFormatter={(v) => `$${v}`} />
                <YAxis type="category" dataKey="category" width={120} tick={{ fontSize: 12 }} />
                <Tooltip formatter={(value: number) => formatCurrency(value)} />
                <Legend />
                <Bar dataKey="amount" fill="#10b981" radius={[0, 4, 4, 0]} name="Spending" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Category Table */}
          <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200">
              <h2 className="text-lg font-semibold text-slate-900">Category Breakdown</h2>
            </div>
            <table className="w-full">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200">
                  <th className="text-left px-6 py-3 text-xs font-medium text-slate-500 uppercase">Category</th>
                  <th className="text-right px-6 py-3 text-xs font-medium text-slate-500 uppercase">Amount</th>
                  <th className="text-right px-6 py-3 text-xs font-medium text-slate-500 uppercase">Transactions</th>
                  <th className="text-right px-6 py-3 text-xs font-medium text-slate-500 uppercase">% of Total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {categories.map((c, i) => (
                  <tr key={c.category} className="hover:bg-slate-50">
                    <td className="px-6 py-3 text-sm">
                      <div className="flex items-center gap-2">
                        <div
                          className="w-3 h-3 rounded-full"
                          style={{ backgroundColor: COLORS[i % COLORS.length] }}
                        />
                        {c.category}
                      </div>
                    </td>
                    <td className="px-6 py-3 text-sm text-right font-medium">{formatCurrency(c.total)}</td>
                    <td className="px-6 py-3 text-sm text-right text-slate-500">{c.count}</td>
                    <td className="px-6 py-3 text-sm text-right text-slate-500">
                      {totalSpending > 0 ? ((c.total / totalSpending) * 100).toFixed(1) : 0}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

import { useQuery } from '@tanstack/react-query'
import { format, startOfMonth, subMonths } from 'date-fns'
import { ChevronLeft, ChevronRight, Download, Search } from 'lucide-react'
import { useState } from 'react'
import { accountsApi } from '../api/accounts'
import { exportApi } from '../api/export'
import { transactionsApi } from '../api/transactions'
import type { Account, TransactionFilters } from '../types'

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount)
}

export default function Transactions() {
  const [filters, setFilters] = useState<TransactionFilters>({
    start_date: format(startOfMonth(subMonths(new Date(), 1)), 'yyyy-MM-dd'),
    end_date: format(new Date(), 'yyyy-MM-dd'),
    page: 1,
    per_page: 50,
  })
  const [searchInput, setSearchInput] = useState('')

  const { data: accounts = [] } = useQuery<Account[]>({
    queryKey: ['accounts'],
    queryFn: accountsApi.list,
  })

  const { data, isLoading } = useQuery({
    queryKey: ['transactions', filters],
    queryFn: () => transactionsApi.list(filters),
  })

  const handleSearch = () => {
    setFilters((f) => ({ ...f, search: searchInput || undefined, page: 1 }))
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Transactions</h1>
        <button
          onClick={() => exportApi.downloadTransactions(filters.start_date, filters.end_date)}
          className="flex items-center gap-2 px-4 py-2 bg-slate-900 text-white text-sm font-medium rounded-lg hover:bg-slate-800 transition-colors"
        >
          <Download className="w-4 h-4" />
          Download CSV
        </button>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 mb-6">
        <div className="flex flex-wrap gap-4 items-end">
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">Start Date</label>
            <input
              type="date"
              value={filters.start_date || ''}
              onChange={(e) => setFilters((f) => ({ ...f, start_date: e.target.value, page: 1 }))}
              className="px-3 py-2 border border-slate-300 rounded-lg text-sm"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">End Date</label>
            <input
              type="date"
              value={filters.end_date || ''}
              onChange={(e) => setFilters((f) => ({ ...f, end_date: e.target.value, page: 1 }))}
              className="px-3 py-2 border border-slate-300 rounded-lg text-sm"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">Account</label>
            <select
              value={filters.account_id || ''}
              onChange={(e) =>
                setFilters((f) => ({ ...f, account_id: e.target.value || undefined, page: 1 }))
              }
              className="px-3 py-2 border border-slate-300 rounded-lg text-sm"
            >
              <option value="">All Accounts</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex-1 min-w-[200px]">
            <label className="block text-xs font-medium text-slate-500 mb-1">Search</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                placeholder="Search transactions..."
                className="flex-1 px-3 py-2 border border-slate-300 rounded-lg text-sm"
              />
              <button
                onClick={handleSearch}
                className="px-3 py-2 bg-slate-100 rounded-lg hover:bg-slate-200 transition-colors"
              >
                <Search className="w-4 h-4 text-slate-600" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center text-slate-500">Loading transactions...</div>
        ) : !data || data.items.length === 0 ? (
          <div className="p-8 text-center text-slate-500">No transactions found.</div>
        ) : (
          <>
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50">
                  <th className="text-left px-6 py-3 text-xs font-medium text-slate-500 uppercase">Date</th>
                  <th className="text-left px-6 py-3 text-xs font-medium text-slate-500 uppercase">Description</th>
                  <th className="text-left px-6 py-3 text-xs font-medium text-slate-500 uppercase">Category</th>
                  <th className="text-right px-6 py-3 text-xs font-medium text-slate-500 uppercase">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.items.map((txn) => (
                  <tr key={txn.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-6 py-3 text-sm text-slate-600">{txn.date}</td>
                    <td className="px-6 py-3">
                      <p className="text-sm font-medium text-slate-900">
                        {txn.merchant_name || txn.description}
                      </p>
                      {txn.merchant_name && (
                        <p className="text-xs text-slate-500">{txn.description}</p>
                      )}
                    </td>
                    <td className="px-6 py-3">
                      <span className="text-xs px-2 py-1 bg-slate-100 text-slate-600 rounded-full">
                        {txn.category || 'Uncategorized'}
                      </span>
                    </td>
                    <td
                      className={`px-6 py-3 text-sm font-semibold text-right ${
                        txn.amount > 0 ? 'text-red-600' : 'text-emerald-600'
                      }`}
                    >
                      {txn.amount > 0 ? '-' : '+'}
                      {formatCurrency(Math.abs(txn.amount))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Pagination */}
            <div className="flex items-center justify-between px-6 py-4 border-t border-slate-200">
              <p className="text-sm text-slate-500">
                Showing {(data.page - 1) * data.per_page + 1}–
                {Math.min(data.page * data.per_page, data.total)} of {data.total}
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setFilters((f) => ({ ...f, page: (f.page || 1) - 1 }))}
                  disabled={data.page <= 1}
                  className="p-2 rounded-lg border border-slate-300 hover:bg-slate-50 disabled:opacity-30"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setFilters((f) => ({ ...f, page: (f.page || 1) + 1 }))}
                  disabled={data.page >= data.pages}
                  className="p-2 rounded-lg border border-slate-300 hover:bg-slate-50 disabled:opacity-30"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

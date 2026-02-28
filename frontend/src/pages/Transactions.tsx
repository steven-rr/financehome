import { useQuery, useQueryClient } from '@tanstack/react-query'
import { format, startOfMonth, subMonths } from 'date-fns'
import { ChevronLeft, ChevronRight, Download, Search, Sparkles, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { accountsApi } from '../api/accounts'
import { csvImportApi } from '../api/csvImport'
import { exportApi } from '../api/export'
import { transactionsApi } from '../api/transactions'
import AIProviderToggle from '../components/AIProviderToggle'
import ImportModal, { type AccountMappings } from '../components/ImportModal'
import { useAIProvider } from '../hooks/useAIProvider'
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
  const [importStatus, setImportStatus] = useState<string | null>(null)
  const [isCategorizing, setIsCategorizing] = useState(false)
  const { provider, setProvider } = useAIProvider()
  const [isDragging, setIsDragging] = useState(false)
  const [pendingFiles, setPendingFiles] = useState<File[] | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const dragCounter = useRef(0)
  const queryClient = useQueryClient()

  const stageFiles = (files: File[]) => {
    const csvFiles = files.filter((f) => f.name.toLowerCase().endsWith('.csv'))
    if (csvFiles.length === 0) {
      setImportStatus('No .csv files found')
      setTimeout(() => setImportStatus(null), 5000)
      return
    }
    setPendingFiles(csvFiles)
  }

  const handleConfirmImport = async (mappings: AccountMappings) => {
    if (!pendingFiles) return
    const files = pendingFiles
    setPendingFiles(null)

    setImportStatus(`Importing ${files.length} file${files.length > 1 ? 's' : ''}...`)
    try {
      const formData = new FormData()
      files.forEach((f) => formData.append('files', f))
      formData.append('account_mappings', JSON.stringify(mappings))
      const result = await csvImportApi.importBulk(formData)
      const errors = result.files.filter((f) => f.error)
      let msg = `Imported ${result.imported} from ${files.length} file${files.length > 1 ? 's' : ''}, skipped ${result.skipped} duplicates`
      if (errors.length > 0) {
        msg += ` (${errors.length} failed)`
      }
      setImportStatus(msg)
      queryClient.invalidateQueries({ queryKey: ['transactions'] })
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
    } catch (err: unknown) {
      console.error('Import failed:', err)
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setImportStatus(detail ? `Import failed: ${detail}` : 'Import failed — check CSV format')
    }
    setTimeout(() => setImportStatus(null), 8000)
  }

  const handleCategorize = async () => {
    setIsCategorizing(true)
    setImportStatus('Categorizing transactions with AI...')
    try {
      const result = await transactionsApi.categorize(provider)
      if (result.categorized === 0) {
        setImportStatus('No uncategorized transactions found')
      } else {
        setImportStatus(`Categorized ${result.categorized} of ${result.total_uncategorized} transactions`)
      }
      queryClient.invalidateQueries({ queryKey: ['transactions'] })
      queryClient.invalidateQueries({ queryKey: ['categories'] })
      queryClient.invalidateQueries({ queryKey: ['insights'] })
    } catch (err) {
      console.error('Categorization failed:', err)
      setImportStatus('AI categorization failed')
    }
    setIsCategorizing(false)
    setTimeout(() => setImportStatus(null), 8000)
  }

  const handleFileImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      stageFiles(Array.from(e.target.files))
    }
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounter.current++
    if (e.dataTransfer.types.includes('Files')) {
      setIsDragging(true)
    }
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounter.current--
    if (dragCounter.current === 0) {
      setIsDragging(false)
    }
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
    dragCounter.current = 0
    const files = e.dataTransfer.files
    if (files.length > 0) {
      stageFiles(Array.from(files))
    }
  }

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
    <div
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
      className="relative"
    >
      {pendingFiles && (
        <ImportModal
          files={pendingFiles}
          accounts={accounts}
          onConfirm={handleConfirmImport}
          onCancel={() => setPendingFiles(null)}
        />
      )}
      {isDragging && (
        <div className="absolute inset-0 z-50 bg-emerald-50/80 dark:bg-emerald-900/30 border-2 border-dashed border-emerald-400 rounded-xl flex items-center justify-center backdrop-blur-sm">
          <div className="text-center">
            <Upload className="w-10 h-10 text-emerald-500 mx-auto mb-2" />
            <p className="text-lg font-semibold text-emerald-700 dark:text-emerald-400">Drop CSV files here</p>
            <p className="text-sm text-emerald-600 dark:text-emerald-500">Multiple files supported</p>
          </div>
        </div>
      )}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Transactions</h1>
        <div className="flex items-center gap-3">
          {importStatus && (
            <span className="text-sm text-slate-600 dark:text-slate-400">{importStatus}</span>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.CSV"
            multiple
            onChange={handleFileImport}
            className="hidden"
          />
          <AIProviderToggle provider={provider} onChange={setProvider} />
          <button
            onClick={handleCategorize}
            disabled={isCategorizing}
            className="flex items-center gap-2 px-4 py-2 border border-purple-300 dark:border-purple-700 text-purple-700 dark:text-purple-400 text-sm font-medium rounded-lg hover:bg-purple-50 dark:hover:bg-purple-900/30 transition-colors disabled:opacity-50"
          >
            <Sparkles className="w-4 h-4" />
            {isCategorizing ? 'Categorizing...' : 'AI Categorize'}
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-2 px-4 py-2 border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-300 text-sm font-medium rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
          >
            <Upload className="w-4 h-4" />
            Import CSV
          </button>
          <button
            onClick={() => exportApi.downloadTransactions(filters.start_date, filters.end_date)}
            className="flex items-center gap-2 px-4 py-2 bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 text-sm font-medium rounded-lg hover:bg-slate-800 dark:hover:bg-slate-200 transition-colors"
          >
            <Download className="w-4 h-4" />
            Download CSV
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 p-4 mb-6">
        <div className="flex flex-wrap gap-4 items-end">
          <div>
            <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Start Date</label>
            <input
              type="date"
              value={filters.start_date || ''}
              onChange={(e) => setFilters((f) => ({ ...f, start_date: e.target.value, page: 1 }))}
              className="px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">End Date</label>
            <input
              type="date"
              value={filters.end_date || ''}
              onChange={(e) => setFilters((f) => ({ ...f, end_date: e.target.value, page: 1 }))}
              className="px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Account</label>
            <select
              value={filters.account_id || ''}
              onChange={(e) =>
                setFilters((f) => ({ ...f, account_id: e.target.value || undefined, page: 1 }))
              }
              className="px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
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
            <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Search</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                placeholder="Search transactions..."
                className="flex-1 px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
              />
              <button
                onClick={handleSearch}
                className="px-3 py-2 bg-slate-100 dark:bg-slate-800 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
              >
                <Search className="w-4 h-4 text-slate-600 dark:text-slate-400" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center text-slate-500 dark:text-slate-400">Loading transactions...</div>
        ) : !data || data.items.length === 0 ? (
          <div className="p-8 text-center text-slate-500 dark:text-slate-400">No transactions found.</div>
        ) : (
          <>
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800">
                  <th className="text-left px-6 py-3 text-xs font-medium text-slate-500 dark:text-slate-400 uppercase">Date</th>
                  <th className="text-left px-6 py-3 text-xs font-medium text-slate-500 dark:text-slate-400 uppercase">Description</th>
                  <th className="text-left px-6 py-3 text-xs font-medium text-slate-500 dark:text-slate-400 uppercase">Category</th>
                  <th className="text-right px-6 py-3 text-xs font-medium text-slate-500 dark:text-slate-400 uppercase">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {data.items.map((txn) => (
                  <tr key={txn.id} className="hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors">
                    <td className="px-6 py-3 text-sm text-slate-600 dark:text-slate-400">{txn.date}</td>
                    <td className="px-6 py-3">
                      <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
                        {txn.merchant_name || txn.description}
                      </p>
                      {txn.merchant_name && (
                        <p className="text-xs text-slate-500 dark:text-slate-400">{txn.description}</p>
                      )}
                    </td>
                    <td className="px-6 py-3">
                      {txn.category ? (
                        <span className="text-xs px-2 py-1 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 rounded-full">
                          {txn.category}
                        </span>
                      ) : txn.ai_category ? (
                        <span className="text-xs px-2 py-1 bg-purple-50 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400 rounded-full">
                          {txn.ai_category}
                        </span>
                      ) : (
                        <span className="text-xs px-2 py-1 bg-slate-50 dark:bg-slate-800 text-slate-400 rounded-full">
                          Uncategorized
                        </span>
                      )}
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
            <div className="flex items-center justify-between px-6 py-4 border-t border-slate-200 dark:border-slate-700">
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Showing {(data.page - 1) * data.per_page + 1}–
                {Math.min(data.page * data.per_page, data.total)} of {data.total}
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setFilters((f) => ({ ...f, page: (f.page || 1) - 1 }))}
                  disabled={data.page <= 1}
                  className="p-2 rounded-lg border border-slate-300 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-30"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setFilters((f) => ({ ...f, page: (f.page || 1) + 1 }))}
                  disabled={data.page >= data.pages}
                  className="p-2 rounded-lg border border-slate-300 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-30"
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

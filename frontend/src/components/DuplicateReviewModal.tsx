import { AlertTriangle, Check, ChevronDown, ChevronUp, X } from 'lucide-react'
import { useState } from 'react'
import { csvImportApi, type DuplicateDecision, type SuspectedDuplicate } from '../api/csvImport'

interface DuplicateReviewModalProps {
  duplicates: SuspectedDuplicate[]
  defaultAccountId: string
  onComplete: (result: { imported: number; skipped: number }) => void
  onCancel: () => void
}

function formatAmount(amount: number): string {
  const abs = Math.abs(amount)
  const sign = amount < 0 ? '-' : ''
  return `${sign}$${abs.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export default function DuplicateReviewModal({ duplicates, defaultAccountId, onComplete, onCancel }: DuplicateReviewModalProps) {
  const [decisions, setDecisions] = useState<Record<number, 'import' | 'skip'>>(() => {
    const init: Record<number, 'import' | 'skip'> = {}
    for (let i = 0; i < duplicates.length; i++) {
      init[i] = 'skip' // safe default
    }
    return init
  })
  const [submitting, setSubmitting] = useState(false)
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)

  const toggleDecision = (idx: number) => {
    setDecisions((d) => ({ ...d, [idx]: d[idx] === 'skip' ? 'import' : 'skip' }))
  }

  const setAll = (action: 'import' | 'skip') => {
    const updated: Record<number, 'import' | 'skip'> = {}
    for (let i = 0; i < duplicates.length; i++) {
      updated[i] = action
    }
    setDecisions(updated)
  }

  const handleSubmit = async () => {
    setSubmitting(true)
    try {
      const decisionList: DuplicateDecision[] = duplicates.map((dup, idx) => ({
        csv_row: dup.csv_row,
        account_id: dup.target_account_id || defaultAccountId,
        action: decisions[idx],
      }))
      const result = await csvImportApi.resolveDuplicates(decisionList)
      onComplete(result)
    } catch {
      setSubmitting(false)
    }
  }

  const importCount = Object.values(decisions).filter((d) => d === 'import').length
  const skipCount = Object.values(decisions).filter((d) => d === 'skip').length

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-white dark:bg-slate-900 rounded-xl shadow-xl w-full max-w-2xl mx-4 max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-700">
          <div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
              Review Suspected Duplicates
            </h2>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
              {duplicates.length} transaction{duplicates.length !== 1 ? 's' : ''} may already exist
            </p>
          </div>
          <button onClick={onCancel} className="p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors">
            <X className="w-5 h-5 text-slate-500 dark:text-slate-400" />
          </button>
        </div>

        {/* Bulk actions */}
        <div className="flex items-center gap-2 px-6 py-3 border-b border-slate-200 dark:border-slate-700">
          <button
            onClick={() => setAll('skip')}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
              skipCount === duplicates.length
                ? 'bg-red-600 text-white'
                : 'border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800'
            }`}
          >
            Skip All ({skipCount})
          </button>
          <button
            onClick={() => setAll('import')}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
              importCount === duplicates.length
                ? 'bg-emerald-600 text-white'
                : 'border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800'
            }`}
          >
            Import All ({importCount})
          </button>
        </div>

        {/* Duplicate list */}
        <div className="overflow-y-auto flex-1 px-6 py-3 space-y-3">
          {duplicates.map((dup, idx) => {
            const isExpanded = expandedIdx === idx
            const action = decisions[idx]

            return (
              <div
                key={idx}
                className={`border rounded-lg transition-colors ${
                  action === 'import'
                    ? 'border-emerald-300 dark:border-emerald-700 bg-emerald-50/50 dark:bg-emerald-950/20'
                    : 'border-slate-200 dark:border-slate-700'
                }`}
              >
                {/* Summary row */}
                <div className="flex items-center gap-3 px-4 py-3">
                  <button
                    onClick={() => setExpandedIdx(isExpanded ? null : idx)}
                    className="p-0.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
                  >
                    {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </button>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-slate-900 dark:text-slate-100 truncate">
                        {dup.csv_row.description}
                      </span>
                      <span className={`shrink-0 px-1.5 py-0.5 text-[10px] font-semibold uppercase rounded ${
                        dup.confidence === 'high'
                          ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
                          : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'
                      }`}>
                        {dup.confidence}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                      {dup.csv_row.date} &middot; {formatAmount(dup.csv_row.amount)}
                      {dup.target_account_name && <> &middot; {dup.target_account_name}</>}
                    </p>
                  </div>

                  <div className="shrink-0 flex gap-1.5">
                    <button
                      onClick={() => setDecisions((d) => ({ ...d, [idx]: 'skip' }))}
                      className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                        action === 'skip'
                          ? 'bg-red-500/20 text-red-600 dark:text-red-400 ring-1 ring-red-500/30'
                          : 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'
                      }`}
                    >
                      Skip
                    </button>
                    <button
                      onClick={() => setDecisions((d) => ({ ...d, [idx]: 'import' }))}
                      className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                        action === 'import'
                          ? 'bg-emerald-600 text-white'
                          : 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'
                      }`}
                    >
                      Import
                    </button>
                  </div>
                </div>

                {/* Expanded detail: side-by-side comparison */}
                {isExpanded && (
                  <div className="px-4 pb-4 pt-1 border-t border-slate-100 dark:border-slate-800">
                    <div className="grid grid-cols-2 gap-3">
                      {/* CSV version */}
                      <div className="p-3 bg-blue-50 dark:bg-blue-950/20 rounded-lg">
                        <p className="text-[10px] font-semibold uppercase text-blue-600 dark:text-blue-400 mb-2">From CSV</p>
                        <p className="text-sm text-slate-900 dark:text-slate-100 break-words">{dup.csv_row.description}</p>
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                          {dup.csv_row.date} &middot; {formatAmount(dup.csv_row.amount)}
                        </p>
                        {dup.csv_row.merchant_name && (
                          <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">Merchant: {dup.csv_row.merchant_name}</p>
                        )}
                      </div>

                      {/* Existing version */}
                      <div className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-lg">
                        <p className="text-[10px] font-semibold uppercase text-slate-500 dark:text-slate-400 mb-2">Already Exists</p>
                        <p className="text-sm text-slate-900 dark:text-slate-100 break-words">{dup.existing_transaction.description}</p>
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                          {dup.existing_transaction.date} &middot; {formatAmount(dup.existing_transaction.amount)}
                        </p>
                        {dup.existing_transaction.merchant_name && (
                          <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">Merchant: {dup.existing_transaction.merchant_name}</p>
                        )}
                        <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">Account: {dup.existing_transaction.account_name}</p>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-slate-200 dark:border-slate-700">
          <div className="flex items-center gap-3 text-xs text-slate-500 dark:text-slate-400">
            <span className="flex items-center gap-1">
              <AlertTriangle className="w-3.5 h-3.5" />
              {skipCount} skip
            </span>
            <span className="flex items-center gap-1">
              <Check className="w-3.5 h-3.5" />
              {importCount} import
            </span>
          </div>
          <div className="flex gap-3">
            <button
              onClick={onCancel}
              className="px-4 py-2 border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-300 text-sm font-medium rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={submitting}
              className="px-4 py-2 bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 text-sm font-medium rounded-lg hover:bg-slate-800 dark:hover:bg-slate-200 transition-colors disabled:opacity-50"
            >
              {submitting ? 'Submitting...' : 'Confirm Decisions'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

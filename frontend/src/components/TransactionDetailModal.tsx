import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { transactionsApi } from '../api/transactions'
import type { Transaction } from '../types'

// Keep in sync with VALID_CATEGORIES in backend/app/services/gemini_categorizer.py
const CATEGORIES = [
  'Groceries',
  'Restaurants',
  'Coffee & Drinks',
  'Shopping',
  'Entertainment',
  'Subscriptions',
  'Transportation',
  'Gas & Fuel',
  'Utilities',
  'Rent & Mortgage',
  'Insurance',
  'Healthcare',
  'Personal Care',
  'Education',
  'Travel',
  'Gifts & Donations',
  'Fees & Charges',
  'Other',
]

interface Props {
  transaction: Transaction
  onClose: () => void
}

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount)
}

export default function TransactionDetailModal({ transaction, onClose }: Props) {
  const [userCategory, setUserCategory] = useState(transaction.user_category || '')
  const [notes, setNotes] = useState(transaction.notes || '')
  const queryClient = useQueryClient()

  const hasChanges =
    (userCategory || null) !== (transaction.user_category || null) ||
    (notes || null) !== (transaction.notes || null)

  const mutation = useMutation({
    mutationFn: () =>
      transactionsApi.update(transaction.id, {
        user_category: userCategory || null,
        notes: notes || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transactions'] })
      queryClient.invalidateQueries({ queryKey: ['categories'] })
      queryClient.invalidateQueries({ queryKey: ['expense-transactions'] })
      queryClient.invalidateQueries({ queryKey: ['income-expenses'] })
      onClose()
    },
  })

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const categorySource = transaction.user_category
    ? 'manual'
    : transaction.category
      ? 'plaid'
      : transaction.ai_category
        ? 'ai'
        : 'none'

  const effectiveCategory =
    transaction.user_category || transaction.category || transaction.ai_category

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="bg-white dark:bg-slate-900 rounded-xl shadow-xl w-full max-w-lg mx-4 max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-700">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            Transaction Details
          </h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-slate-500 dark:text-slate-400" />
          </button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto px-6 py-4 space-y-4 flex-1">
          {/* Read-only details */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-0.5">Date</p>
              <p className="text-sm text-slate-900 dark:text-slate-100">{transaction.date}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-0.5">
                Amount
              </p>
              <p
                className={`text-sm font-semibold ${transaction.amount > 0 ? 'text-red-600' : 'text-emerald-600'}`}
              >
                {transaction.amount > 0 ? '-' : '+'}
                {formatCurrency(Math.abs(transaction.amount))}
              </p>
            </div>
          </div>

          {transaction.merchant_name && (
            <div>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-0.5">
                Merchant
              </p>
              <p className="text-sm text-slate-900 dark:text-slate-100">
                {transaction.merchant_name}
              </p>
            </div>
          )}

          <div>
            <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-0.5">
              Description
            </p>
            <p className="text-sm text-slate-900 dark:text-slate-100">{transaction.description}</p>
          </div>

          {transaction.is_pending && (
            <div className="px-2 py-1 bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-800 rounded-lg">
              <p className="text-xs text-amber-700 dark:text-amber-400 font-medium">Pending</p>
            </div>
          )}

          {/* Current category with provenance */}
          <div>
            <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">
              Current Category
            </p>
            <div className="flex items-center gap-2">
              <span className="text-sm text-slate-900 dark:text-slate-100">
                {effectiveCategory || 'Uncategorized'}
              </span>
              {categorySource === 'manual' && (
                <span className="text-[10px] px-1.5 py-0.5 bg-emerald-50 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400 rounded-full font-medium">
                  Manual
                </span>
              )}
              {categorySource === 'plaid' && (
                <span className="text-[10px] px-1.5 py-0.5 bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 rounded-full font-medium">
                  Plaid
                </span>
              )}
              {categorySource === 'ai' && (
                <span className="text-[10px] px-1.5 py-0.5 bg-purple-50 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400 rounded-full font-medium">
                  AI
                </span>
              )}
            </div>
          </div>

          {/* Editable: Override Category */}
          <div>
            <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">
              Override Category
            </label>
            <select
              value={userCategory}
              onChange={(e) => setUserCategory(e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
            >
              <option value="">
                Use default ({effectiveCategory && !transaction.user_category ? effectiveCategory : 'Uncategorized'})
              </option>
              {CATEGORIES.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>
          </div>

          {/* Editable: Notes */}
          <div>
            <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">
              Notes
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              placeholder="Add notes about this transaction..."
              className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 resize-none"
            />
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-slate-200 dark:border-slate-700">
          <button
            onClick={onClose}
            className="px-4 py-2 border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-300 text-sm font-medium rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => mutation.mutate()}
            disabled={!hasChanges || mutation.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white text-sm font-medium rounded-lg hover:bg-emerald-700 transition-colors disabled:opacity-50"
          >
            <Check className="w-4 h-4" />
            {mutation.isPending ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  )
}

import { Shield, X } from 'lucide-react'
import { useState } from 'react'
import { consentApi } from '../api/consent'

const CONSENT_VERSION = '1.0'
const CONSENT_TYPE = 'plaid_data_sharing'

const CONSENT_TEXT = `By connecting your bank account, you consent to FinanceHome accessing your financial data including account balances, transaction history, and account details through Plaid. This data is used to provide you with financial insights and budgeting tools. You can revoke this consent at any time by unlinking your account in Settings. Your data will be deleted upon request.`

interface ConsentModalProps {
  onConsent: () => void
  onCancel: () => void
}

export default function ConsentModal({ onConsent, onCancel }: ConsentModalProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleAgree = async () => {
    setLoading(true)
    setError('')
    try {
      await consentApi.grantConsent(CONSENT_TYPE, CONSENT_VERSION)
      onConsent()
    } catch {
      setError('Failed to record consent. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="fixed inset-0 bg-black/50" onClick={onCancel} />
      <div className="relative bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 shadow-xl max-w-md w-full p-6">
        <button
          onClick={onCancel}
          className="absolute top-4 right-4 p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded transition-colors"
        >
          <X className="w-4 h-4 text-slate-400" />
        </button>

        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 bg-emerald-50 dark:bg-emerald-900/30 rounded-lg">
            <Shield className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
          </div>
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            Data Sharing Consent
          </h2>
        </div>

        <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed mb-4">
          {CONSENT_TEXT}
        </p>

        <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-3 mb-4">
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-2">
            Data we access:
          </p>
          <ul className="text-xs text-slate-600 dark:text-slate-400 space-y-1">
            <li>- Account balances and details</li>
            <li>- Transaction history</li>
            <li>- Account and routing numbers (for identification only)</li>
          </ul>
        </div>

        {error && (
          <p className="text-sm text-red-600 dark:text-red-400 mb-4">{error}</p>
        )}

        <div className="flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 px-4 py-2.5 border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-300 rounded-lg text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleAgree}
            disabled={loading}
            className="flex-1 px-4 py-2.5 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 transition-colors disabled:opacity-50"
          >
            {loading ? 'Recording...' : 'I Agree'}
          </button>
        </div>

        <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-3 text-center">
          Consent version {CONSENT_VERSION}
        </p>
      </div>
    </div>
  )
}

export { CONSENT_TYPE }

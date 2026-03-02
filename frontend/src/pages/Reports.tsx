import { useMutation } from '@tanstack/react-query'
import { Download, FileText, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { reportsApi } from '../api/reports'

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

const currentYear = new Date().getFullYear()
const currentMonth = new Date().getMonth() + 1
const YEARS = Array.from({ length: currentYear - 2022 }, (_, i) => currentYear - i)

export default function Reports() {
  const [tab, setTab] = useState<'monthly' | 'annual'>('monthly')
  const [month, setMonth] = useState(currentMonth)
  const [monthYear, setMonthYear] = useState(currentYear)
  const [annualYear, setAnnualYear] = useState(currentYear)

  const monthlyMutation = useMutation({
    mutationFn: () => reportsApi.downloadMonthly(monthYear, month),
  })

  const annualMutation = useMutation({
    mutationFn: () => reportsApi.downloadAnnual(annualYear),
  })

  const isLoading = monthlyMutation.isPending || annualMutation.isPending

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 mb-6">Reports</h1>

      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 p-6">
        {/* Tab selector */}
        <div className="flex gap-1 bg-slate-100 dark:bg-slate-800 rounded-lg p-1 mb-6 w-fit">
          <button
            onClick={() => setTab('monthly')}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              tab === 'monthly'
                ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-sm'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100'
            }`}
          >
            Monthly
          </button>
          <button
            onClick={() => setTab('annual')}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              tab === 'annual'
                ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-sm'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100'
            }`}
          >
            Annual
          </button>
        </div>

        {/* Period selector */}
        <div className="flex flex-wrap items-end gap-4 mb-6">
          {tab === 'monthly' && (
            <>
              <div>
                <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Month</label>
                <select
                  value={month}
                  onChange={(e) => setMonth(Number(e.target.value))}
                  className="px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
                >
                  {MONTHS.map((name, i) => (
                    <option key={i} value={i + 1}>{name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Year</label>
                <select
                  value={monthYear}
                  onChange={(e) => setMonthYear(Number(e.target.value))}
                  className="px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
                >
                  {YEARS.map((y) => (
                    <option key={y} value={y}>{y}</option>
                  ))}
                </select>
              </div>
            </>
          )}

          {tab === 'annual' && (
            <div>
              <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Year</label>
              <select
                value={annualYear}
                onChange={(e) => setAnnualYear(Number(e.target.value))}
                className="px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
              >
                {YEARS.map((y) => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </select>
            </div>
          )}

          <button
            onClick={() => tab === 'monthly' ? monthlyMutation.mutate() : annualMutation.mutate()}
            disabled={isLoading}
            className="flex items-center gap-2 px-5 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 transition-colors disabled:opacity-50"
          >
            {isLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Download className="w-4 h-4" />
            )}
            {isLoading ? 'Generating...' : 'Download PDF'}
          </button>
        </div>

        {/* Report description */}
        <div className="border border-slate-200 dark:border-slate-700 rounded-lg p-4 bg-slate-50 dark:bg-slate-800">
          <div className="flex items-start gap-3">
            <FileText className="w-5 h-5 text-emerald-600 mt-0.5 flex-shrink-0" />
            <div>
              <p className="text-sm font-medium text-slate-900 dark:text-slate-100 mb-1">
                {tab === 'monthly'
                  ? `${MONTHS[month - 1]} ${monthYear} Report`
                  : `${annualYear} Annual Report`}
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {tab === 'monthly'
                  ? 'Includes income & expenses summary, spending by category, top merchants, and budget performance.'
                  : 'Includes everything in a monthly report plus a 12-month trend breakdown and annualized budget performance.'}
              </p>
            </div>
          </div>
        </div>

        {/* Error display */}
        {(monthlyMutation.isError || annualMutation.isError) && (
          <p className="mt-4 text-sm text-red-600 dark:text-red-400">
            Failed to generate report. Please try again.
          </p>
        )}
      </div>
    </div>
  )
}

import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, CreditCard, DollarSign, Lightbulb, Loader2, RefreshCw } from 'lucide-react'
import { useMemo, useState } from 'react'
import { recurringApi } from '../api/recurring'
import type { RecurringItem, RecurringSummary, SubscriptionInsights } from '../types'

const FREQUENCY_MULTIPLIERS: Record<string, number> = {
  weekly: 4.33,
  'bi-weekly': 2.17,
  monthly: 1.0,
  quarterly: 0.33,
  annual: 0.083,
}

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount)
}

function FrequencyBadge({ frequency }: { frequency: string }) {
  const colors: Record<string, string> = {
    weekly: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
    'bi-weekly': 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
    monthly: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
    quarterly: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
    annual: 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300',
  }
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${colors[frequency] || colors.monthly}`}>
      {frequency.charAt(0).toUpperCase() + frequency.slice(1)}
    </span>
  )
}

type CategoryGroup = {
  category: string
  items: RecurringItem[]
  monthlyTotal: number
}

export default function Subscriptions() {
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set())

  const { data: recurring, isLoading } = useQuery<RecurringSummary>({
    queryKey: ['recurring'],
    queryFn: recurringApi.getSummary,
  })

  const queryClient = useQueryClient()
  const [isRefreshing, setIsRefreshing] = useState(false)
  const { data: insights, isLoading: insightsLoading } = useQuery<SubscriptionInsights>({
    queryKey: ['subscription-insights'],
    queryFn: () => recurringApi.getInsights(),
    enabled: !!recurring?.items.length,
    staleTime: 1000 * 60 * 60,
  })

  const handleRefreshInsights = async () => {
    setIsRefreshing(true)
    try {
      const fresh = await recurringApi.getInsights(true)
      queryClient.setQueryData(['subscription-insights'], fresh)
    } finally {
      setIsRefreshing(false)
    }
  }

  const toggleCategory = (category: string) => {
    setExpandedCategories((prev) => {
      const next = new Set(prev)
      if (next.has(category)) next.delete(category)
      else next.add(category)
      return next
    })
  }

  const monthlyEquivalent = (item: RecurringItem) =>
    item.amount * (FREQUENCY_MULTIPLIERS[item.frequency] ?? 1.0)

  const groupedItems = useMemo((): CategoryGroup[] => {
    if (!recurring?.items.length) return []
    const groups: Record<string, RecurringItem[]> = {}
    for (const item of recurring.items) {
      if (!groups[item.category]) groups[item.category] = []
      groups[item.category].push(item)
    }
    return Object.entries(groups)
      .map(([category, items]) => ({
        category,
        items: items.sort((a, b) => monthlyEquivalent(b) - monthlyEquivalent(a)),
        monthlyTotal: items.reduce((sum, i) => sum + monthlyEquivalent(i), 0),
      }))
      .sort((a, b) => b.monthlyTotal - a.monthlyTotal)
  }, [recurring])

  const annualCost = (recurring?.total_monthly_cost ?? 0) * 12

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 mb-6">Subscriptions</h1>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 p-6">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-slate-500 dark:text-slate-400">Monthly Cost</span>
            <div className="w-10 h-10 rounded-lg flex items-center justify-center bg-emerald-500">
              <DollarSign className="w-5 h-5 text-white" />
            </div>
          </div>
          <p className="text-2xl font-bold text-slate-900 dark:text-slate-100">
            {formatCurrency(recurring?.total_monthly_cost ?? 0)}
          </p>
          <p className="text-xs text-slate-400 mt-1">
            {recurring?.items.length ?? 0} active subscriptions
          </p>
        </div>
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 p-6">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-slate-500 dark:text-slate-400">Annual Projection</span>
            <div className="w-10 h-10 rounded-lg flex items-center justify-center bg-blue-500">
              <CreditCard className="w-5 h-5 text-white" />
            </div>
          </div>
          <p className="text-2xl font-bold text-slate-900 dark:text-slate-100">
            {formatCurrency(annualCost)}
          </p>
          <p className="text-xs text-slate-400 mt-1">Projected yearly spend</p>
        </div>
      </div>

      {/* Subscriptions List */}
      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-700">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">All Subscriptions</h2>
        </div>

        {isLoading ? (
          <div className="p-8 text-center text-slate-500 dark:text-slate-400">
            Detecting recurring charges...
          </div>
        ) : groupedItems.length === 0 ? (
          <div className="p-8 text-center text-slate-500 dark:text-slate-400">
            Not enough transaction history to detect recurring charges yet.
          </div>
        ) : (
          <div>
            {/* Header */}
            <div className="hidden sm:grid grid-cols-12 gap-2 px-6 py-2 bg-slate-50 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700">
              <div className="col-span-4 text-xs font-medium text-slate-500 dark:text-slate-400 uppercase">Name</div>
              <div className="col-span-2 text-xs font-medium text-slate-500 dark:text-slate-400 uppercase">Amount</div>
              <div className="col-span-2 text-xs font-medium text-slate-500 dark:text-slate-400 uppercase">Frequency</div>
              <div className="col-span-2 text-xs font-medium text-slate-500 dark:text-slate-400 uppercase text-right">Monthly</div>
              <div className="col-span-2 text-xs font-medium text-slate-500 dark:text-slate-400 uppercase text-right">Last Charged</div>
            </div>

            {groupedItems.map((group) => {
              const isExpanded = expandedCategories.has(group.category)
              return (
                <div key={group.category}>
                  {/* Category header */}
                  <button
                    onClick={() => toggleCategory(group.category)}
                    className="w-full grid grid-cols-2 sm:grid-cols-12 gap-2 px-4 sm:px-6 py-3 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors border-b border-slate-100 dark:border-slate-800"
                  >
                    <div className="col-span-1 sm:col-span-4 flex items-center gap-2 text-left">
                      {isExpanded ? (
                        <ChevronDown className="w-4 h-4 text-slate-400 flex-shrink-0" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-slate-400 flex-shrink-0" />
                      )}
                      <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                        {group.category}
                      </span>
                      <span className="text-xs text-slate-400">{group.items.length}</span>
                    </div>
                    <div className="col-span-2 hidden sm:block" />
                    <div className="col-span-2 hidden sm:block" />
                    <div className="col-span-1 sm:col-span-2 text-sm font-semibold text-slate-900 dark:text-slate-100 text-right">
                      {formatCurrency(group.monthlyTotal)}
                    </div>
                    <div className="col-span-2 hidden sm:block" />
                  </button>

                  {/* Items */}
                  {isExpanded &&
                    group.items.map((item, i) => (
                      <div
                        key={i}
                        className="px-4 sm:px-6 sm:pl-12 py-3 bg-slate-50/50 dark:bg-slate-800/30 border-b border-slate-100 dark:border-slate-800"
                      >
                        {/* Mobile layout */}
                        <div className="sm:hidden pl-6">
                          <div className="flex items-center justify-between">
                            <div>
                              <p className="text-sm text-slate-900 dark:text-slate-100">{item.merchant}</p>
                              <div className="flex items-center gap-2 mt-0.5">
                                <FrequencyBadge frequency={item.frequency} />
                                <span className="text-xs text-slate-400">{item.last_date}</span>
                              </div>
                            </div>
                            <div className="text-right">
                              <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
                                {formatCurrency(monthlyEquivalent(item))}/mo
                              </p>
                              <p className="text-xs text-slate-500 dark:text-slate-400">
                                {formatCurrency(item.amount)}
                              </p>
                            </div>
                          </div>
                        </div>
                        {/* Desktop layout */}
                        <div className="hidden sm:grid grid-cols-12 gap-2">
                          <div className="col-span-4">
                            <p className="text-sm text-slate-900 dark:text-slate-100">{item.merchant}</p>
                            <p className="text-xs text-slate-400">{item.occurrence_count} charges detected</p>
                          </div>
                          <div className="col-span-2 flex items-center">
                            <span className="text-sm text-slate-700 dark:text-slate-300">
                              {formatCurrency(item.amount)}
                            </span>
                          </div>
                          <div className="col-span-2 flex items-center">
                            <FrequencyBadge frequency={item.frequency} />
                          </div>
                          <div className="col-span-2 flex items-center justify-end">
                            <span className="text-sm font-medium text-slate-900 dark:text-slate-100">
                              {formatCurrency(monthlyEquivalent(item))}
                            </span>
                          </div>
                          <div className="col-span-2 flex items-center justify-end">
                            <span className="text-xs text-slate-500 dark:text-slate-400">
                              {item.last_date}
                            </span>
                          </div>
                        </div>
                      </div>
                    ))}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Insights */}
      {recurring?.items.length ? (
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 p-6 mt-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-amber-100 dark:bg-amber-900/30">
                <Lightbulb className="w-4 h-4 text-amber-600 dark:text-amber-400" />
              </div>
              <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Subscription Insights</h2>
            </div>
            <button
              onClick={handleRefreshInsights}
              disabled={isRefreshing}
              className="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 flex items-center gap-1 transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`w-3 h-3 ${isRefreshing ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>

          {insightsLoading || isRefreshing ? (
            <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400 py-4">
              <Loader2 className="w-4 h-4 animate-spin" />
              Analyzing your subscriptions...
            </div>
          ) : insights?.insights.length ? (
            <ul className="space-y-3">
              {insights.insights.map((insight, i) => (
                <li key={i} className="flex gap-3 text-sm text-slate-700 dark:text-slate-300">
                  <span className="text-amber-500 mt-0.5 flex-shrink-0">&#x2022;</span>
                  <span>{insight}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-500 dark:text-slate-400">No insights available yet.</p>
          )}

          {insights?.generated_at && !isRefreshing && (
            <p className="text-xs text-slate-400 mt-4">
              Generated {new Date(insights.generated_at).toLocaleDateString()}
            </p>
          )}
        </div>
      ) : null}
    </div>
  )
}

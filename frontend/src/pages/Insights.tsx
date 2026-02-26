import { useMutation, useQuery } from '@tanstack/react-query'
import { format, startOfMonth, subMonths } from 'date-fns'
import {
  AlertTriangle,
  BarChart3,
  Lightbulb,
  MessageSquare,
  Send,
  Sparkles,
  TrendingUp,
} from 'lucide-react'
import { useState } from 'react'
import { insightsApi } from '../api/insights'
import type { Insight } from '../types'

const INSIGHT_TYPES = [
  { key: 'spending_summary', label: 'Spending Summary', icon: BarChart3 },
  { key: 'anomalies', label: 'Anomaly Detection', icon: AlertTriangle },
  { key: 'recommendations', label: 'Recommendations', icon: Lightbulb },
  { key: 'category_analysis', label: 'Category Analysis', icon: Sparkles },
  { key: 'forecast', label: 'Cash Flow Forecast', icon: TrendingUp },
]

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function InsightCard({ insight }: { insight: Insight }) {
  const content = insight.content as Record<string, any>

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <span className="text-xs px-2 py-1 bg-emerald-50 text-emerald-700 rounded-full font-medium">
          {insight.insight_type.replace(/_/g, ' ')}
        </span>
        <span className="text-xs text-slate-400">
          {insight.period_start} to {insight.period_end}
        </span>
      </div>

      {content.summary && (
        <p className="text-sm text-slate-700 mb-4">{String(content.summary)}</p>
      )}

      {content.highlights && Array.isArray(content.highlights) && (
        <ul className="space-y-1 mb-4">
          {(content.highlights as string[]).map((h, i) => (
            <li key={i} className="text-sm text-slate-600 flex items-start gap-2">
              <span className="text-emerald-500 mt-1">&#8226;</span>
              {h}
            </li>
          ))}
        </ul>
      )}

      {content.recommendations && Array.isArray(content.recommendations) && (
        <div className="space-y-3">
          {(content.recommendations as Array<Record<string, unknown>>).map((rec, i) => (
            <div key={i} className="p-3 bg-slate-50 rounded-lg">
              <p className="text-sm font-medium text-slate-900">{String(rec.title)}</p>
              <p className="text-xs text-slate-500 mt-1">{String(rec.description)}</p>
            </div>
          ))}
        </div>
      )}

      {content.anomalies && Array.isArray(content.anomalies) && (
        <div className="space-y-2">
          {(content.anomalies as Array<Record<string, unknown>>).map((a, i) => (
            <div key={i} className="flex items-start gap-2 p-2 bg-amber-50 rounded-lg">
              <AlertTriangle className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-sm text-slate-700">{String(a.description)}</p>
                <p className="text-xs text-slate-500">
                  {String(a.merchant)} &middot; ${String(a.amount)} &middot; {String(a.date)}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}

      {content.raw_response && (
        <p className="text-sm text-slate-700 whitespace-pre-wrap">{String(content.raw_response)}</p>
      )}
    </div>
  )
}

export default function Insights() {
  const [startDate, setStartDate] = useState(
    format(startOfMonth(subMonths(new Date(), 1)), 'yyyy-MM-dd'),
  )
  const [endDate, setEndDate] = useState(format(new Date(), 'yyyy-MM-dd'))
  const [question, setQuestion] = useState('')
  const [chatAnswer, setChatAnswer] = useState('')

  const { data: insights = [] } = useQuery<Insight[]>({
    queryKey: ['insights'],
    queryFn: () => insightsApi.list(),
  })

  const generateMutation = useMutation({
    mutationFn: (type: string) => insightsApi.generate(type, startDate, endDate),
  })

  const askMutation = useMutation({
    mutationFn: () => insightsApi.ask(question, startDate, endDate),
    onSuccess: (data) => {
      setChatAnswer(data.answer)
      setQuestion('')
    },
  })

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900 mb-6">AI Insights</h1>

      {/* Date Range & Generate */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 mb-6">
        <div className="flex flex-wrap gap-4 items-end mb-4">
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
        </div>
        <div className="flex flex-wrap gap-2">
          {INSIGHT_TYPES.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => generateMutation.mutate(key)}
              disabled={generateMutation.isPending}
              className="flex items-center gap-2 px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-100 transition-colors disabled:opacity-50"
            >
              <Icon className="w-4 h-4" />
              {label}
            </button>
          ))}
        </div>
        {generateMutation.isPending && (
          <p className="mt-3 text-sm text-emerald-600">Analyzing your finances with AI...</p>
        )}
      </div>

      {/* Ask a Question */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 mb-6">
        <h2 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
          <MessageSquare className="w-5 h-5 text-emerald-600" />
          Ask About Your Finances
        </h2>
        <div className="flex gap-2">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && question && askMutation.mutate()}
            placeholder="e.g., How much did I spend on dining out this month?"
            className="flex-1 px-3 py-2 border border-slate-300 rounded-lg text-sm"
          />
          <button
            onClick={() => askMutation.mutate()}
            disabled={!question || askMutation.isPending}
            className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 transition-colors disabled:opacity-50"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
        {askMutation.isPending && (
          <p className="mt-3 text-sm text-emerald-600">Thinking...</p>
        )}
        {chatAnswer && (
          <div className="mt-4 p-4 bg-slate-50 rounded-lg">
            <p className="text-sm text-slate-700 whitespace-pre-wrap">{chatAnswer}</p>
          </div>
        )}
      </div>

      {/* Generated Insight (most recent) */}
      {generateMutation.data && (
        <div className="mb-6">
          <h2 className="text-lg font-semibold text-slate-900 mb-3">Latest Insight</h2>
          <InsightCard insight={generateMutation.data} />
        </div>
      )}

      {/* Previous Insights */}
      {insights.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-slate-900 mb-3">Previous Insights</h2>
          <div className="space-y-4">
            {insights.map((insight) => (
              <InsightCard key={insight.id} insight={insight} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

import type { AIProvider } from '../hooks/useAIProvider'

interface Props {
  provider: AIProvider
  onChange: (provider: AIProvider) => void
}

export default function AIProviderToggle({ provider, onChange }: Props) {
  return (
    <div className="flex items-center gap-1 bg-slate-100 dark:bg-slate-800 rounded-lg p-0.5">
      <button
        onClick={() => onChange('gemini')}
        className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
          provider === 'gemini'
            ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-sm'
            : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300'
        }`}
      >
        Gemini
        <span className="ml-1 text-[10px] text-emerald-600">free</span>
      </button>
      <button
        onClick={() => onChange('anthropic')}
        className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
          provider === 'anthropic'
            ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-sm'
            : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300'
        }`}
      >
        Claude
        <span className="ml-1 text-[10px] text-amber-600">paid</span>
      </button>
    </div>
  )
}

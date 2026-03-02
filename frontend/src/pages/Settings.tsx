import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, CheckCircle, Mail, Send, Shield } from 'lucide-react'
import { useState } from 'react'
import { notificationsApi, type NotificationPreferences } from '../api/notifications'

const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

function Toggle({
  enabled,
  onChange,
}: {
  enabled: boolean
  onChange: (val: boolean) => void
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!enabled)}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
        enabled ? 'bg-emerald-600' : 'bg-slate-300 dark:bg-slate-600'
      }`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
          enabled ? 'translate-x-6' : 'translate-x-1'
        }`}
      />
    </button>
  )
}

export default function Settings() {
  const queryClient = useQueryClient()
  const [testStatus, setTestStatus] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle')

  const { data: prefs, isLoading } = useQuery({
    queryKey: ['notification-preferences'],
    queryFn: async () => {
      const { data } = await notificationsApi.getPreferences()
      return data
    },
  })

  const updateMutation = useMutation({
    mutationFn: (update: Partial<NotificationPreferences>) =>
      notificationsApi.updatePreferences(update),
    onSuccess: ({ data }) => {
      queryClient.setQueryData(['notification-preferences'], data)
    },
  })

  const testDigestMutation = useMutation({
    mutationFn: () => notificationsApi.sendTestDigest(),
    onMutate: () => setTestStatus('sending'),
    onSuccess: () => setTestStatus('sent'),
    onError: () => setTestStatus('error'),
  })

  const update = (field: keyof NotificationPreferences, value: boolean | string | number) => {
    updateMutation.mutate({ [field]: value })
  }

  if (isLoading) {
    return (
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 mb-6">Settings</h1>
        <div className="animate-pulse space-y-4">
          <div className="h-48 bg-slate-200 dark:bg-slate-800 rounded-xl" />
          <div className="h-48 bg-slate-200 dark:bg-slate-800 rounded-xl" />
        </div>
      </div>
    )
  }

  if (!prefs) return null

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 mb-6">Settings</h1>

      {/* Email Digest */}
      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 p-6 mb-6">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-4 flex items-center gap-2">
          <Mail className="w-5 h-5 text-emerald-600" />
          Weekly Email Digest
        </h2>
        <p className="text-sm text-slate-500 dark:text-slate-400 mb-5">
          Get a summary of your income, expenses, top categories, and budget status delivered to your inbox.
        </p>

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-slate-900 dark:text-slate-100">Enable weekly digest</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">Sent once a week with your financial summary</p>
            </div>
            <Toggle enabled={prefs.digest_enabled} onChange={(v) => update('digest_enabled', v)} />
          </div>

          {prefs.digest_enabled && (
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-900 dark:text-slate-100">Delivery day</p>
                <p className="text-xs text-slate-500 dark:text-slate-400">Which day to receive your digest</p>
              </div>
              <select
                value={prefs.digest_day}
                onChange={(e) => update('digest_day', e.target.value)}
                className="px-3 py-1.5 border border-slate-300 dark:border-slate-600 rounded-lg text-sm bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
              >
                {DAYS.map((d) => (
                  <option key={d} value={d}>
                    {d.charAt(0).toUpperCase() + d.slice(1)}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      </div>

      {/* Real-Time Alerts */}
      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 p-6 mb-6">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-4 flex items-center gap-2">
          <Bell className="w-5 h-5 text-emerald-600" />
          Real-Time Alerts
        </h2>
        <p className="text-sm text-slate-500 dark:text-slate-400 mb-5">
          Get notified immediately when important things happen with your finances.
        </p>

        <div className="space-y-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-slate-900 dark:text-slate-100">Budget exceeded</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">Alert when spending exceeds a category budget</p>
            </div>
            <Toggle
              enabled={prefs.alert_budget_exceeded}
              onChange={(v) => update('alert_budget_exceeded', v)}
            />
          </div>

          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-slate-900 dark:text-slate-100">Large transactions</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">Alert when a single transaction exceeds the threshold</p>
            </div>
            <Toggle
              enabled={prefs.alert_large_transaction}
              onChange={(v) => update('alert_large_transaction', v)}
            />
          </div>

          {prefs.alert_large_transaction && (
            <div className="flex items-center justify-between pl-4 border-l-2 border-emerald-200 dark:border-emerald-800">
              <div>
                <p className="text-sm font-medium text-slate-900 dark:text-slate-100">Threshold amount</p>
                <p className="text-xs text-slate-500 dark:text-slate-400">Transactions above this amount trigger an alert</p>
              </div>
              <div className="flex items-center gap-1">
                <span className="text-sm text-slate-500">$</span>
                <input
                  type="number"
                  min={1}
                  step={50}
                  value={prefs.alert_large_transaction_threshold}
                  onChange={(e) => {
                    const val = parseFloat(e.target.value)
                    if (val > 0) update('alert_large_transaction_threshold', val)
                  }}
                  className="w-24 px-3 py-1.5 border border-slate-300 dark:border-slate-600 rounded-lg text-sm bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 text-right"
                />
              </div>
            </div>
          )}

          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-slate-900 dark:text-slate-100">Spending anomalies</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">Alert when weekly spending in a category is unusually high</p>
            </div>
            <Toggle enabled={prefs.alert_anomaly} onChange={(v) => update('alert_anomaly', v)} />
          </div>
        </div>
      </div>

      {/* Test */}
      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 p-6 mb-6">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-4 flex items-center gap-2">
          <Shield className="w-5 h-5 text-emerald-600" />
          Test Notifications
        </h2>
        <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">
          Send yourself a test digest email to see how it looks.
        </p>
        <button
          onClick={() => testDigestMutation.mutate()}
          disabled={testStatus === 'sending'}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 transition-colors disabled:opacity-50"
        >
          {testStatus === 'sending' ? (
            <>
              <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              Sending...
            </>
          ) : testStatus === 'sent' ? (
            <>
              <CheckCircle className="w-4 h-4" />
              Sent!
            </>
          ) : (
            <>
              <Send className="w-4 h-4" />
              Send Test Digest
            </>
          )}
        </button>
        {testStatus === 'error' && (
          <p className="mt-2 text-sm text-red-600 dark:text-red-400">
            Failed to send. Make sure the Resend API key is configured.
          </p>
        )}
      </div>
    </div>
  )
}

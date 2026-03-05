import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Bell, CheckCircle, Copy, KeyRound, Mail, Send, Shield, ShieldCheck, ShieldOff, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { authApi } from '../api/auth'
import type { MFAConfirmResponse, MFASetupResponse } from '../api/auth'
import { notificationsApi, type NotificationPreferences } from '../api/notifications'
import { useAuth } from '../context/AuthContext'


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


function MFASection() {
  const queryClient = useQueryClient()
  const [setupStep, setSetupStep] = useState<'idle' | 'qr' | 'codes'>('idle')
  const [setupData, setSetupData] = useState<MFASetupResponse | null>(null)
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([])
  const [confirmCode, setConfirmCode] = useState('')
  const [disableCode, setDisableCode] = useState('')
  const [regenCode, setRegenCode] = useState('')
  const [error, setError] = useState('')
  const [showDisable, setShowDisable] = useState(false)
  const [showRegen, setShowRegen] = useState(false)
  const [copied, setCopied] = useState(false)

  const { data: mfaStatus, isLoading } = useQuery({
    queryKey: ['mfa-status'],
    queryFn: () => authApi.mfaStatus(),
  })

  const setupMutation = useMutation({
    mutationFn: () => authApi.mfaSetup(),
    onSuccess: (data) => {
      setSetupData(data)
      setSetupStep('qr')
      setError('')
    },
    onError: () => setError('Failed to start MFA setup'),
  })

  const confirmMutation = useMutation({
    mutationFn: (code: string) => authApi.mfaConfirm(code),
    onSuccess: (data: MFAConfirmResponse) => {
      setRecoveryCodes(data.recovery_codes)
      setSetupStep('codes')
      setConfirmCode('')
      setError('')
      queryClient.invalidateQueries({ queryKey: ['mfa-status'] })
    },
    onError: () => setError('Invalid code. Make sure your authenticator app is synced.'),
  })

  const disableMutation = useMutation({
    mutationFn: (code: string) => authApi.mfaDisable(code),
    onSuccess: () => {
      setShowDisable(false)
      setDisableCode('')
      setError('')
      queryClient.invalidateQueries({ queryKey: ['mfa-status'] })
    },
    onError: () => setError('Invalid code'),
  })

  const regenMutation = useMutation({
    mutationFn: (code: string) => authApi.mfaRegenerateCodes(code),
    onSuccess: (data: MFAConfirmResponse) => {
      setRecoveryCodes(data.recovery_codes)
      setShowRegen(false)
      setRegenCode('')
      setSetupStep('codes')
      setError('')
    },
    onError: () => setError('Invalid code'),
  })

  const copyRecoveryCodes = () => {
    navigator.clipboard.writeText(recoveryCodes.join('\n'))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 p-6 mb-6">
        <div className="animate-pulse h-24 bg-slate-200 dark:bg-slate-800 rounded" />
      </div>
    )
  }

  const enabled = mfaStatus?.mfa_enabled ?? false

  return (
    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 p-6 mb-6">
      <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-4 flex items-center gap-2">
        <Shield className="w-5 h-5 text-emerald-600" />
        Two-Factor Authentication
      </h2>

      {error && (
        <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 rounded-lg text-sm">
          {error}
        </div>
      )}

      {/* Recovery codes display (shared by setup + regenerate) */}
      {setupStep === 'codes' && recoveryCodes.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <KeyRound className="w-4 h-4 text-amber-600" />
            <p className="text-sm font-medium text-slate-900 dark:text-slate-100">Recovery Codes</p>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">
            Save these codes in a safe place. Each code can only be used once to sign in if you lose access to your authenticator.
          </p>
          <div className="grid grid-cols-2 gap-2 mb-4 p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
            {recoveryCodes.map((code) => (
              <code key={code} className="text-sm font-mono text-slate-700 dark:text-slate-300">
                {code}
              </code>
            ))}
          </div>
          <div className="flex gap-2">
            <button
              onClick={copyRecoveryCodes}
              className="flex items-center gap-2 px-3 py-1.5 border border-slate-300 dark:border-slate-600 rounded-lg text-sm hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
            >
              {copied ? <CheckCircle className="w-4 h-4 text-emerald-600" /> : <Copy className="w-4 h-4" />}
              {copied ? 'Copied!' : 'Copy all codes'}
            </button>
            <button
              onClick={() => { setSetupStep('idle'); setRecoveryCodes([]) }}
              className="px-3 py-1.5 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 transition-colors"
            >
              I've saved my codes
            </button>
          </div>
        </div>
      )}

      {/* QR code setup step */}
      {setupStep === 'qr' && setupData && (
        <div>
          <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">
            Scan this QR code with your authenticator app (Google Authenticator, 1Password, Authy, etc.)
          </p>
          <div className="flex justify-center mb-4">
            <img src={setupData.qr_code_data_uri} alt="MFA QR Code" className="w-48 h-48 rounded-lg" />
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mb-1 text-center">Or enter this key manually:</p>
          <p className="text-xs font-mono text-center text-slate-600 dark:text-slate-300 mb-4 select-all">
            {setupData.secret}
          </p>

          <form
            onSubmit={(e) => { e.preventDefault(); confirmMutation.mutate(confirmCode) }}
            className="flex gap-2"
          >
            <input
              type="text"
              value={confirmCode}
              onChange={(e) => setConfirmCode(e.target.value)}
              maxLength={6}
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="6-digit code"
              className="flex-1 px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm text-center tracking-widest bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
            <button
              type="submit"
              disabled={confirmMutation.isPending || confirmCode.length < 6}
              className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 transition-colors disabled:opacity-50"
            >
              {confirmMutation.isPending ? 'Verifying...' : 'Confirm'}
            </button>
          </form>
          <button
            onClick={() => { setSetupStep('idle'); setSetupData(null); setError('') }}
            className="mt-3 text-sm text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
          >
            Cancel
          </button>
        </div>
      )}

      {/* Idle states */}
      {setupStep === 'idle' && !enabled && (
        <div>
          <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">
            Add an extra layer of security to your account by requiring a code from your authenticator app when signing in.
          </p>
          <button
            onClick={() => { setError(''); setupMutation.mutate() }}
            disabled={setupMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 transition-colors disabled:opacity-50"
          >
            <ShieldCheck className="w-4 h-4" />
            {setupMutation.isPending ? 'Setting up...' : 'Enable Two-Factor Authentication'}
          </button>
        </div>
      )}

      {setupStep === 'idle' && enabled && (
        <div>
          <div className="flex items-center gap-2 mb-4 p-3 bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 rounded-lg">
            <ShieldCheck className="w-5 h-5 text-emerald-600" />
            <div>
              <p className="text-sm font-medium text-emerald-700 dark:text-emerald-400">Two-factor authentication is enabled</p>
              {mfaStatus?.mfa_enabled_at && (
                <p className="text-xs text-emerald-600 dark:text-emerald-500">
                  Enabled {new Date(mfaStatus.mfa_enabled_at).toLocaleDateString()}
                </p>
              )}
            </div>
          </div>

          <div className="flex gap-2">
            {!showRegen && !showDisable && (
              <>
                <button
                  onClick={() => { setShowRegen(true); setShowDisable(false); setError('') }}
                  className="flex items-center gap-2 px-3 py-1.5 border border-slate-300 dark:border-slate-600 rounded-lg text-sm hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                >
                  <KeyRound className="w-4 h-4" />
                  Regenerate Recovery Codes
                </button>
                <button
                  onClick={() => { setShowDisable(true); setShowRegen(false); setError('') }}
                  className="flex items-center gap-2 px-3 py-1.5 border border-red-300 dark:border-red-800 text-red-600 dark:text-red-400 rounded-lg text-sm hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                >
                  <ShieldOff className="w-4 h-4" />
                  Disable 2FA
                </button>
              </>
            )}
          </div>

          {/* Disable MFA form */}
          {showDisable && (
            <form
              onSubmit={(e) => { e.preventDefault(); disableMutation.mutate(disableCode) }}
              className="mt-3"
            >
              <p className="text-sm text-slate-500 dark:text-slate-400 mb-2">Enter your authenticator code to disable 2FA:</p>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={disableCode}
                  onChange={(e) => setDisableCode(e.target.value)}
                  maxLength={6}
                  inputMode="numeric"
                  placeholder="6-digit code"
                  className="flex-1 px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm text-center tracking-widest bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-red-500"
                />
                <button
                  type="submit"
                  disabled={disableMutation.isPending || disableCode.length < 6}
                  className="px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 transition-colors disabled:opacity-50"
                >
                  {disableMutation.isPending ? 'Disabling...' : 'Disable'}
                </button>
                <button
                  type="button"
                  onClick={() => { setShowDisable(false); setDisableCode(''); setError('') }}
                  className="px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </form>
          )}

          {/* Regenerate codes form */}
          {showRegen && (
            <form
              onSubmit={(e) => { e.preventDefault(); regenMutation.mutate(regenCode) }}
              className="mt-3"
            >
              <p className="text-sm text-slate-500 dark:text-slate-400 mb-2">Enter your authenticator code to regenerate recovery codes:</p>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={regenCode}
                  onChange={(e) => setRegenCode(e.target.value)}
                  maxLength={6}
                  inputMode="numeric"
                  placeholder="6-digit code"
                  className="flex-1 px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm text-center tracking-widest bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
                <button
                  type="submit"
                  disabled={regenMutation.isPending || regenCode.length < 6}
                  className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 transition-colors disabled:opacity-50"
                >
                  {regenMutation.isPending ? 'Generating...' : 'Regenerate'}
                </button>
                <button
                  type="button"
                  onClick={() => { setShowRegen(false); setRegenCode(''); setError('') }}
                  className="px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </form>
          )}
        </div>
      )}
    </div>
  )
}


function DeleteAccountSection() {
  const { deleteAccount } = useAuth()
  const navigate = useNavigate()
  const [showConfirm, setShowConfirm] = useState(false)
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [deleting, setDeleting] = useState(false)

  const handleDelete = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setDeleting(true)
    try {
      await deleteAccount(password)
      navigate('/login')
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to delete account'
      setError(message)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="bg-white dark:bg-slate-900 rounded-xl border border-red-200 dark:border-red-900 p-6 mb-6">
      <h2 className="text-lg font-semibold text-red-600 dark:text-red-400 mb-4 flex items-center gap-2">
        <Trash2 className="w-5 h-5" />
        Delete Account
      </h2>

      {error && (
        <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 rounded-lg text-sm">
          {error}
        </div>
      )}

      {!showConfirm ? (
        <div>
          <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">
            Permanently delete your account and all associated data including linked bank accounts, transactions, budgets, and settings. This action cannot be undone.
          </p>
          <button
            onClick={() => setShowConfirm(true)}
            className="flex items-center gap-2 px-4 py-2 border border-red-300 dark:border-red-800 text-red-600 dark:text-red-400 rounded-lg text-sm font-medium hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
          >
            <Trash2 className="w-4 h-4" />
            Delete my account
          </button>
        </div>
      ) : (
        <form onSubmit={handleDelete}>
          <div className="flex items-start gap-3 mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
            <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400 mt-0.5 shrink-0" />
            <div className="text-sm text-red-700 dark:text-red-400">
              <p className="font-medium mb-1">This will permanently delete:</p>
              <ul className="list-disc list-inside space-y-0.5 text-xs">
                <li>All linked bank accounts and Plaid connections</li>
                <li>All transactions and categorization data</li>
                <li>Budgets, insights, and notification preferences</li>
                <li>Your account and login credentials</li>
              </ul>
            </div>
          </div>

          <p className="text-sm text-slate-500 dark:text-slate-400 mb-2">Enter your password to confirm:</p>
          <div className="flex gap-2">
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Your password"
              required
              className="flex-1 px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-red-500"
            />
            <button
              type="submit"
              disabled={deleting || !password}
              className="px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 transition-colors disabled:opacity-50"
            >
              {deleting ? 'Deleting...' : 'Confirm Delete'}
            </button>
            <button
              type="button"
              onClick={() => { setShowConfirm(false); setPassword(''); setError('') }}
              className="px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>
      )}
    </div>
  )
}


export default function Settings() {
  const { isDemo } = useAuth()
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

      {/* Two-Factor Authentication (hidden for demo users) */}
      {!isDemo && <MFASection />}

      {/* Email Digest */}
      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 p-6 mb-6">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-4 flex items-center gap-2">
          <Mail className="w-5 h-5 text-emerald-600" />
          Daily Email Digest
        </h2>
        <p className="text-sm text-slate-500 dark:text-slate-400 mb-5">
          Get a daily summary of your spending, top categories, and budget status delivered to your inbox.
        </p>

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-slate-900 dark:text-slate-100">Enable daily digest</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">Sent every day with your financial summary</p>
            </div>
            <Toggle enabled={prefs.digest_enabled} onChange={(v) => update('digest_enabled', v)} />
          </div>

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
          <Send className="w-5 h-5 text-emerald-600" />
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

      {/* Delete Account (hidden for demo users) */}
      {!isDemo && <DeleteAccountSection />}
    </div>
  )
}

import client from './client'

export interface NotificationPreferences {
  digest_enabled: boolean
  digest_day: string
  alert_budget_exceeded: boolean
  alert_large_transaction: boolean
  alert_large_transaction_threshold: number
  alert_anomaly: boolean
}

export const notificationsApi = {
  getPreferences: () => client.get<NotificationPreferences>('/notifications/preferences'),

  updatePreferences: (prefs: Partial<NotificationPreferences>) =>
    client.put<NotificationPreferences>('/notifications/preferences', prefs),

  sendTestDigest: () => client.post<{ message: string; to: string }>('/notifications/test-digest'),
}

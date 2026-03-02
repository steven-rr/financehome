import client from './client'
import type { RecurringSummary, SubscriptionInsights } from '../types'

export const recurringApi = {
  getSummary: async (): Promise<RecurringSummary> => {
    const { data } = await client.get('/recurring')
    return data
  },

  getInsights: async (refresh = false): Promise<SubscriptionInsights> => {
    const { data } = await client.get(`/recurring/insights${refresh ? '?refresh=true' : ''}`)
    return data
  },
}

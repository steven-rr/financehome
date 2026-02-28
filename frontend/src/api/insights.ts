import client from './client'
import type { Insight } from '../types'

export const insightsApi = {
  generate: async (
    insightType: string,
    startDate: string,
    endDate: string,
    provider: string = 'gemini',
  ): Promise<Insight> => {
    const { data } = await client.post('/insights/generate', {
      insight_type: insightType,
      start_date: startDate,
      end_date: endDate,
      provider,
    })
    return data
  },

  list: async (insightType?: string): Promise<Insight[]> => {
    const params = insightType ? `?insight_type=${insightType}` : ''
    const { data } = await client.get(`/insights${params}`)
    return data
  },

  spendingInsights: async (): Promise<{ insights: string[]; generated_at: string }> => {
    const { data } = await client.get('/insights/spending-insights')
    return data
  },

  ask: async (
    question: string,
    startDate?: string,
    endDate?: string,
    provider: string = 'gemini',
  ): Promise<{ answer: string }> => {
    const { data } = await client.post('/insights/ask', {
      question,
      start_date: startDate,
      end_date: endDate,
      provider,
    })
    return data
  },
}

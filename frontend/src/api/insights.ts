import client from './client'
import type { Insight } from '../types'

export const insightsApi = {
  generate: async (
    insightType: string,
    startDate: string,
    endDate: string,
  ): Promise<Insight> => {
    const { data } = await client.post('/insights/generate', {
      insight_type: insightType,
      start_date: startDate,
      end_date: endDate,
    })
    return data
  },

  list: async (insightType?: string): Promise<Insight[]> => {
    const params = insightType ? `?insight_type=${insightType}` : ''
    const { data } = await client.get(`/insights${params}`)
    return data
  },

  ask: async (
    question: string,
    startDate?: string,
    endDate?: string,
  ): Promise<{ answer: string }> => {
    const { data } = await client.post('/insights/ask', {
      question,
      start_date: startDate,
      end_date: endDate,
    })
    return data
  },
}

import client from './client'
import type { Budget } from '../types'

export const budgetsApi = {
  list: async (): Promise<Budget[]> => {
    const { data } = await client.get('/budgets')
    return data
  },

  upsert: async (category: string, monthly_limit: number): Promise<Budget> => {
    const { data } = await client.put('/budgets', { category, monthly_limit })
    return data
  },

  delete: async (category: string): Promise<void> => {
    await client.delete(`/budgets/${encodeURIComponent(category)}`)
  },
}

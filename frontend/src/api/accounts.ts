import client from './client'
import type { Account } from '../types'

export const accountsApi = {
  list: async (): Promise<Account[]> => {
    const { data } = await client.get('/accounts')
    return data
  },

  get: async (id: string): Promise<Account> => {
    const { data } = await client.get(`/accounts/${id}`)
    return data
  },

  sync: async (): Promise<{ synced_accounts: number }> => {
    const { data } = await client.post('/accounts/sync')
    return data
  },
}

import client from './client'
import type { RecurringSummary } from '../types'

export const recurringApi = {
  getSummary: async (): Promise<RecurringSummary> => {
    const { data } = await client.get('/recurring')
    return data
  },
}

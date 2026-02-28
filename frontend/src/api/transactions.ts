import client from './client'
import type { CategorySummary, ExpenseTransaction, IncomeExpenseSummary, IncomeTransaction, MonthlyTrend, PaginatedTransactions, Transaction, TransactionFilters } from '../types'

export const transactionsApi = {
  list: async (filters: TransactionFilters): Promise<PaginatedTransactions> => {
    const params = new URLSearchParams()
    if (filters.start_date) params.append('start_date', filters.start_date)
    if (filters.end_date) params.append('end_date', filters.end_date)
    if (filters.account_id) params.append('account_id', filters.account_id)
    if (filters.category) params.append('category', filters.category)
    if (filters.search) params.append('search', filters.search)
    if (filters.page) params.append('page', String(filters.page))
    if (filters.per_page) params.append('per_page', String(filters.per_page))

    const { data } = await client.get(`/transactions?${params.toString()}`)
    return data
  },

  categories: async (startDate?: string, endDate?: string): Promise<CategorySummary[]> => {
    const params = new URLSearchParams()
    if (startDate) params.append('start_date', startDate)
    if (endDate) params.append('end_date', endDate)

    const { data } = await client.get(`/transactions/categories?${params.toString()}`)
    return data
  },

  expenseTransactions: async (startDate?: string, endDate?: string): Promise<ExpenseTransaction[]> => {
    const params = new URLSearchParams()
    if (startDate) params.append('start_date', startDate)
    if (endDate) params.append('end_date', endDate)

    const { data } = await client.get(`/transactions/expenses?${params.toString()}`)
    return data
  },

  incomeTransactions: async (startDate?: string, endDate?: string): Promise<IncomeTransaction[]> => {
    const params = new URLSearchParams()
    if (startDate) params.append('start_date', startDate)
    if (endDate) params.append('end_date', endDate)

    const { data } = await client.get(`/transactions/income?${params.toString()}`)
    return data
  },

  incomeExpenses: async (startDate?: string, endDate?: string): Promise<IncomeExpenseSummary> => {
    const params = new URLSearchParams()
    if (startDate) params.append('start_date', startDate)
    if (endDate) params.append('end_date', endDate)

    const { data } = await client.get(`/transactions/income-expenses?${params.toString()}`)
    return data
  },

  monthlyTrend: async (months: number = 6): Promise<MonthlyTrend[]> => {
    const { data } = await client.get(`/transactions/monthly-trend?months=${months}`)
    return data
  },

  categorize: async (provider: string = 'gemini'): Promise<{ categorized: number; total_uncategorized: number }> => {
    const { data } = await client.post('/categorize/run', { provider })
    return data
  },

  update: async (id: string, body: { user_category?: string | null; notes?: string | null }): Promise<Transaction> => {
    const { data } = await client.patch(`/transactions/${id}`, body)
    return data
  },
}

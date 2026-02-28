export interface Account {
  id: string
  plaid_account_id: string
  name: string
  official_name: string | null
  type: string
  subtype: string | null
  balance_current: number | null
  balance_available: number | null
  currency: string
  institution_name: string | null
}

export interface Transaction {
  id: string
  account_id: string
  date: string
  amount: number
  merchant_name: string | null
  description: string
  category: string | null
  subcategory: string | null
  ai_category: string | null
  is_pending: boolean
}

export interface PaginatedTransactions {
  items: Transaction[]
  total: number
  page: number
  per_page: number
  pages: number
}

export interface TransactionFilters {
  start_date?: string
  end_date?: string
  account_id?: string
  category?: string
  search?: string
  page?: number
  per_page?: number
}

export interface CategorySummary {
  category: string
  total: number
  count: number
}

export interface IncomeExpenseSummary {
  income: number
  expenses: number
  net: number
}

export interface IncomeTransaction {
  date: string
  description: string
  merchant_name: string | null
  amount: number
}

export interface ExpenseTransaction {
  date: string
  description: string
  merchant_name: string | null
  amount: number
  category: string
}

export interface Insight {
  id: string
  insight_type: string
  period_start: string
  period_end: string
  content: Record<string, unknown>
  generated_at: string
}

export interface MonthlyTrend {
  month: string
  income: number
  expenses: number
  net: number
}

export interface RecurringItem {
  merchant: string
  amount: number
  frequency: string
  category: string
  confidence: number
  last_date: string
  occurrence_count: number
}

export interface RecurringSummary {
  total_monthly_cost: number
  items: RecurringItem[]
}

export interface Budget {
  id: string
  category: string
  monthly_limit: number
}

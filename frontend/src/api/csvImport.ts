import client from './client'

export interface SuspectedDuplicate {
  csv_row: {
    date: string
    amount: number
    description: string
    merchant_name: string | null
    category: string | null
  }
  existing_transaction: {
    id: string
    date: string
    amount: number
    description: string
    merchant_name: string | null
    account_name: string
  }
  confidence: 'high' | 'low'
  target_account_id?: string
  target_account_name?: string
}

export interface ImportResult {
  imported: number
  skipped: number
  suspected_duplicates: SuspectedDuplicate[]
  account_id: string
  total_in_file: number
}

export interface BulkImportFileResult {
  file: string
  account?: string
  imported?: number
  skipped?: number
  suspected_duplicates?: number
  total_in_file?: number
  error?: string
}

export interface BulkImportResult {
  imported: number
  skipped: number
  suspected_duplicates: SuspectedDuplicate[]
  total_in_files: number
  files: BulkImportFileResult[]
}

export interface DuplicateDecision {
  csv_row: {
    date: string
    amount: number
    description: string
    merchant_name?: string | null
    category?: string | null
  }
  account_id: string
  action: 'import' | 'skip'
}

export const csvImportApi = {
  async importTransactions(file: File, accountName: string = 'Apple Card'): Promise<ImportResult> {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('account_name', accountName)

    const { data } = await client.post('/import/transactions', formData)
    return data
  },

  async importBulk(formData: FormData): Promise<BulkImportResult> {
    const { data } = await client.post('/import/transactions/bulk', formData)
    return data
  },

  async resolveDuplicates(decisions: DuplicateDecision[]): Promise<{ imported: number; skipped: number }> {
    const { data } = await client.post('/import/transactions/resolve-duplicates', { decisions })
    return data
  },
}

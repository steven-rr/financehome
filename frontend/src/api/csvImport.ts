import client from './client'

interface ImportResult {
  imported: number
  skipped: number
  total_in_file: number
}

interface BulkImportFileResult {
  file: string
  account?: string
  imported?: number
  skipped?: number
  total_in_file?: number
  error?: string
}

interface BulkImportResult {
  imported: number
  skipped: number
  total_in_files: number
  files: BulkImportFileResult[]
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
}

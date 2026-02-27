import client from './client'

interface ImportResult {
  imported: number
  skipped: number
  total_in_file: number
}

export const csvImportApi = {
  async importTransactions(file: File, accountName: string = 'Apple Card'): Promise<ImportResult> {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('account_name', accountName)

    const { data } = await client.post('/import/transactions', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },
}

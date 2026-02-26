import client from './client'

export const exportApi = {
  async downloadTransactions(startDate?: string, endDate?: string) {
    const params = new URLSearchParams()
    if (startDate) params.append('start_date', startDate)
    if (endDate) params.append('end_date', endDate)

    const { data } = await client.get(`/export/transactions?${params.toString()}`, {
      responseType: 'blob',
    })

    const url = window.URL.createObjectURL(new Blob([data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `transactions_${startDate || 'all'}_${endDate || 'all'}.csv`)
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  },
}

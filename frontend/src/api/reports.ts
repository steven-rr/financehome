import client from './client'

export const reportsApi = {
  downloadMonthly: async (year: number, month: number): Promise<void> => {
    const { data } = await client.get(`/reports/monthly?year=${year}&month=${month}`, {
      responseType: 'blob',
    })
    const url = URL.createObjectURL(data)
    const a = document.createElement('a')
    a.href = url
    a.download = `report-${year}-${String(month).padStart(2, '0')}.pdf`
    a.click()
    URL.revokeObjectURL(url)
  },

  downloadAnnual: async (year: number): Promise<void> => {
    const { data } = await client.get(`/reports/annual?year=${year}`, {
      responseType: 'blob',
    })
    const url = URL.createObjectURL(data)
    const a = document.createElement('a')
    a.href = url
    a.download = `report-${year}-annual.pdf`
    a.click()
    URL.revokeObjectURL(url)
  },
}

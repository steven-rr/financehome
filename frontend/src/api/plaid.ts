import client from './client'

export const plaidApi = {
  createLinkToken: async (): Promise<string> => {
    const { data } = await client.post('/plaid/link-token')
    return data.link_token
  },

  exchangeToken: async (publicToken: string): Promise<{ institution_name: string; accounts_linked: number }> => {
    const { data } = await client.post('/plaid/exchange-token', { public_token: publicToken })
    return data
  },
}

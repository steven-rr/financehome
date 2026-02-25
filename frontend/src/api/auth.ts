import client from './client'

interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export const authApi = {
  login: async (email: string, password: string): Promise<TokenResponse> => {
    const { data } = await client.post('/auth/login', { email, password })
    return data
  },

  register: async (email: string, password: string): Promise<TokenResponse> => {
    const { data } = await client.post('/auth/register', { email, password })
    return data
  },

  getMe: async () => {
    const { data } = await client.get('/auth/me')
    return data
  },
}

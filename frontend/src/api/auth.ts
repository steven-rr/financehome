import client from './client'

interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface LoginResponse {
  access_token?: string
  refresh_token?: string
  token_type: string
  mfa_required: boolean
  mfa_token?: string
}

export interface MFASetupResponse {
  secret: string
  qr_code_data_uri: string
}

export interface MFAConfirmResponse {
  recovery_codes: string[]
}

export interface MFAStatusResponse {
  mfa_enabled: boolean
  mfa_enabled_at: string | null
}

export const authApi = {
  login: async (email: string, password: string): Promise<LoginResponse> => {
    const { data } = await client.post('/auth/login', { email, password })
    return data
  },

  register: async (email: string, password: string): Promise<TokenResponse> => {
    const { data } = await client.post('/auth/register', { email, password })
    return data
  },

  demoLogin: async (): Promise<TokenResponse> => {
    const { data } = await client.post('/auth/demo')
    return data
  },

  getMe: async () => {
    const { data } = await client.get('/auth/me')
    return data
  },

  githubAuthorize: async (): Promise<{ url: string; state: string }> => {
    const { data } = await client.get('/auth/github/authorize')
    return data
  },

  githubCallback: async (code: string): Promise<LoginResponse> => {
    const { data } = await client.post('/auth/github/callback', { code })
    return data
  },

  // MFA
  mfaStatus: async (): Promise<MFAStatusResponse> => {
    const { data } = await client.get('/auth/mfa/status')
    return data
  },

  mfaSetup: async (): Promise<MFASetupResponse> => {
    const { data } = await client.post('/auth/mfa/setup')
    return data
  },

  mfaConfirm: async (code: string): Promise<MFAConfirmResponse> => {
    const { data } = await client.post('/auth/mfa/confirm', { code })
    return data
  },

  mfaVerify: async (mfaToken: string, code: string): Promise<LoginResponse> => {
    const { data } = await client.post('/auth/mfa/verify', { mfa_token: mfaToken, code })
    return data
  },

  mfaDisable: async (code: string): Promise<void> => {
    await client.post('/auth/mfa/disable', { code })
  },

  mfaRegenerateCodes: async (code: string): Promise<MFAConfirmResponse> => {
    const { data } = await client.post('/auth/mfa/recovery-codes/regenerate', { code })
    return data
  },
}

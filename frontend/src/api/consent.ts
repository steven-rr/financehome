import client from './client'

export interface ConsentRecord {
  id: string
  consent_type: string
  consent_version: string
  granted_at: string
  revoked_at: string | null
}

export interface ConsentStatus {
  has_consent: boolean
  consent: ConsentRecord | null
}

export const consentApi = {
  grantConsent: async (consentType: string, consentVersion: string): Promise<ConsentRecord> => {
    const { data } = await client.post('/consent/grant', {
      consent_type: consentType,
      consent_version: consentVersion,
    })
    return data
  },

  revokeConsent: async (consentId: string): Promise<void> => {
    await client.post('/consent/revoke', { consent_id: consentId })
  },

  getConsentStatus: async (consentType: string): Promise<ConsentStatus> => {
    const { data } = await client.get('/consent/status', {
      params: { consent_type: consentType },
    })
    return data
  },

  getConsentHistory: async (): Promise<ConsentRecord[]> => {
    const { data } = await client.get('/consent/history')
    return data
  },
}

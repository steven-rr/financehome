import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { usePlaidLink } from 'react-plaid-link'
import { plaidApi } from '../api/plaid'

export default function OAuthCallback() {
  const navigate = useNavigate()
  const [linkToken, setLinkToken] = useState<string | null>(null)

  useEffect(() => {
    const stored = localStorage.getItem('plaid_link_token')
    if (stored) {
      setLinkToken(stored)
    } else {
      navigate('/accounts')
    }
  }, [navigate])

  const onSuccess = useCallback(
    async (publicToken: string) => {
      await plaidApi.exchangeToken(publicToken)
      localStorage.removeItem('plaid_link_token')
      navigate('/accounts')
    },
    [navigate],
  )

  const { open, ready } = usePlaidLink({
    token: linkToken,
    onSuccess,
    receivedRedirectUri: window.location.href,
  })

  useEffect(() => {
    if (ready) open()
  }, [ready, open])

  return (
    <div className="flex items-center justify-center min-h-screen">
      <p className="text-slate-500">Completing bank connection...</p>
    </div>
  )
}

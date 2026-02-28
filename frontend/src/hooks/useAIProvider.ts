import { useState } from 'react'

export type AIProvider = 'gemini' | 'anthropic'

export function useAIProvider() {
  const [provider, setProviderState] = useState<AIProvider>(
    () => (localStorage.getItem('ai_provider') as AIProvider) || 'gemini',
  )

  const setProvider = (p: AIProvider) => {
    localStorage.setItem('ai_provider', p)
    setProviderState(p)
  }

  return { provider, setProvider }
}

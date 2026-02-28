import { X } from 'lucide-react'
import { useState } from 'react'
import type { Account } from '../types'

interface AccountMapping {
  account_id?: string
  new_name?: string
}

export type AccountMappings = Record<string, AccountMapping>

interface ImportModalProps {
  files: File[]
  accounts: Account[]
  onConfirm: (mappings: AccountMappings) => void
  onCancel: () => void
}

export default function ImportModal({ files, accounts, onConfirm, onCancel }: ImportModalProps) {
  const [selections, setSelections] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {}
    for (const f of files) {
      init[f.name] = 'new'
    }
    return init
  })

  const [customNames, setCustomNames] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {}
    for (const f of files) {
      init[f.name] = f.name.replace(/\.[^.]+$/, '')
    }
    return init
  })

  const handleConfirm = () => {
    const mappings: AccountMappings = {}
    for (const f of files) {
      const sel = selections[f.name]
      if (sel === 'new') {
        mappings[f.name] = { new_name: customNames[f.name] }
      } else {
        mappings[f.name] = { account_id: sel }
      }
    }
    onConfirm(mappings)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg mx-4 max-h-[80vh] flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
          <h2 className="text-lg font-semibold text-slate-900">Import CSV Files</h2>
          <button onClick={onCancel} className="p-1 hover:bg-slate-100 rounded-lg transition-colors">
            <X className="w-5 h-5 text-slate-500" />
          </button>
        </div>

        <div className="overflow-y-auto px-6 py-4 space-y-4 flex-1">
          <p className="text-sm text-slate-500">Choose which account each file should import into.</p>

          {files.map((f) => (
            <div key={f.name} className="border border-slate-200 rounded-lg p-4 space-y-2">
              <p className="text-sm font-medium text-slate-900 truncate">{f.name}</p>
              <select
                value={selections[f.name]}
                onChange={(e) =>
                  setSelections((s) => ({ ...s, [f.name]: e.target.value }))
                }
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
              >
                <option value="new">Create new account</option>
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}{a.institution_name && a.name !== a.institution_name ? ` (${a.institution_name})` : ''}
                  </option>
                ))}
              </select>

              {selections[f.name] === 'new' && (
                <input
                  type="text"
                  value={customNames[f.name]}
                  onChange={(e) =>
                    setCustomNames((n) => ({ ...n, [f.name]: e.target.value }))
                  }
                  placeholder="Account name"
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                />
              )}
            </div>
          ))}
        </div>

        <div className="flex justify-end gap-3 px-6 py-4 border-t border-slate-200">
          <button
            onClick={onCancel}
            className="px-4 py-2 border border-slate-300 text-slate-700 text-sm font-medium rounded-lg hover:bg-slate-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            className="px-4 py-2 bg-slate-900 text-white text-sm font-medium rounded-lg hover:bg-slate-800 transition-colors"
          >
            Import {files.length} file{files.length > 1 ? 's' : ''}
          </button>
        </div>
      </div>
    </div>
  )
}

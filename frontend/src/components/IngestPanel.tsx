import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api/client'

type UploadKind = 'agent-config' | 'runtime-logs' | 'policy'

const UPLOAD_KINDS: { value: UploadKind; label: string }[] = [
  { value: 'agent-config', label: 'Agent config (YAML/JSON)' },
  { value: 'runtime-logs', label: 'Runtime logs (JSONL)' },
  { value: 'policy', label: 'Policy document (Markdown/text)' },
]

interface IngestPanelProps {
  onIngested: () => void
}

export function IngestPanel({ onIngested }: IngestPanelProps) {
  const [bundles, setBundles] = useState<string[]>([])
  const [bundle, setBundle] = useState('')
  const [reset, setReset] = useState(true)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [uploadKind, setUploadKind] = useState<UploadKind>('agent-config')
  const [uploadReset, setUploadReset] = useState(false)
  const fileRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    let active = true
    api
      .getBundles()
      .then((r) => {
        if (!active) return
        setBundles(r.bundles)
        setBundle((prev) => (r.bundles.includes(prev) ? prev : r.bundles[0] ?? ''))
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : String(e)))
    return () => {
      active = false
    }
  }, [])

  async function withBusy(action: () => Promise<string>) {
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      setMessage(await action())
      onIngested()
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const ingestBundle = () =>
    withBusy(async () => {
      await api.ingestBundle(bundle, reset)
      return `Ingested bundle "${bundle}".`
    })

  const uploadFile = () =>
    withBusy(async () => {
      const file = fileRef.current?.files?.[0]
      if (!file) throw new ApiError('Choose a file to upload.', 0)
      await api.uploadFile(uploadKind, file, uploadReset)
      if (fileRef.current) fileRef.current.value = ''
      return `Uploaded ${file.name} as ${uploadKind}.`
    })

  const resetGraph = () =>
    withBusy(async () => {
      await api.resetGraph()
      return 'Graph reset.'
    })

  return (
    <section className="panel">
      <h2>Ingest</h2>

      <label className="field">
        <span>Sample bundle</span>
        <select value={bundle} onChange={(e) => setBundle(e.target.value)} disabled={bundles.length === 0}>
          {bundles.length === 0 && <option value="">(none found)</option>}
          {bundles.map((b) => (
            <option key={b} value={b}>
              {b}
            </option>
          ))}
        </select>
      </label>
      <label className="checkbox">
        <input type="checkbox" checked={reset} onChange={(e) => setReset(e.target.checked)} />
        Reset graph first
      </label>
      <button className="btn primary" onClick={ingestBundle} disabled={busy || !bundle}>
        {busy ? 'Working…' : 'Ingest bundle'}
      </button>

      <hr />

      <label className="field">
        <span>Upload a file</span>
        <select value={uploadKind} onChange={(e) => setUploadKind(e.target.value as UploadKind)}>
          {UPLOAD_KINDS.map((k) => (
            <option key={k.value} value={k.value}>
              {k.label}
            </option>
          ))}
        </select>
      </label>
      <input ref={fileRef} type="file" className="file" />
      <label className="checkbox">
        <input type="checkbox" checked={uploadReset} onChange={(e) => setUploadReset(e.target.checked)} />
        Reset graph first
      </label>
      <div className="row">
        <button className="btn" onClick={uploadFile} disabled={busy}>
          Upload
        </button>
        <button className="btn danger" onClick={resetGraph} disabled={busy}>
          Reset graph
        </button>
      </div>

      {error && <p className="error">{error}</p>}
      {message && <p className="summary">{message}</p>}
    </section>
  )
}

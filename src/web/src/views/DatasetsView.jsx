import React, { useState } from 'react'
import { AlertTriangle, AtSign, Lock, Search, Trash2, Upload } from 'lucide-react'
import { Badge, Button, Card, PageHeader, Spinner } from '../ui'
import { fmt, fmtTime } from '../labels'

function StatusBadge({ dataset }) {
  const job = dataset.job ?? {}
  if (job.state === 'running') return <Badge tone="accent"><Spinner className="w-3 h-3" />Analysing · step {job.step + 1}/{job.stages.length}</Badge>
  if (job.state === 'error') return <Badge tone="URGENT">Failed</Badge>
  if (dataset.analyzed) return <Badge tone="benign">Ready</Badge>
  return <Badge>Not analysed</Badge>
}

// Every dataset is X API v2 JSON, stored in its own X database (docs/data-model.md)
export function DatasetsView({ datasets, currentId, onOpen, onAnalyze, onDelete, onUpload, onXSearch, xConfigured }) {
  return (
    <>
      <PageHeader title="Datasets" subtitle="X API v2 posts, uploaded as the API returned them or fetched from X, analysed for coordinated campaigns." />
      <div className="grid gap-4 lg:grid-cols-12 items-start">
        <div className="lg:col-span-4 space-y-4">
          <UploadCard onUpload={onUpload} />
          <XSearchCard onSearch={onXSearch} configured={xConfigured} />
        </div>

        <Card title="All datasets" className="lg:col-span-8" bodyClassName="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-subtle text-xs text-muted text-left">
              <tr>
                <th className="font-medium px-4 py-2">Name</th>
                <th className="font-medium px-4 py-2 text-right">Posts</th>
                <th className="font-medium px-4 py-2 text-right">Accounts</th>
                <th className="font-medium px-4 py-2">Status</th>
                <th className="px-4 py-2"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {datasets.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-10 text-center text-sm text-muted">
                  No datasets yet. Upload an export or search X to start.
                </td></tr>
              )}
              {datasets.map((d) => {
                const running = d.job?.state === 'running'
                return (
                  <tr key={d.id} className={d.id === currentId ? 'bg-subtle/60' : ''}>
                    <td className="px-4 py-3">
                      <div className="font-medium">{d.name}</div>
                      {d.description && <div className="text-xs text-muted mt-0.5 max-w-md">{d.description}</div>}
                      <div className="text-xs font-mono text-faint mt-0.5">
                        {d.source === 'x_api' ? `X search · fetched ${fmtTime(d.fetched_at, true)}` : `X API v2 upload · ${d.id}`}
                      </div>
                      {d.warnings?.map((w) => (
                        <div key={w} className="flex gap-1 text-xs text-alert mt-0.5 max-w-md"><AlertTriangle className="w-3.5 h-3.5 mt-px shrink-0" aria-hidden />{w}</div>
                      ))}
                    </td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums">{fmt(d.posts)}</td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums">{fmt(d.accounts)}</td>
                    <td className="px-4 py-3"><StatusBadge dataset={d} /></td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end items-center gap-1.5">
                        <Button onClick={() => onOpen(d.id)}>Open</Button>
                        <Button variant="ghost" disabled={running || d.protected} onClick={() => onAnalyze(d.id)}>
                          {d.analyzed ? 'Re-run' : 'Analyse'}
                        </Button>
                        {d.protected ? (
                          <span
                            className="inline-flex items-center gap-1 px-2 py-1 text-xs font-mono text-muted bg-subtle rounded border border-line cursor-default"
                            title="Protected reference dataset — deletion disabled"
                          >
                            <Lock className="w-3 h-3 text-faint" aria-hidden />
                            Protected
                          </span>
                        ) : (
                          <Button
                            variant="ghost"
                            className="px-2 hover:text-urgent"
                            disabled={running}
                            onClick={() => onDelete(d)}
                            aria-label={`Delete ${d.name}`}
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </Card>
      </div>
    </>
  )
}

function UploadCard({ onUpload, className = '' }) {
  const [file, setFile] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState(null)

  const pick = (f) => {
    setFile(f)
    setError(null)
  }
  const submit = async () => {
    setUploading(true)
    setError(null)
    try {
      await onUpload(file)
      setFile(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setUploading(false)
    }
  }

  return (
    <Card title="Upload X API v2 JSON" className={className}>
      <label
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); if (e.dataTransfer.files[0]) pick(e.dataTransfer.files[0]) }}
        className={`flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-4 py-8 text-center cursor-pointer transition-colors ${dragging ? 'border-accent bg-subtle' : 'border-line hover:bg-subtle'}`}
      >
        <Upload className="w-6 h-6 text-faint" aria-hidden />
        <span className="text-sm font-medium">{file ? file.name : 'Drop a file here or choose one'}</span>
        <span className="text-xs text-muted">{file ? `${(file.size / 1e6).toFixed(1)} MB` : '.json or .jsonl, exactly as the X API returned it'}</span>
        <input type="file" accept=".json,.jsonl" className="sr-only" onChange={(e) => e.target.files[0] && pick(e.target.files[0])} />
      </label>

      <Button variant="primary" className="w-full mt-3" disabled={!file || uploading} onClick={submit}>
        {uploading ? <><Spinner />Reading file…</> : 'Upload and analyse'}
      </Button>
      {uploading && <p className="text-xs text-muted mt-2">Large files (100 MB) take up to a minute to read.</p>}
      {error && <p className="text-sm text-urgent mt-2">{error}</p>}

      <div className="text-xs text-muted mt-4 space-y-2">
        <p className="font-medium text-ink">Only X API v2 output is accepted</p>
        <p>
          A search, timeline or lookup response ({'{'}"data", "includes", "meta"{'}'}), a list of them, one per line, or
          filtered-stream lines. Each post needs <span className="font-mono">created_at</span> and{' '}
          <span className="font-mono">author_id</span>; with <span className="font-mono">expansions=author_id</span>,
          <span className="font-mono"> referenced_tweets</span> and <span className="font-mono">public_metrics</span> every
          signal and the full post view work. Anything else is refused with the reason.
        </p>
        <p>
          <a href="/x-api-v2-example.json" download className="text-accent hover:underline">Download an example response</a>
          <span className="text-faint"> · request fields and the database layout in docs/data-model.md</span>
        </p>
      </div>
    </Card>
  )
}

// Pulls the last 7 days of posts matching a query from X's recent-search API into a new dataset
function XSearchCard({ onSearch, configured }) {
  const [query, setQuery] = useState('')
  const [max, setMax] = useState(500)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await onSearch(query, max)
      setQuery('')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card title="Search X" subtitle="Posts from the last 7 days, straight from the X API">
      <form onSubmit={submit} className="space-y-2">
        <label className="relative block">
          <AtSign className="w-4 h-4 absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" aria-hidden />
          <input value={query} onChange={(e) => setQuery(e.target.value)} disabled={!configured || busy}
            placeholder='#RajpuraBachao OR "bachcha chor" -is:retweet'
            className="w-full h-9 pl-8 pr-3 rounded-md border border-line bg-surface text-sm placeholder:text-faint disabled:opacity-60" />
        </label>
        <div className="flex gap-2">
          <select value={max} onChange={(e) => setMax(Number(e.target.value))} disabled={!configured || busy}
            aria-label="How many posts" className="h-8 rounded-md border border-line bg-surface text-sm px-2 cursor-pointer">
            {[100, 500, 1000, 5000].map((n) => <option key={n} value={n}>up to {fmt(n)} posts</option>)}
          </select>
          <Button variant="primary" className="flex-1" disabled={!configured || busy || !query.trim()} type="submit">
            {busy ? <><Spinner /> Fetching…</> : <><Search className="w-4 h-4" /> Fetch and analyse</>}
          </Button>
        </div>
        {error && <p className="text-sm text-urgent">{error}</p>}
        <p className="text-xs text-muted">
          {configured
            ? 'Uses X search operators (OR, quotes, -is:retweet, lang:hi, has:links). Authors, retweets, replies, links and locations come with the posts.'
            : 'Add X_BEARER_TOKEN to src/.env (an X API plan that includes recent search) and restart the server to turn this on.'}
        </p>
      </form>
    </Card>
  )
}

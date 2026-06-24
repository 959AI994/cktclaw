import type { UploadMeta } from '../types/api'

const DEFAULT_ACCEPT =
  '.png,.jpg,.jpeg,.gif,.webp,.svg,.v,.sv,.vh,.svh,.py,.md,.txt,.json,.yml,.yaml,.tcl,.sdc,.lib,.lef,.def,.spice,.csv,.log'

export function uploadUrl(meta: Pick<UploadMeta, 'id' | 'session_id' | 'url'>): string {
  if (meta.url) return meta.url
  const sid = encodeURIComponent(meta.session_id || 'default')
  return `/api/uploads/${encodeURIComponent(meta.id)}?session_id=${sid}`
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function isImageMime(mime: string): boolean {
  return mime.startsWith('image/')
}

export async function uploadFiles(sessionId: string, files: File[]): Promise<UploadMeta[]> {
  if (!sessionId || !files.length) return []

  const form = new FormData()
  form.append('session_id', sessionId)
  for (const f of files) {
    form.append('file', f)
  }

  const res = await fetch('/api/uploads', { method: 'POST', body: form })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const err = await res.json()
      detail = err.detail || (Array.isArray(err.errors) ? err.errors.join('; ') : detail)
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === 'string' ? detail : 'Upload failed')
  }

  const data = (await res.json()) as { uploads?: UploadMeta[]; errors?: string[] }
  if (data.errors?.length && !data.uploads?.length) {
    throw new Error(data.errors.join('; '))
  }
  return data.uploads || []
}

export async function listUploads(sessionId: string): Promise<UploadMeta[]> {
  const res = await fetch(`/api/uploads?session_id=${encodeURIComponent(sessionId)}`)
  if (!res.ok) return []
  return res.json() as Promise<UploadMeta[]>
}

export { DEFAULT_ACCEPT }

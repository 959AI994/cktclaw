import { useRef, useState } from 'react'
import type { UploadMeta } from '../../types/api'
import { DEFAULT_ACCEPT, formatFileSize, isImageMime, uploadFiles, uploadUrl } from '../../lib/uploads'
import { useAppStore } from '../../store/appStore'

interface AttachmentUploaderProps {
  sessionId: string
  attachments: UploadMeta[]
  onChange: (attachments: UploadMeta[]) => void
  disabled?: boolean
  accept?: string
  compact?: boolean
}

export function AttachmentUploader({
  sessionId,
  attachments,
  onChange,
  disabled = false,
  accept = DEFAULT_ACCEPT,
  compact = false,
}: AttachmentUploaderProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const toast = useAppStore((s) => s.toast)

  const handleFiles = async (files: File[]) => {
    if (!sessionId || !files.length || disabled) return
    setUploading(true)
    try {
      const uploaded = await uploadFiles(sessionId, files)
      onChange([...attachments, ...uploaded])
      if (uploaded.length) toast('success', `Uploaded ${uploaded.length} file(s)`)
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  const remove = (id: string) => {
    onChange(attachments.filter((a) => a.id !== id))
  }

  return (
    <div className={compact ? 'space-y-2' : 'space-y-3'}>
      <div className="flex flex-wrap gap-2 items-center">
        <button
          type="button"
          className="attachment-upload-btn"
          disabled={disabled || uploading || !sessionId}
          onClick={() => inputRef.current?.click()}
        >
          {uploading ? 'Uploading…' : '+ Attach files'}
        </button>
        <span className="text-xs text-[var(--color-text-dim)]">
          Images & code · drag & drop supported · max 10 MB
        </span>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={accept}
          className="hidden"
          disabled={disabled || uploading}
          onChange={(e) => {
            const files = Array.from(e.target.files || [])
            if (files.length) void handleFiles(files)
          }}
        />
      </div>

      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {attachments.map((a) => (
            <AttachmentChip key={a.id} meta={a} onRemove={() => remove(a.id)} disabled={disabled} />
          ))}
        </div>
      )}
    </div>
  )
}

function AttachmentChip({
  meta,
  onRemove,
  disabled,
}: {
  meta: UploadMeta
  onRemove: () => void
  disabled?: boolean
}) {
  const isImage = isImageMime(meta.mime)
  const url = uploadUrl(meta)

  return (
    <div className="attachment-chip">
      {isImage ? (
        <img src={url} alt={meta.filename} className="attachment-thumb" />
      ) : (
        <span className="attachment-file-icon">📄</span>
      )}
      <div className="attachment-chip-meta">
        <span className="attachment-chip-name" title={meta.filename}>
          {meta.filename}
        </span>
        <span className="attachment-chip-size">{formatFileSize(meta.size)}</span>
      </div>
      {!disabled && (
        <button type="button" className="attachment-chip-remove" onClick={onRemove} aria-label="Remove">
          ×
        </button>
      )}
    </div>
  )
}

export function AttachmentPreviewList({ attachments }: { attachments: UploadMeta[] }) {
  if (!attachments.length) return null
  return (
    <div className="flex flex-wrap gap-2 mt-2">
      {attachments.map((a) => (
        <AttachmentChip key={a.id} meta={a} onRemove={() => {}} disabled />
      ))}
    </div>
  )
}

/** Hook for parent components that handle drag-drop at a larger zone */
export function useAttachmentUploadHandler(
  sessionId: string,
  attachments: UploadMeta[],
  onChange: (attachments: UploadMeta[]) => void,
  disabled = false,
) {
  const toast = useAppStore((s) => s.toast)

  return async (files: File[]) => {
    if (!sessionId || !files.length || disabled) return
    try {
      const uploaded = await uploadFiles(sessionId, files)
      onChange([...attachments, ...uploaded])
      if (uploaded.length) toast('success', `Uploaded ${uploaded.length} file(s)`)
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Upload failed')
    }
  }
}

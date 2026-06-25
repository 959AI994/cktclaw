import { useCallback, useRef, useState } from 'react'

export function useDragDrop(onDropFiles: (files: File[]) => void, disabled = false) {
  const [isDragging, setIsDragging] = useState(false)
  const dragCounter = useRef(0)

  const onDragEnter = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      if (disabled) return
      dragCounter.current += 1
      if (e.dataTransfer.types.includes('Files')) {
        setIsDragging(true)
      }
    },
    [disabled],
  )

  const onDragLeave = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      if (disabled) return
      dragCounter.current -= 1
      if (dragCounter.current <= 0) {
        dragCounter.current = 0
        setIsDragging(false)
      }
    },
    [disabled],
  )

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }, [])

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      dragCounter.current = 0
      setIsDragging(false)
      if (disabled) return
      const files = Array.from(e.dataTransfer.files || [])
      if (files.length) onDropFiles(files)
    },
    [disabled, onDropFiles],
  )

  return { isDragging, onDragEnter, onDragLeave, onDragOver, onDrop }
}

import { useCallback, useEffect } from 'react'
import { useChatStore } from '../../store/chatStore'
import { useWebSocket } from '../../hooks/useWebSocket'
import { useDragDrop } from '../../hooks/useDragDrop'
import { ChatThread } from '../chat/ChatThread'
import { ChatInputBar } from '../chat/ChatInput'
import { useAttachmentUploadHandler } from '../upload/AttachmentUploader'
import { Button } from '../ui/Button'
import { sessionId as formatSessionId } from '../../lib/utils'

export function ChatPanel() {
  const sessionId = useChatStore((s) => s.sessionId)
  const availableSessions = useChatStore((s) => s.availableSessions)
  const sessionsLoading = useChatStore((s) => s.sessionsLoading)
  const messages = useChatStore((s) => s.messages)
  const inputText = useChatStore((s) => s.inputText)
  const pendingAttachments = useChatStore((s) => s.pendingAttachments)
  const streamBuffer = useChatStore((s) => s.streamBuffer)
  const streaming = useChatStore((s) => s.streaming)
  const skipOrchestratorConfirm = useChatStore((s) => s.skipOrchestratorConfirm)
  const disableTools = useChatStore((s) => s.disableTools)
  const orchestratorProposal = useChatStore((s) => s.orchestratorProposal)
  const activeOrchestratorRun = useChatStore((s) => s.activeOrchestratorRun)
  const pendingToolCalls = useChatStore((s) => s.pendingToolCalls)
  const setInputText = useChatStore((s) => s.setInputText)
  const setSkipOrchestratorConfirm = useChatStore((s) => s.setSkipOrchestratorConfirm)
  const setDisableTools = useChatStore((s) => s.setDisableTools)
  const setPendingAttachments = useChatStore((s) => s.setPendingAttachments)
  const sendMessage = useChatStore((s) => s.sendMessage)
  const abortChat = useChatStore((s) => s.abortChat)
  const confirmOrchestrator = useChatStore((s) => s.confirmOrchestrator)
  const cancelOrchestrator = useChatStore((s) => s.cancelOrchestrator)
  const handleChatMessage = useChatStore((s) => s.handleChatMessage)
  const initChat = useChatStore((s) => s.initChat)
  const fetchAvailableSessions = useChatStore((s) => s.fetchAvailableSessions)
  const newSession = useChatStore((s) => s.newSession)
  const setSessionId = useChatStore((s) => s.setSessionId)

  const { sendChat, abortChat: wsAbort, onChat, confirmOrchestrator: wsConfirm, cancelOrchestrator: wsCancel } =
    useWebSocket()

  const handleDropFiles = useAttachmentUploadHandler(
    sessionId,
    pendingAttachments,
    setPendingAttachments,
    streaming || !sessionId,
  )

  const onDropFiles = useCallback(
    (files: File[]) => {
      void handleDropFiles(files)
    },
    [handleDropFiles],
  )

  const { isDragging, onDragEnter, onDragLeave, onDragOver, onDrop } = useDragDrop(
    onDropFiles,
    streaming || !sessionId,
  )

  useEffect(() => {
    initChat()
  }, [initChat])

  useEffect(() => {
    if (!sessionId) return
    return onChat(sessionId, handleChatMessage)
  }, [sessionId, onChat, handleChatMessage])

  return (
    <div className="flex flex-col h-full -m-5">
      <div className="px-5 pt-5 pb-2">
        <h2 className="text-lg font-semibold mb-3">Chat</h2>
        <div className="flex items-center gap-2 text-sm flex-wrap">
          <select
            className="px-2 py-1 rounded-md border border-[var(--color-border)] bg-[var(--color-bg-root)] text-[var(--color-text)] min-w-[200px]"
            value={sessionId}
            onChange={(e) => setSessionId(e.target.value)}
            disabled={sessionsLoading}
          >
            {!sessionId && <option value="">Select session…</option>}
            {availableSessions.map((s) => {
              const id = formatSessionId(s)
              const label = s.session_title || id
              const count = s.message_count != null ? ` (${s.message_count})` : ''
              return (
                <option key={id} value={id}>
                  {label}
                  {count}
                </option>
              )
            })}
            {sessionId && !availableSessions.some((s) => formatSessionId(s) === sessionId) && (
              <option value={sessionId}>{sessionId}</option>
            )}
          </select>
          <Button size="sm" onClick={fetchAvailableSessions} disabled={sessionsLoading}>
            ↻ Sessions
          </Button>
          <Button size="sm" onClick={newSession}>
            + New
          </Button>
        </div>
      </div>

      <div
        className="relative flex-1 flex flex-col min-h-0 border border-[var(--color-border)] rounded-lg mx-5 mb-5 overflow-hidden bg-[var(--color-bg-surface)]"
        onDragEnter={onDragEnter}
        onDragLeave={onDragLeave}
        onDragOver={onDragOver}
        onDrop={onDrop}
      >
        {isDragging && (
          <div className="drop-overlay">
            <div className="drop-overlay-inner">Drop files here</div>
          </div>
        )}
        <ChatThread
          messages={messages}
          streamBuffer={streamBuffer}
          streaming={streaming}
          pendingToolCalls={pendingToolCalls}
          orchestratorProposal={orchestratorProposal}
          activeOrchestratorRun={activeOrchestratorRun}
          onOrchestratorConfirm={(task) => confirmOrchestrator(wsConfirm, task)}
          onOrchestratorCancel={() => cancelOrchestrator(wsCancel)}
        />
        <ChatInputBar
          value={inputText}
          streaming={streaming}
          skipOrchestratorConfirm={skipOrchestratorConfirm}
          disableTools={disableTools}
          sessionId={sessionId}
          pendingAttachments={pendingAttachments}
          onAttachmentsChange={setPendingAttachments}
          onChange={setInputText}
          onSkipOrchestratorConfirmChange={setSkipOrchestratorConfirm}
          onDisableToolsChange={setDisableTools}
          onSend={() => sendMessage(sendChat)}
          onAbort={() => abortChat(wsAbort)}
        />
      </div>
    </div>
  )
}

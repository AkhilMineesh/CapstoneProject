import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { AnalyzeResponse, Filters, SearchRequest } from '../api'
import { analyze } from '../api'

export type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  text: string
  createdAt: number
}

export type Chat = {
  id: string
  title: string
  createdAt: number
  updatedAt: number
  request: SearchRequest
  response: AnalyzeResponse
  messages: ChatMessage[]
}

type CreateChatOptions = {
  filters?: Filters
  rerank?: boolean
  includeInsights?: boolean
}

type ChatsState = {
  chats: Chat[]
  activeChatId: string | null
  setActiveChatId: (id: string | null) => void
  createChatFromQuery: (query: string, options?: CreateChatOptions) => Promise<Chat>
  deleteChat: (id: string) => void
  clearChats: () => void
  getChat: (id: string) => Chat | null
}

const STORAGE_KEY = 'medrag.chats.v1'

function safeParseChats(raw: string | null): Chat[] {
  if (!raw) return []
  try {
    const data = JSON.parse(raw) as unknown
    if (!Array.isArray(data)) return []
    return data as Chat[]
  } catch {
    return []
  }
}

function makeId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `c_${Math.random().toString(16).slice(2)}_${Date.now()}`
}

function summarizeAssistant(resp: AnalyzeResponse): string {
  const parts: string[] = []
  const summary = resp.insights?.summary?.trim()
  if (summary) parts.push(summary)
  const findings = (resp.insights?.key_findings ?? []).slice(0, 4)
  if (findings.length) parts.push(`Key points:\n- ${findings.join('\n- ')}`)
  if (!parts.length) parts.push('I analyzed your query and selected only the most relevant articles.')
  return parts.join('\n\n')
}

const ChatsContext = createContext<ChatsState | null>(null)

export function ChatsProvider(props: { children: React.ReactNode }) {
  const [chats, setChats] = useState<Chat[]>(() => safeParseChats(localStorage.getItem(STORAGE_KEY)))
  const [activeChatId, setActiveChatId] = useState<string | null>(() => (chats[0]?.id ? chats[0].id : null))

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(chats.slice(0, 100)))
  }, [chats])

  const getChat = useCallback(
    (id: string) => {
      return chats.find((c) => c.id === id) ?? null
    },
    [chats],
  )

  const createChatFromQuery = useCallback(async (query: string, options?: CreateChatOptions) => {
    const req: SearchRequest = {
      query,
      filters: options?.filters && Object.keys(options.filters).length ? options.filters : null,
      rerank: options?.rerank ?? true,
      include_insights: options?.includeInsights ?? true,
    }

    const resp = await analyze(req)
    const now = Date.now()
    const chatId = makeId()
    const messages: ChatMessage[] = [
      { id: makeId(), role: 'user', text: query, createdAt: now },
      { id: makeId(), role: 'assistant', text: summarizeAssistant(resp), createdAt: now + 1 },
    ]

    const chat: Chat = {
      id: chatId,
      title: query.trim().slice(0, 42) || 'New chat',
      createdAt: now,
      updatedAt: now,
      request: req,
      response: resp,
      messages,
    }

    setChats((prev) => [chat, ...prev].slice(0, 100))
    setActiveChatId(chatId)
    return chat
  }, [])

  const deleteChat = useCallback((id: string) => {
    setChats((prev) => prev.filter((c) => c.id !== id))
    setActiveChatId((cur) => (cur === id ? null : cur))
  }, [])

  const clearChats = useCallback(() => {
    setChats([])
    setActiveChatId(null)
  }, [])

  const value = useMemo<ChatsState>(
    () => ({
      chats,
      activeChatId,
      setActiveChatId,
      createChatFromQuery,
      deleteChat,
      clearChats,
      getChat,
    }),
    [activeChatId, chats, clearChats, createChatFromQuery, deleteChat, getChat],
  )

  return <ChatsContext.Provider value={value}>{props.children}</ChatsContext.Provider>
}

export function useChats(): ChatsState {
  const ctx = useContext(ChatsContext)
  if (!ctx) throw new Error('useChats must be used within ChatsProvider')
  return ctx
}

import type { AnalyzeResponse } from '../api'

export type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  ts: number
  turnId?: string
}

export type ChatTurn = {
  id: string
  query: string
  createdAt: number
  response: AnalyzeResponse
}

export type Chat = {
  id: string
  title: string
  createdAt: number
  updatedAt: number
  messages: ChatMessage[]
  turns: Record<string, ChatTurn>
}

const KEY = 'medrag_chats_v2'
const LAST_KEY = 'medrag_last_chat_v2'

let memoryChats: Chat[] | null = null
let memoryLast: string | null = null
const EVT = 'medrag_chats_changed'

function now() {
  return Date.now()
}

function rid() {
  return Math.random().toString(36).slice(2, 10) + '-' + Math.random().toString(36).slice(2, 10)
}

function safeGet(k: string): string | null {
  try {
    return localStorage.getItem(k)
  } catch {
    return null
  }
}

function safeSet(k: string, v: string) {
  try {
    localStorage.setItem(k, v)
  } catch {
    // ignore
  }
}

function safeDel(k: string) {
  try {
    localStorage.removeItem(k)
  } catch {
    // ignore
  }
}

function assistantWelcome(): ChatMessage {
  return {
    id: rid(),
    role: 'assistant',
    ts: now(),
    content:
      'Ask a medical research question in natural language. I will retrieve the most relevant PubMed/MEDLINE abstracts and show a focused list of articles.',
  }
}

function notifyChanged() {
  try {
    window.dispatchEvent(new Event(EVT))
  } catch {
    // ignore
  }
}

export function onChatsChanged(cb: () => void) {
  const handler = () => cb()
  window.addEventListener(EVT, handler)
  window.addEventListener('storage', handler)
  return () => {
    window.removeEventListener(EVT, handler)
    window.removeEventListener('storage', handler)
  }
}

function normalizeChat(c: any): Chat {
  const id = typeof c?.id === 'string' ? c.id : rid()
  const createdAt = typeof c?.createdAt === 'number' ? c.createdAt : now()
  const updatedAt = typeof c?.updatedAt === 'number' ? c.updatedAt : createdAt

  const normMessages: ChatMessage[] = []
  if (Array.isArray(c?.messages)) {
    for (const m of c.messages) {
      if (!m || typeof m !== 'object') continue
      if (m.role !== 'user' && m.role !== 'assistant') continue
      if (typeof m.content !== 'string') continue
      normMessages.push({
        id: typeof m.id === 'string' ? m.id : rid(),
        role: m.role,
        content: m.content,
        ts: typeof m.ts === 'number' ? m.ts : now(),
        turnId: typeof m.turnId === 'string' ? m.turnId : undefined,
      })
    }
  }
  if (!normMessages.length) normMessages.push(assistantWelcome())

  const normTurns: Record<string, ChatTurn> = {}
  if (c?.turns && typeof c.turns === 'object') {
    for (const [k, v] of Object.entries(c.turns)) {
      const t: any = v
      if (!t || typeof t !== 'object') continue
      if (typeof t.id !== 'string' || typeof t.query !== 'string' || !t.response) continue
      normTurns[k] = {
        id: t.id,
        query: t.query,
        createdAt: typeof t.createdAt === 'number' ? t.createdAt : now(),
        response: t.response as AnalyzeResponse,
      }
    }
  }

  const title =
    typeof c?.title === 'string' && c.title.trim()
      ? c.title
      : normMessages.find((m) => m.role === 'user')?.content.slice(0, 42) ?? 'Chat'

  return { id, title, createdAt, updatedAt, messages: normMessages, turns: normTurns }
}

export function loadChats(): Chat[] {
  try {
    const raw = safeGet(KEY)
    if (!raw) return memoryChats ?? []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    const chats = parsed.map(normalizeChat)
    saveChats(chats)
    return chats
  } catch {
    return memoryChats ?? []
  }
}

export function saveChats(chats: Chat[]) {
  memoryChats = chats
  safeSet(KEY, JSON.stringify(chats))
  notifyChanged()
}

export function setLastChatId(chatId: string) {
  memoryLast = chatId
  safeSet(LAST_KEY, chatId)
  notifyChanged()
}

export function getLastChatId(): string | null {
  return safeGet(LAST_KEY) ?? memoryLast
}

export function ensureChat(): Chat {
  const chats = loadChats()
  const chat: Chat = {
    id: rid(),
    title: 'New chat',
    createdAt: now(),
    updatedAt: now(),
    messages: [assistantWelcome()],
    turns: {},
  }
  chats.unshift(chat)
  saveChats(chats)
  setLastChatId(chat.id)
  return chat
}

export function createChat(): Chat {
  return {
    id: rid(),
    title: 'New chat',
    createdAt: now(),
    updatedAt: now(),
    messages: [assistantWelcome()],
    turns: {},
  }
}

export function getChat(chatId: string): Chat | null {
  return loadChats().find((c) => c.id === chatId) ?? null
}

export function upsertChat(chat: Chat) {
  const chats = loadChats()
  const idx = chats.findIndex((c) => c.id === chat.id)
  if (idx >= 0) chats[idx] = chat
  else chats.unshift(chat)
  chats.sort((a, b) => b.updatedAt - a.updatedAt)
  saveChats(chats)
  setLastChatId(chat.id)
}

export function deleteChat(chatId: string) {
  const chats = loadChats().filter((c) => c.id !== chatId)
  saveChats(chats)
  const last = getLastChatId()
  if (last === chatId) {
    memoryLast = null
    safeDel(LAST_KEY)
  }
  notifyChanged()
}

export function clearAllChats() {
  memoryChats = []
  memoryLast = null
  safeDel(KEY)
  safeDel(LAST_KEY)
  notifyChanged()
}

export function appendUserMessage(chat: Chat, content: string) {
  chat.messages.push({ id: rid(), role: 'user', content, ts: now() })
  chat.updatedAt = now()
  if (chat.title === 'New chat') chat.title = content.slice(0, 42) + (content.length > 42 ? '...' : '')
}

export function appendAssistantMessage(chat: Chat, content: string, turnId?: string) {
  chat.messages.push({ id: rid(), role: 'assistant', content, ts: now(), turnId })
  chat.updatedAt = now()
}

export function saveTurn(chat: Chat, query: string, response: AnalyzeResponse): string {
  const turnId = rid()
  chat.turns[turnId] = { id: turnId, query, createdAt: now(), response }
  chat.updatedAt = now()
  return turnId
}

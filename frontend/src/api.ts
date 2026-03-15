export type Filters = {
  publication_year_from?: number
  publication_year_to?: number
  journal?: string
  study_type?: string
  disease_area?: string
  clinical_trial_stage?: string
}

export type SearchRequest = {
  query: string
  filters?: Filters | null
  top_k?: number | null
  rerank?: boolean
  include_insights?: boolean
}

export type EvidenceSnippet = { text: string; why: string }
export type Citation = {
  pmid: string
  title: string
  journal?: string | null
  year?: number | null
  authors: string[]
  doi?: string | null
}
export type PaperResult = {
  pmid: string
  score: number
  title: string
  abstract: string
  citation: Citation
  mesh_terms: string[]
  keywords: string[]
  publication_types: string[]
  disease_area?: string | null
  trial_stage?: string | null
  evidence: EvidenceSnippet[]
}

export type ConflictItem = {
  outcome: string
  papers_supporting: string[]
  papers_conflicting: string[]
  note: string
}
export type TrendItem = { term: string; counts_by_year: Record<string, number> }
export type KnowledgeGraph = {
  nodes: Array<{ id: string; label: string; kind: string; count: number }>
  edges: Array<{ source: string; target: string; rel: string; weight: number }>
}
export type Insights = {
  summary: string
  key_findings: string[]
  conflicts: ConflictItem[]
  trends: TrendItem[]
  knowledge_graph?: KnowledgeGraph | null
  guardrails: string[]
  expanded_query?: string | null
}
export type AgentReport = { agent: string; notes: string[] }
export type AnalyzeResponse = {
  query: string
  expanded_query?: string | null
  results: PaperResult[]
  insights?: Insights | null
  agent_reports: AgentReport[]
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const j = await res.json()
      if (j?.detail) detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch {
      // ignore
    }
    throw new Error(detail)
  }
  return (await res.json()) as T
}

export async function analyze(req: SearchRequest): Promise<AnalyzeResponse> {
  return http<AnalyzeResponse>('/api/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
}

export async function metadataOptions(): Promise<{
  years: { min: number | null; max: number | null }
  journals: string[]
  disease_areas: string[]
  trial_stages: string[]
  study_types: string[]
}> {
  return http('/api/metadata/options')
}

export async function analyzeFile(
  kind: 'document' | 'image' | 'audio',
  file: File,
  opts?: { rerank?: boolean; include_insights?: boolean },
): Promise<AnalyzeResponse> {
  const fd = new FormData()
  fd.append('file', file)
  const params = new URLSearchParams()
  if (opts?.rerank === false) params.set('rerank', 'false')
  if (opts?.include_insights === false) params.set('include_insights', 'false')
  const q = params.toString() ? `?${params.toString()}` : ''
  return http<AnalyzeResponse>(`/api/query/${kind}${q}`, { method: 'POST', body: fd })
}

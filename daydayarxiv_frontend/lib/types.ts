export interface Paper {
  arxiv_id: string
  title: string
  title_zh: string
  authors: string[]
  abstract: string
  tldr_zh: string
  categories: string[]
  primary_category: string
  comment: string
  pdf_url?: string
  published_date: string
  updated_date: string
}

export interface DailyData {
  date: string
  category: string
  summary: string
  papers: Paper[]
}

export interface DataIndex {
  available_dates: string[]
  categories: string[]
  by_date: Record<string, string[]>
  last_updated?: string
}

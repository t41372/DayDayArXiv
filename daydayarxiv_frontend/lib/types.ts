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
  pdfUrl?: string
  published_date: string
  updated_date: string
}

export interface DailyData {
  date: string
  category: string
  summary: string
  papers: Paper[]
}


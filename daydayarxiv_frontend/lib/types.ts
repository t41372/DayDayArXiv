export interface Paper {
  id: string
  title: string
  titleZh: string
  authors: string[]
  abstract: string
  abstractZh: string
  categories: string[]
  date: string
  pdfUrl?: string
}

export interface DailyData {
  date: string
  category: string
  summary: string
  papers: Paper[]
}


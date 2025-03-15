import { format } from "date-fns"

interface DailySummaryProps {
  date: Date
  category: string
  summary: string
}

export default function DailySummary({ date, category, summary }: DailySummaryProps) {
  const formattedDate = format(date, "yyyy 年MM月dd日")

  return (
    <div className="bg-white rounded-lg p-6 shadow-sm border border-black border-opacity-50">
      <h2 className="text-2xl font-medium mb-2">
        {formattedDate}: arXiv 每日总结, {category} 区
      </h2>
      <h3 className="text-lg font-medium mb-4">今天都有些什么论文</h3>

      <p className="text-[#45454a] whitespace-pre-line">{summary}</p>
    </div>
  )
}


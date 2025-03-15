import { format } from "date-fns"

interface DailySummaryProps {
  date: Date
  category: string
  summary: string
}

export default function DailySummary({ date, category, summary }: DailySummaryProps) {
  return (
    <div className="bg-white/85 backdrop-blur-sm rounded-lg p-6 shadow-sm border border-black border-opacity-50">
      <h2 className="text-xl font-medium mb-2">
        {format(date, "yyyy年MM月dd日")} {category} 论文速递
      </h2>
      <p className="text-[#45454a] whitespace-pre-line">{summary}</p>
    </div>
  )
}


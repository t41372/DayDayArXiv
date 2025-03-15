import { ExternalLink } from "lucide-react"
import type { Paper } from "@/lib/types"

interface PaperCardProps {
  paper: Paper
}

export default function PaperCard({ paper }: PaperCardProps) {
  return (
    <div className="bg-white rounded-lg p-6 shadow-sm border border-black border-opacity-50">
      <h2 className="text-xl font-medium mb-2">{paper.titleZh}</h2>
      <h3 className="text-lg font-medium mb-4 text-[#45454a]">{paper.title}</h3>

      <p className="text-sm text-[#45454a] mb-4">{paper.authors.join(", ")}</p>

      <p className="text-[#45454a] mb-6 whitespace-pre-line">{paper.abstractZh}</p>

      <div className="flex flex-wrap gap-2 mb-4">
        <span className="bg-[#c00f0c] text-white px-3 py-1 rounded-md text-sm">arXiv:{paper.id}</span>
        {paper.categories.map((category, index) => (
          <span key={index} className="bg-[#0e0e0f] text-white px-3 py-1 rounded-md text-sm">
            {category}
          </span>
        ))}
        <span className="bg-[#0e0e0f] text-white px-3 py-1 rounded-md text-sm">{paper.date}</span>
      </div>

      <div className="flex gap-4">
        <a
          href={`https://arxiv.org/abs/${paper.id}`}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center text-blue-600 hover:underline"
        >
          <ExternalLink className="h-4 w-4 mr-1" />
          arXiv
        </a>
        <a
          href={`https://arxiv.org/pdf/${paper.id}.pdf`}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center text-blue-600 hover:underline"
        >
          <ExternalLink className="h-4 w-4 mr-1" />
          PDF
        </a>
      </div>
    </div>
  )
}


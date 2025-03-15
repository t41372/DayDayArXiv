"use client"

import { cn } from "@/lib/utils"

interface CategorySelectorProps {
  selectedCategory: string
  onCategoryChange: (category: string) => void
}

export default function CategorySelector({ selectedCategory, onCategoryChange }: CategorySelectorProps) {
  const categories = ["cs.AI", "cs.CL", "cs.CV", "cs.LG", "cs.RO"]

  return (
    <div className="bg-white/85 backdrop-blur-sm rounded-lg p-4 shadow-sm border border-black border-opacity-50">
      <h3 className="text-xl font-medium mb-4">分类</h3>
      <div className="space-y-2">
        {categories.map((category) => (
          <button
            key={category}
            onClick={() => onCategoryChange(category)}
            className={`w-full text-left px-3 py-2 rounded-md ${
              selectedCategory === category
                ? "bg-[#0e0e0f] text-white"
                : "bg-gray-100 text-gray-700 hover:bg-gray-200"
            }`}
          >
            {category}
          </button>
        ))}
      </div>
    </div>
  )
}


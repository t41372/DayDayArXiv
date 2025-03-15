"use client"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface CategorySelectorProps {
  selectedCategory: string
  onCategoryChange: (category: string) => void
}

const categories = [
  { id: "cs.AI", name: "cs.AI" },
  { id: "cs.CL", name: "cs.CL" },
  { id: "cs.CV", name: "cs.CV" },
  { id: "cs.LG", name: "cs.LG" },
  { id: "cs.RO", name: "cs.RO" },
]

export default function CategorySelector({ selectedCategory, onCategoryChange }: CategorySelectorProps) {
  return (
    <div className="bg-white rounded-lg p-4 shadow-sm border border-black border-opacity-50">
      <h3 className="text-xl font-medium mb-4">分区</h3>
      <div className="flex flex-wrap gap-2">
        {categories.map((category) => (
          <Button
            key={category.id}
            variant="outline"
            size="sm"
            onClick={() => onCategoryChange(category.id)}
            className={cn(
              "rounded-md",
              selectedCategory === category.id
                ? "bg-[#0e0e0f] text-white hover:bg-[#0e0e0f]/90 hover:text-white"
                : "bg-white text-[#0e0e0f] hover:bg-gray-100",
            )}
          >
            {category.name}
          </Button>
        ))}
      </div>
    </div>
  )
}


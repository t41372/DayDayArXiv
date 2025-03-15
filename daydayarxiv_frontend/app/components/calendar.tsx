"use client"

import { useState } from "react"
import { ChevronLeft, ChevronRight } from "lucide-react"

export function Calendar() {
  const [currentMonth, setCurrentMonth] = useState("Jun 2022")

  // Calendar data for June 2022
  const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
  const weeks = [
    [27, 28, 29, 30, 1, 2, 3],
    [4, 5, 6, 7, 8, 9, 10],
    [11, 12, 13, 14, 15, 16, 17],
    [18, 19, 20, 21, 22, 23, 24],
    [25, 26, 27, 28, 29, 30, 31],
  ]

  const selectedDay = 20

  return (
    <div className="bg-white/85 backdrop-blur-sm rounded-lg p-4 shadow-sm border border-black border-opacity-50">
      <div className="flex items-center justify-between mb-4">
        <button className="p-1">
          <ChevronLeft className="h-5 w-5 text-[#45454a]" />
        </button>

        <div className="flex items-center">
          <span className="font-medium">{currentMonth}</span>
          <ChevronRight className="h-4 w-4 text-[#45454a] inline ml-1" />
        </div>

        <button className="p-1">
          <ChevronRight className="h-5 w-5 text-[#45454a]" />
        </button>
      </div>

      <div className="grid grid-cols-7 gap-1">
        {days.map((day) => (
          <div key={day} className="text-center text-sm text-[#797b86] py-1">
            {day}
          </div>
        ))}

        {weeks.flat().map((day, index) => {
          const isPreviousMonth = day > 20 && index < 7
          const isCurrentDay = day === 20

          return (
            <div
              key={`day-${index}`}
              className={`text-center py-1 text-sm ${isPreviousMonth ? "text-[#c9c9c9]" : "text-[#000000]"} ${
                isCurrentDay ? "bg-[#0e0e0f] text-white rounded-full" : ""
              }`}
            >
              {day}
            </div>
          )
        })}
      </div>
    </div>
  )
}


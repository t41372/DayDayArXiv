"use client"

import React, { useEffect, useState } from "react"
import { ChevronLeft, ChevronRight } from "lucide-react"
import {
  format,
  startOfMonth,
  endOfMonth,
  eachDayOfInterval,
  isSameMonth,
  isSameDay,
  addMonths,
  subMonths,
  startOfWeek,
  endOfWeek,
  isAfter,
  startOfDay,
} from "date-fns"
import { cn } from "@/lib/utils"

interface CalendarProps {
  selectedDate: Date
  onDateChange: (date: Date) => void
  availableDates: Date[]
}

export default function Calendar({ selectedDate, onDateChange, availableDates }: CalendarProps) {
  const [currentMonth, setCurrentMonth] = useState<Date>(selectedDate)
  
  // Get current date to compare against future dates
  const today = startOfDay(new Date())
  const days = ["一", "二", "三", "四", "五", "六", "日"]


  const handlePreviousMonth = () => {
    setCurrentMonth(subMonths(currentMonth, 1))
  }

  const handleNextMonth = () => {
    // Only allow moving to next month if it doesn't go into the future
    const nextMonth = addMonths(currentMonth, 1)
    if (!isAfter(startOfMonth(nextMonth), startOfMonth(today))) {
      setCurrentMonth(nextMonth)
    }
  }

  // Get all days in the current month
  const monthStart = startOfMonth(currentMonth)
  const monthEnd = endOfMonth(currentMonth)
  const monthDays = eachDayOfInterval({ start: monthStart, end: monthEnd })

  // Calculate days from previous month to fill the first row
  const prevMonthDays = eachDayOfInterval({
    start: startOfWeek(monthStart, { weekStartsOn: 1 }),
    end: subMonths(monthStart, 0),
  }).filter((date) => !isSameMonth(date, monthStart))

  // Calculate days from next month to fill the last row
  const nextMonthDays = eachDayOfInterval({
    start: addMonths(monthEnd, 0),
    end: endOfWeek(monthEnd, { weekStartsOn: 1 }),
  }).filter((date) => !isSameMonth(date, monthStart))

  // Combine all days
  const calendarDays = [...prevMonthDays, ...monthDays, ...nextMonthDays]

  // Group days into weeks
  const weeks: Date[][] = []
  for (let i = 0; i < calendarDays.length; i += 7) {
    weeks.push(calendarDays.slice(i, i + 7))
  }

  // Check if a date is available
  const isDateAvailable = (date: Date): boolean => {
    // Future dates are never available
    if (isAfter(date, today)) {
      return false
    }
    
    if (availableDates.length === 0) {
      // If no available dates are provided, assume all non-future dates are available
      return true
    }
    
    return availableDates.some((availableDate) => isSameDay(availableDate, date))
  }

  // Check if the next month button should be disabled
  const isNextMonthDisabled = isAfter(
    startOfMonth(addMonths(currentMonth, 1)), 
    startOfMonth(today)
  )

  useEffect(() => {
    if (!isSameMonth(selectedDate, currentMonth)) {
      setCurrentMonth(selectedDate)
    }
  }, [currentMonth, selectedDate])

  return (
    <div className="bg-white rounded-lg p-4 shadow-sm border border-black border-opacity-50">
      <div className="flex items-center justify-between mb-4">
        <button onClick={handlePreviousMonth} className="p-1 hover:bg-gray-100 rounded-full">
          <ChevronLeft className="h-5 w-5 text-[#45454a]" />
        </button>

        <div className="flex items-center">
          <span className="font-medium">{format(currentMonth, "MMM yyyy")}</span>
        </div>

        <button 
          onClick={handleNextMonth} 
          disabled={isNextMonthDisabled}
          className={cn(
            "p-1 rounded-full",
            isNextMonthDisabled 
              ? "text-gray-300 cursor-not-allowed" 
              : "hover:bg-gray-100 text-[#45454a]"
          )}
        >
          <ChevronRight className="h-5 w-5" />
        </button>
      </div>

      <div className="grid grid-cols-7 gap-1">
        {days.map((day) => (
          <div key={day} className="text-center text-sm text-[#797b86] py-1">
            {day}
          </div>
        ))}

        {weeks.map((week, weekIndex) =>
          week.map((day, dayIndex) => {
            const isCurrentMonth = isSameMonth(day, currentMonth)
            const isSelected = isSameDay(day, selectedDate)
            const isAvailable = isDateAvailable(day)
            const isFutureDate = isAfter(day, today)
            const isToday = isSameDay(day, today)

            return (
              <button
                key={`${weekIndex}-${dayIndex}`}
                onClick={() => (isAvailable && isCurrentMonth ? onDateChange(day) : null)}
                disabled={!isAvailable || !isCurrentMonth || isFutureDate}
                className={cn(
                  "text-center py-1 text-sm rounded-full w-8 h-8 mx-auto flex items-center justify-center",
                  !isCurrentMonth && "text-[#c9c9c9]",
                  isCurrentMonth && isFutureDate && "text-[#c9c9c9] cursor-not-allowed",
                  isCurrentMonth && !isFutureDate && !isAvailable && "text-[#c9c9c9] cursor-not-allowed",
                  isCurrentMonth && isAvailable && !isFutureDate && !isSelected && "hover:bg-gray-100 cursor-pointer",
                  isSelected && "bg-[#0e0e0f] text-white",
                  isToday && !isSelected && "ring-1 ring-inset ring-black"
                )}
              >
                {format(day, "d")}
              </button>
            )
          }),
        )}
      </div>
    </div>
  )
}

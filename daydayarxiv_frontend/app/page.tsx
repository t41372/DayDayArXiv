"use client"

import { useState, useEffect } from "react"
import { format } from "date-fns"
import { Menu } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "@/components/ui/sheet"
import Calendar from "@/components/calendar"
import DailySummary from "@/components/daily-summary"
import PaperCard from "@/components/paper-card"
import CategorySelector from "@/components/category-selector"
import { fetchDailyData } from "@/lib/api"
import type { DailyData } from "@/lib/types"
import { Sidebar } from '@/app/components/sidebar'

export default function Home() {
  const [selectedDate, setSelectedDate] = useState<Date>(new Date())
  const [selectedCategory, setSelectedCategory] = useState<string>("cs.AI")
  const [dailyData, setDailyData] = useState<DailyData | null>(null)
  const [loading, setLoading] = useState<boolean>(true)

  useEffect(() => {
    const loadData = async () => {
      setLoading(true)
      try {
        const data = await fetchDailyData(selectedDate, selectedCategory)
        setDailyData(data)
      } catch (error) {
        console.error("Failed to load data:", error)
        setDailyData(null)
      } finally {
        setLoading(false)
      }
    }

    loadData()
  }, [selectedDate, selectedCategory])

  const handleDateChange = (date: Date) => {
    setSelectedDate(date)
  }

  const handleCategoryChange = (category: string) => {
    setSelectedCategory(category)
  }

  return (
    <div className="min-h-screen">
      <header className="fixed top-0 left-0 right-0 z-50 border-b border-[#d9d9d9] py-4 px-6 flex justify-between items-center backdrop-blur-md bg-white/80">
        <h1 className="text-2xl md:text-3xl font-bold">arXivDayDay.com</h1>
        <Sheet>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" className="md:hidden">
              <Menu className="h-6 w-6" />
              <span className="sr-only">Open menu</span>
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="bg-[#fffef7] overflow-y-auto">
            <SheetTitle>arXiv DayDay Menu</SheetTitle>
            <div className="py-4">
              <Calendar selectedDate={selectedDate} onDateChange={handleDateChange} availableDates={[]} />
              <CategorySelector selectedCategory={selectedCategory} onCategoryChange={handleCategoryChange} />
              <Sidebar />
            </div>
          </SheetContent>
        </Sheet>
      </header>

      <main className="container mx-auto px-4 py-6 flex flex-col md:flex-row gap-6 mt-[72px]">
        <aside className="hidden md:block md:w-1/3 lg:w-1/4 space-y-6 h-[calc(100vh-5rem)] overflow-y-auto sticky top-20 pr-4 md:pr-2">
          <Calendar selectedDate={selectedDate} onDateChange={handleDateChange} availableDates={[]} />
          <CategorySelector selectedCategory={selectedCategory} onCategoryChange={handleCategoryChange} />
          <Sidebar />
        </aside>

        <div className="md:w-2/3 lg:w-3/4 space-y-6">
          {loading ? (
            <div className="flex justify-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-gray-900"></div>
            </div>
          ) : dailyData ? (
            <>
              <DailySummary date={selectedDate} category={selectedCategory} summary={dailyData.summary} />

              {dailyData.papers.map((paper, index) => (
                <PaperCard key={paper.arxiv_id || index} paper={paper} />
              ))}
            </>
          ) : (
            <div className="bg-white rounded-lg p-6 shadow-sm text-center">
              <p className="text-lg text-gray-600">
                没有找到 {format(selectedDate, "yyyy-MM-dd")} 的 {selectedCategory} 数据
              </p>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}


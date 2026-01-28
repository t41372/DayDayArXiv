import type { DailyData, DataIndex } from "./types"
import { format } from "date-fns"
import {
  getCachedData, 
  cacheData,
  getCachedIndex,
  cacheIndex,
  initCache
} from "./dataCache"
import { formatUtcDateFromLocal, parseLocalDate } from "./utils"

// Initialize cache when this module is imported
if (typeof window !== 'undefined') {
  initCache().catch(err => console.error('Failed to initialize cache:', err));
}

// Function to fetch data from JSON files in the public directory
export async function fetchDailyData(date: Date, category: string): Promise<DailyData> {
  try {
    // First check if we have this data in cache
    if (typeof window !== 'undefined') {
      const cachedData = await getCachedData(date, category);
      if (cachedData) {
        console.log(`Using cached data for ${format(date, "yyyy-MM-dd")}/${category}`);
        return cachedData;
      }
    }
    
    // Not in cache, fetch from network
    const dateStr = formatUtcDateFromLocal(date);
    console.log(`Fetching data for ${dateStr}/${category} from network`);
    
    const response = await fetch(`/data/${dateStr}/${category}.json`);

    if (!response.ok) {
      if (response.status === 404) {
        console.log(`No data available for ${dateStr}/${category}`);
        return {
          date: dateStr,
          category: category,
          summary: `No data available for ${category} on ${dateStr}.`,
          papers: [],
          processing_status: "no_papers",
        };
      }
      const message = `Failed to load ${dateStr}/${category}: ${response.status} ${response.statusText}`;
      console.error(message);
      return {
        date: dateStr,
        category: category,
        summary: `数据加载失败（${response.status}）`,
        papers: [],
        processing_status: "failed",
        error: message,
      };
    }
    
    const data = await response.json();
    
    // Cache the fetched data
    if (typeof window !== 'undefined') {
      await cacheData(date, category, data)
        .catch(err => console.error('Failed to cache data:', err));
    }
    
    return data;
  } catch (error) {
    console.error("Failed to load data:", error);
    const dateStr = formatUtcDateFromLocal(date);
    const message = `Failed to load ${dateStr}/${category}: ${error instanceof Error ? error.message : String(error)}`;
    // Return a default response for any errors
    return {
      date: dateStr,
      category: category,
      summary: "数据加载失败",
      papers: [],
      processing_status: "failed",
      error: message,
    };
  }
}

// Function to get available dates (would check which JSON files exist)
export async function getAvailableIndex(): Promise<DataIndex | null> {
  let cachedIndex: DataIndex | null = null
  if (typeof window !== "undefined") {
    cachedIndex = await getCachedIndex().catch(() => null)
  }

  try {
    const response = await fetch(`/data/index.json`, { cache: "no-store" })
    if (!response.ok) {
      console.error("No index.json available")
      return cachedIndex
    }
    const index = (await response.json()) as DataIndex

    if (typeof window !== "undefined") {
      await cacheIndex(index).catch((err) =>
        console.error("Failed to cache available index:", err),
      )
    }

    return index
  } catch (error) {
    console.error("Error in getAvailableIndex:", error)
    return cachedIndex
  }
}

export async function getAvailableDates(category?: string): Promise<Date[]> {
  const index = await getAvailableIndex();
  if (!index) {
    return [];
  }
  const availableDates = category
    ? index.available_dates.filter((dateStr) => index.by_date[dateStr]?.includes(category))
    : index.available_dates;
  return availableDates.map((dateStr) => parseLocalDate(dateStr));
}

// Function to check if data exists for a specific date and category
export async function dataExists(date: Date, category: string): Promise<boolean> {
  try {
    if (typeof window !== 'undefined') {
      const cachedData = await getCachedData(date, category);
      if (cachedData) {
        return true;
      }
    }

    const dateStr = formatUtcDateFromLocal(date);
    const index = await getAvailableIndex();
    if (index) {
      return index.by_date[dateStr]?.includes(category) ?? false;
    }

    const response = await fetch(`/data/${dateStr}/${category}.json`, { method: 'GET' });
    return response.ok;
  } catch (error) {
    console.error("Error checking data existence:", error);
    return false;
  }
}

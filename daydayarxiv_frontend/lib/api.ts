import type { DailyData, DataIndex } from "./types"
import { format } from "date-fns"
import {
  getCachedData, 
  cacheData,
  getCachedIndex,
  cacheIndex,
  initCache
} from "./dataCache"
import { parseLocalDate } from "./utils"

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
    const dateStr = format(date, "yyyy-MM-dd");
    console.log(`Fetching data for ${dateStr}/${category} from network`);
    
    const response = await fetch(`/data/${dateStr}/${category}.json`);
    
    if (!response.ok) {
      console.log(`No data available for ${dateStr}/${category}`);
      // Return a default response instead of throwing an error
      return {
        date: dateStr,
        category: category,
        summary: `No data available for ${category} on ${dateStr}.`,
        papers: []
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
    console.log("No data for this date:", error);
    const dateStr = format(date, "yyyy-MM-dd");
    // Return a default response for any errors
    return {
      date: dateStr,
      category: category,
      summary: `No data available for ${category} on ${dateStr}.`,
      papers: []
    };
  }
}

// Function to get available dates (would check which JSON files exist)
export async function getAvailableIndex(): Promise<DataIndex | null> {
  try {
    // First check if we have this data in cache
    if (typeof window !== 'undefined') {
      const cachedIndex = await getCachedIndex();
      if (cachedIndex) {
        console.log('Using cached available index');
        return cachedIndex;
      }
    }
    
    const response = await fetch(`/data/index.json`, { cache: 'no-store' });
    if (!response.ok) {
      console.error('No index.json available');
      return null;
    }
    const index = (await response.json()) as DataIndex;
    
    // Cache the index
    if (typeof window !== 'undefined') {
      await cacheIndex(index)
        .catch(err => console.error('Failed to cache available index:', err));
    }
    
    return index;
  } catch (error) {
    console.error("Error in getAvailableIndex:", error);
    return null;
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

    const dateStr = format(date, "yyyy-MM-dd");
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

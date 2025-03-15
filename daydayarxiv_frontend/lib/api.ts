import type { DailyData } from "./types"
import { format } from "date-fns"
import { 
  getCachedData, 
  cacheData, 
  getCachedAvailableDates, 
  cacheAvailableDates,
  initCache
} from "./dataCache"

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
export async function getAvailableDates(): Promise<Date[]> {
  try {
    // First check if we have this data in cache
    if (typeof window !== 'undefined') {
      const cachedDates = await getCachedAvailableDates();
      if (cachedDates) {
        console.log('Using cached available dates');
        return cachedDates;
      }
    }
    
    // Not in cache, use the known static dates
    // In a production environment, we would fetch this from an API endpoint
    // or from a pre-generated index file
    const dates = [
      new Date("2025-03-13"),
      new Date("2025-03-14")
    ];
    
    // Cache the dates
    if (typeof window !== 'undefined') {
      await cacheAvailableDates(dates)
        .catch(err => console.error('Failed to cache available dates:', err));
    }
    
    return dates;
  } catch (error) {
    console.error("Error in getAvailableDates:", error);
    
    // Fallback to known dates
    return [
      new Date("2025-03-13"),
      new Date("2025-03-14")
    ];
  }
}

// Function to check if data exists for a specific date and category
export async function dataExists(date: Date, category: string): Promise<boolean> {
  try {
    // First check if we have this data in cache
    if (typeof window !== 'undefined') {
      const cachedData = await getCachedData(date, category);
      if (cachedData) {
        return true;
      }
    }
    
    // Not in cache, check if it exists on the server
    const dateStr = format(date, "yyyy-MM-dd");
    const response = await fetch(`/data/${dateStr}/${category}.json`, { method: 'HEAD' });
    
    // If exists, cache that information
    if (response.ok && typeof window !== 'undefined') {
      // We don't cache the actual data here (just doing a HEAD request)
      // The actual data will be cached when fetchDailyData is called
      const availableDates = await getAvailableDates();
      if (!availableDates.some(d => format(d, "yyyy-MM-dd") === dateStr)) {
        availableDates.push(date);
        await cacheAvailableDates(availableDates)
          .catch(err => console.error('Failed to update available dates cache:', err));
      }
    }
    
    return response.ok;
  } catch (error) {
    console.error("Error checking data existence:", error);
    return false;
  }
}


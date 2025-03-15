// IndexedDB caching system for arxiv data files
import { format } from 'date-fns';
import type { DailyData } from './types';

const DB_NAME = 'daydayarxivCache';
const DATA_STORE_NAME = 'dataCache';
const META_STORE_NAME = 'metaCache';
const DB_VERSION = 1;

// Cache expiration (7 days in milliseconds)
const CACHE_EXPIRATION = 7 * 24 * 60 * 60 * 1000;

interface CacheEntry {
  data: DailyData;
  timestamp: number;
}

interface MetaEntry {
  availableDates: string[];
  categories: string[];
  lastUpdated: number;
}

// Open (or create) the IndexedDB database
function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    
    request.onerror = (event) => {
      console.error('IndexedDB error:', event);
      reject('Error opening IndexedDB');
    };
    
    request.onsuccess = (event) => {
      resolve((event.target as IDBOpenDBRequest).result);
    };
    
    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;
      
      // Create object store for data cache
      if (!db.objectStoreNames.contains(DATA_STORE_NAME)) {
        db.createObjectStore(DATA_STORE_NAME);
      }
      
      // Create object store for metadata cache
      if (!db.objectStoreNames.contains(META_STORE_NAME)) {
        db.createObjectStore(META_STORE_NAME);
      }
    };
  });
}

// Cache data by date and category
export async function cacheData(date: Date, category: string, data: DailyData): Promise<void> {
  try {
    const db = await openDB();
    const transaction = db.transaction(DATA_STORE_NAME, 'readwrite');
    const store = transaction.objectStore(DATA_STORE_NAME);
    
    const key = `${format(date, 'yyyy-MM-dd')}/${category}`;
    const entry: CacheEntry = {
      data,
      timestamp: Date.now(),
    };
    
    store.put(entry, key);
    
    return new Promise((resolve, reject) => {
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(new Error('Error caching data'));
    });
  } catch (error) {
    console.error('Cache error:', error);
    throw error;
  }
}

// Get cached data by date and category
export async function getCachedData(date: Date, category: string): Promise<DailyData | null> {
  try {
    const db = await openDB();
    const transaction = db.transaction(DATA_STORE_NAME, 'readonly');
    const store = transaction.objectStore(DATA_STORE_NAME);
    
    const key = `${format(date, 'yyyy-MM-dd')}/${category}`;
    
    return new Promise((resolve, reject) => {
      const request = store.get(key);
      
      request.onsuccess = () => {
        const entry = request.result as CacheEntry | undefined;
        
        if (!entry) {
          resolve(null);
          return;
        }
        
        // Check if cache has expired
        if (Date.now() - entry.timestamp > CACHE_EXPIRATION) {
          // Cache expired, delete it
          const deleteTransaction = db.transaction(DATA_STORE_NAME, 'readwrite');
          const deleteStore = deleteTransaction.objectStore(DATA_STORE_NAME);
          deleteStore.delete(key);
          resolve(null);
          return;
        }
        
        resolve(entry.data);
      };
      
      request.onerror = () => reject(new Error('Error retrieving cached data'));
    });
  } catch (error) {
    console.error('Cache retrieval error:', error);
    return null;
  }
}

// Cache available dates metadata
export async function cacheAvailableDates(dates: Date[], categories: string[] = ['cs.AI']): Promise<void> {
  try {
    const db = await openDB();
    const transaction = db.transaction(META_STORE_NAME, 'readwrite');
    const store = transaction.objectStore(META_STORE_NAME);
    
    const dateStrings = dates.map(date => format(date, 'yyyy-MM-dd'));
    const entry: MetaEntry = {
      availableDates: dateStrings,
      categories,
      lastUpdated: Date.now(),
    };
    
    store.put(entry, 'metadata');
    
    return new Promise((resolve, reject) => {
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(new Error('Error caching metadata'));
    });
  } catch (error) {
    console.error('Cache metadata error:', error);
    throw error;
  }
}

// Get cached available dates
export async function getCachedAvailableDates(): Promise<Date[] | null> {
  try {
    const db = await openDB();
    const transaction = db.transaction(META_STORE_NAME, 'readonly');
    const store = transaction.objectStore(META_STORE_NAME);
    
    return new Promise((resolve, reject) => {
      const request = store.get('metadata');
      
      request.onsuccess = () => {
        const entry = request.result as MetaEntry | undefined;
        
        if (!entry) {
          resolve(null);
          return;
        }
        
        // Check if metadata cache has expired
        if (Date.now() - entry.lastUpdated > CACHE_EXPIRATION) {
          resolve(null);
          return;
        }
        
        const dates = entry.availableDates.map(dateStr => new Date(dateStr));
        resolve(dates);
      };
      
      request.onerror = () => reject(new Error('Error retrieving cached metadata'));
    });
  } catch (error) {
    console.error('Cache metadata retrieval error:', error);
    return null;
  }
}

// Clear expired cache entries
export async function clearExpiredCache(): Promise<void> {
  try {
    const db = await openDB();
    const transaction = db.transaction(DATA_STORE_NAME, 'readwrite');
    const store = transaction.objectStore(DATA_STORE_NAME);
    
    const request = store.openCursor();
    
    request.onsuccess = (event) => {
      const cursor = (event.target as IDBRequest).result as IDBCursorWithValue;
      
      if (cursor) {
        const entry = cursor.value as CacheEntry;
        
        // Check if cache has expired
        if (Date.now() - entry.timestamp > CACHE_EXPIRATION) {
          cursor.delete();
        }
        
        cursor.continue();
      }
    };
    
    return new Promise((resolve) => {
      transaction.oncomplete = () => resolve();
    });
  } catch (error) {
    console.error('Error clearing expired cache:', error);
  }
}

// Function to handle cache initialization and cleanup on app startup
export async function initCache(): Promise<void> {
  try {
    await clearExpiredCache();
  } catch (error) {
    console.error('Cache initialization error:', error);
  }
}
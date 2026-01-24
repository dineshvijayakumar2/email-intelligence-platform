/**
 * Filter Cache Service
 *
 * Caches filter options (categories, mailboxes, folders) in sessionStorage
 * to avoid re-fetching on every page visit. Uses a 5-minute TTL.
 */

interface CachedData<T> {
  data: T;
  timestamp: number;
}

// Cache TTL: 5 minutes
const CACHE_TTL = 5 * 60 * 1000;

// Cache keys
const CACHE_PREFIX = 'filter_cache_';

export const filterCache = {
  /**
   * Get cached data if it exists and is not expired
   */
  get<T>(key: string): T | null {
    try {
      const cached = sessionStorage.getItem(`${CACHE_PREFIX}${key}`);
      if (!cached) return null;

      const { data, timestamp }: CachedData<T> = JSON.parse(cached);

      // Check if cache has expired
      if (Date.now() - timestamp > CACHE_TTL) {
        sessionStorage.removeItem(`${CACHE_PREFIX}${key}`);
        return null;
      }

      return data;
    } catch (error) {
      console.warn(`[FilterCache] Error reading cache for ${key}:`, error);
      return null;
    }
  },

  /**
   * Store data in cache with current timestamp
   */
  set<T>(key: string, data: T): void {
    try {
      const cacheEntry: CachedData<T> = {
        data,
        timestamp: Date.now(),
      };
      sessionStorage.setItem(`${CACHE_PREFIX}${key}`, JSON.stringify(cacheEntry));
    } catch (error) {
      console.warn(`[FilterCache] Error writing cache for ${key}:`, error);
    }
  },

  /**
   * Invalidate specific cache key or all filter caches
   */
  invalidate(key?: string): void {
    if (key) {
      sessionStorage.removeItem(`${CACHE_PREFIX}${key}`);
    } else {
      // Clear all filter caches
      const keysToRemove: string[] = [];
      for (let i = 0; i < sessionStorage.length; i++) {
        const storageKey = sessionStorage.key(i);
        if (storageKey?.startsWith(CACHE_PREFIX)) {
          keysToRemove.push(storageKey);
        }
      }
      keysToRemove.forEach(k => sessionStorage.removeItem(k));
    }
  },

  /**
   * Check if cache is valid (exists and not expired)
   */
  isValid(key: string): boolean {
    return this.get(key) !== null;
  },

  /**
   * Get cache age in seconds (or null if not cached)
   */
  getAge(key: string): number | null {
    try {
      const cached = sessionStorage.getItem(`${CACHE_PREFIX}${key}`);
      if (!cached) return null;

      const { timestamp }: CachedData<unknown> = JSON.parse(cached);
      return Math.round((Date.now() - timestamp) / 1000);
    } catch {
      return null;
    }
  },
};

// Filter-specific cache keys
export const FILTER_KEYS = {
  CATEGORIES: 'categories',
  MAILBOXES: 'mailboxes',
  FOLDERS: 'folders',
} as const;

export default filterCache;

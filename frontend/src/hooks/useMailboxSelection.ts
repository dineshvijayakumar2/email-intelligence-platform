/**
 * Hook to manage mailbox selection state with persistence
 */
import { useState, useEffect } from 'react';

export const useMailboxSelection = (defaultValue: string[] = []) => {
  const storageKey = 'selectedMailboxIds';

  const [selectedMailboxIds, setSelectedMailboxIds] = useState<string[]>(() => {
    try {
      const stored = localStorage.getItem(storageKey);
      return stored ? JSON.parse(stored) : defaultValue;
    } catch {
      return defaultValue;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(selectedMailboxIds));
    } catch {
      // Ignore storage errors
    }
  }, [selectedMailboxIds]);

  return [selectedMailboxIds, setSelectedMailboxIds] as const;
};

export default useMailboxSelection;

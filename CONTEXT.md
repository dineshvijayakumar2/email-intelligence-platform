# Email Intelligence Platform - Development Context

## Recent Changes (2026-02-06)

### Mailbox Switching UX Improvements

**Problem**: Mailbox switching showed stale data briefly before loading new content, causing user confusion.

**Solution Implemented**:
1. **Route-Based Navigation** - Each mailbox has its own URL (`/emails/:mailboxId`)
2. **Instant Skeleton Feedback** - Clear old content immediately and show loading skeleton
3. **Removed "All Mailboxes" View** - Always require mailbox selection
4. **React Strict Mode Fix** - Handle double-mounting gracefully in MailboxSelector

### Key Files Modified

#### Frontend
- `frontend/src/App.tsx` - Added `/emails/:mailboxId` route
- `frontend/src/pages/emails.tsx` - Major UX improvements:
  - Route-based mailbox navigation with URL params
  - Instant skeleton display when switching folders/filters
  - Removed initial `loadEmails()` call that loaded all emails
  - Added strict guards to prevent loading without valid mailbox
  - Clear `totalCount` when switching to force skeleton display
- `frontend/src/components/MailboxSelector.tsx` - Fixed React Strict Mode issue
  - Preserve good data when API returns null on second mount
- `frontend/src/services/apiClient.ts` - Added debug logging
- `frontend/src/services/mailboxService.ts` - Added debug logging

#### Backend
- `backend/fix_accessible_mailboxes.sql` - Fixed RPC function for roles array support

### Technical Details

#### Mailbox Switching Flow
1. User selects mailbox from dropdown → `handleMailboxSelectorChange()`
2. Immediately clear emails, set loading=true, clear totalCount=0
3. Navigate to `/emails/:mailboxId`
4. URL sync effect picks up mailboxId → sets filters.mailbox
5. Email loading effect triggers → loads emails
6. Skeleton displays until data loads

#### Folder Switching Flow
1. User clicks folder → `handleFolderSelect()`
2. Immediately clear emails, set loading=true, clear totalCount=0
3. Update filters.folder
4. Email loading effect triggers → loads emails
5. Stats bar shows "Loading emails..." instead of stale count

### Guards to Prevent "All Mailboxes" Loading
```typescript
// In loadEmails callback
if (!filters.mailbox) {
  setLoading(false);
  setEmails([]);
  setTotalCount(0);
  return;
}

// Removed initial loadEmails() from mount effect
// Now emails only load when mailbox is selected
```

### React Strict Mode Fix
```typescript
// MailboxSelector - don't overwrite good data with null
if (data && data.length > 0) {
  setMailboxes(data.filter(m => m.is_active));
} else {
  console.warn('Received empty/null data, keeping existing mailboxes');
}
```

## Git Commits

1. `de2943d` - Improve mailbox switching UX with instant feedback
2. `f63a990` - Fix folder/filter switching to show skeleton immediately

## Next Steps

### To Do
- [ ] Apply same UX improvements to Processing page:
  - [ ] Route-based filtering (`/processing/:mailboxId` or `/processing?mailbox=id`)
  - [ ] Skeleton views during refresh/filter changes
  - [ ] Instant feedback when switching status filters
- [ ] Consider removing debug console.logs once stable
- [ ] Add E2E tests for mailbox switching flow

### Known Issues
None currently

## Architecture Notes

### State Management
- **URL as source of truth** for mailbox selection
- **Optimistic UI updates** before navigation/data loading
- **Strict guards** prevent loading without required context

### Performance Optimizations
- Don't load folders until mailbox selected
- Auto-refresh jobs every 5 seconds (without full page reload)
- Mailbox maps cached to avoid repeated lookups

## Development Guidelines

### When Adding New Filters/Views
1. Clear old data immediately (setEmails([]), setTotalCount(0))
2. Set loading=true
3. Update filters/navigate
4. Let effects handle data loading
5. Ensure skeleton displays during loading

### When Adding New Routes
- Use route params for primary filters (mailbox, job, client)
- Use query params for secondary filters (date range, status)
- Always sync URL with component state
- Handle direct URL access (page refresh)
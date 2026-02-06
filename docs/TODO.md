# TODO List

## High Priority

### Processing Page UX Improvements
- [ ] Add route-based filtering to Processing page
  - [ ] Consider `/processing/:mailboxId` or `/processing?mailbox=id&status=running`
  - [ ] Add MailboxSelector to top-right like Emails page
  - [ ] Add status filter dropdown (All, Running, Completed, Failed, etc.)
- [ ] Add skeleton views during refresh/filter changes
  - [ ] Show skeleton table rows when loading
  - [ ] Clear old data immediately when switching filters
  - [ ] Instant feedback when clicking refresh
- [ ] Optimize filter switching performance
  - [ ] Optimistic UI updates
  - [ ] Clear totalCount when switching
  - [ ] Show loading state immediately

### Code Cleanup
- [ ] Remove debug console.logs once UX is stable
  - [ ] MailboxSelector.tsx logging
  - [ ] mailboxService.ts logging
  - [ ] apiClient.ts response logging
  - [ ] emails.tsx loading logs
- [ ] Remove unused handler `handleMailboxSelect` from emails.tsx
- [ ] Fix deprecated `dropdownRender` usage in emails.tsx (use `dropdownRender` prop properly)

## Medium Priority

### Testing
- [ ] Add E2E tests for mailbox switching flow
  - [ ] Test route navigation
  - [ ] Test skeleton display
  - [ ] Test empty states
  - [ ] Test React Strict Mode compatibility
- [ ] Add unit tests for email loading guards
- [ ] Add integration tests for folder switching

### Performance
- [ ] Consider implementing virtual scrolling for large email lists
- [ ] Add request debouncing for search input
- [ ] Implement intelligent prefetching for next folder
- [ ] Cache folder lists per mailbox

### UX Enhancements
- [ ] Add keyboard shortcuts for folder navigation
- [ ] Add bulk actions for emails
- [ ] Implement email preview on hover
- [ ] Add "Mark as read/unread" functionality

## Low Priority

### Documentation
- [ ] Add JSDoc comments to key functions
- [ ] Create architecture diagrams
- [ ] Document state management patterns
- [ ] Add API documentation

### Monitoring
- [ ] Add analytics for user navigation patterns
- [ ] Track mailbox switch performance metrics
- [ ] Monitor API response times
- [ ] Add error tracking (Sentry integration?)

### Nice to Have
- [ ] Add dark mode support
- [ ] Implement email threading
- [ ] Add email labels/tags
- [ ] Export email data (CSV, JSON)
- [ ] Advanced search with boolean operators
- [ ] Saved searches/filters

## Completed ✅

- [x] Route-based navigation for emails (`/emails/:mailboxId`)
- [x] Move mailbox selector to top-right dropdown
- [x] Instant skeleton feedback for mailbox switching
- [x] Remove "all mailboxes" view
- [x] Fix React Strict Mode mailbox dropdown issue
- [x] Clear totalCount when switching folders
- [x] Add proper empty states
- [x] Fix initial loadEmails() call
- [x] Add strict mailbox guards
- [x] Organize troubleshooting scripts into `scripts/troubleshooting/`

## Blocked/Waiting

None currently

## Notes

### Performance Considerations
- React Strict Mode causes double mounting in development - handled gracefully
- API response caching could improve perceived performance
- Consider implementing optimistic updates for more actions

### Architecture Decisions
- URL as source of truth for mailbox selection (enables deep linking, browser back/forward)
- Optimistic UI updates for instant feedback (better UX than waiting for server)
- Strict guards prevent invalid states (defensive programming)

### Future Considerations
- Consider using React Query or SWR for data fetching
- Evaluate moving to Zustand or Redux for complex state management
- Consider implementing command pattern for undo/redo
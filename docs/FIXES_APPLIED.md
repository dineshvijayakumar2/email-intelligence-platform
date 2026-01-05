# Bug Fixes Applied

## Fix #1: MBOX Archive Folder Leak & Case Normalization

**Date**: 2026-01-05
**Status**: ✅ Fixed (migration pending)

### Problem

1. **267 emails** ended up with `folder_path = "MBOX Archive"` (generic placeholder that should never be stored)
2. **Case inconsistency**: Some emails had `"INBOX"` (uppercase), others had `"Inbox"` (proper case)
3. **Missing normalizations**: Gmail labels like "Archived", "Muted" weren't normalized

### Root Cause

**Bug in `src/processors/normalizer.py`** (line 109):
```python
'inbox': 'INBOX',  # ❌ WRONG! Returns uppercase instead of proper case
```

**Effect**:
- MBOX extractor returns `'INBOX'` for emails without Gmail labels
- Normalizer tries to normalize `'INBOX'` → `'INBOX'` (unchanged)
- Some emails bypass normalization entirely → "MBOX Archive" leaks through

### Solution

**File**: `src/processors/normalizer.py`

#### Change 1: Fixed folder normalization mapping
```python
# BEFORE
'inbox': 'INBOX',  # Returns uppercase

# AFTER
'inbox': 'Inbox',  # Returns proper case
```

#### Change 2: Added comprehensive Gmail label mappings
```python
folder_map = {
    # Inbox variations
    'inbox': 'Inbox',
    'mail': 'Inbox',

    # Sent variations
    'sent': 'Sent',
    'sent items': 'Sent',

    # Archive variations
    'archive': 'Archive',
    'archived': 'Archive',

    # Spam variations
    'spam': 'Spam',
    'junk': 'Spam',

    # Draft variations
    'draft': 'Drafts',
    'drafts': 'Drafts',

    # Gmail-specific labels
    'important': 'Important',
    'starred': 'Starred',
    'muted': 'Muted',
    'snoozed': 'Snoozed',
    'chats': 'Chats',
}
```

#### Change 3: Improved inference logic
```python
# Generic placeholders that trigger inference (never stored in DB)
generic_folders = ['MBOX Archive', 'Archive', 'Unknown', '', None, 'INBOX']

# If extractor returns one of these → inference happens instead
```

#### Change 4: Added debug logging
```python
logger.debug(f"Using provided folder: {provided_folder} → {normalized}")
logger.debug(f"Inferring folder for email (provided: {provided_folder}, outbound: {is_outbound})")
logger.debug("  → Inferred: Sent (outbound email)")
```

### Data Migration

**File**: `sql/migrations/001_fix_mbox_archive_folders.sql`

**What it does**:
1. Fixes 267 emails with `folder_path = "MBOX Archive"`:
   - Outbound emails → `Sent`
   - Inbound emails → `Inbox`
2. Normalizes `INBOX` → `Inbox` (5 emails)
3. Normalizes `Archived` → `Archive` (601 emails)
4. Normalizes all other folder name variations
5. Recalculates `folders` table counts

**To apply**:
```bash
# Option 1: Run in Supabase SQL Editor
# Copy contents of sql/migrations/001_fix_mbox_archive_folders.sql

# Option 2: Run via psql
psql $SUPABASE_URL -f sql/migrations/001_fix_mbox_archive_folders.sql
```

**Expected result**:
```
BEFORE:
  MBOX Archive: 267 emails ❌
  INBOX: 5 emails ❌
  Inbox: 7137 emails ✓
  Archived: 601 emails ⚠️

AFTER:
  Inbox: 7142 emails (7137 + 5) ✓
  Sent: 756 + ~200 outbound from MBOX Archive ✓
  Archive: 601 emails (normalized) ✓
  Spam: 133 emails ✓
  Muted: 1 email ✓
  [No more "MBOX Archive" or "INBOX"] ✅
```

### Testing

**Verify the fix works**:
```bash
# Process a new MBOX file
# Check folder_path values in database

SELECT folder_path, COUNT(*) FROM emails GROUP BY folder_path;

# Should see:
# - No "MBOX Archive"
# - No "INBOX" (uppercase)
# - All folders in proper case (Inbox, Sent, Archive, etc.)
```

### Impact

- ✅ **Future processing**: All new emails will have properly normalized folders
- ✅ **Consistency**: All mailbox types (MBOX, PST, OLM) use same folder names
- ✅ **No breaking changes**: Frontend and queries work the same
- ⚠️ **Existing data**: Requires migration (see above)

---

## Summary of Folder Detection Logic (Updated)

### MBOX
1. Extractor reads `X-Gmail-Labels` header
   - Found → Returns first label (e.g., "Inbox", "Sent", "Archived")
   - Not found → Returns "INBOX" (generic placeholder)
2. Normalizer processes folder:
   - Real label (e.g., "Archived") → Normalizes to "Archive"
   - Generic ("INBOX") → Infers from email characteristics → "Inbox" or "Sent"

### PST / OLM
1. Extractor reads native folder structure
   - PST: Binary folder tree
   - OLM: XML folder mapping
2. Normalizer processes folder:
   - Normalizes to proper case (e.g., "sent items" → "Sent")
   - No inference needed

### Result
- **All mailbox types** → Consistent folder names
- **No generic placeholders** → "MBOX Archive" never stored
- **Proper case** → "Inbox" not "INBOX" or "inbox"

---

## Next Fixes

See TODO list for remaining issues:
- [ ] Pause/Stop button API integration
- [ ] Progress counter real-time updates
- [ ] Dashboard "Categories" → "Tags" terminology
- [ ] Reprocessing Redis progress updates

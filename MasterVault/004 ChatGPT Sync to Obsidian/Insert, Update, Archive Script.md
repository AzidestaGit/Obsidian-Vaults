---
uuid: b046c027-92c2-43d7-a122-5b3dd1b7f175
---

# Vault Sync System – Technical Overview

This document outlines the architecture, behavior, and recovery procedures for your smart, Obsidian-compatible vault synchronization system. It uses Python, Supabase, OpenAI embeddings, and YAML frontmatter to enable AI-accessible, version-aware syncing of all Markdown files in your vault.

---

## 📦 Project Structure

```
ObsidianVaults/
├── Brain/
│   ├── sync_vault_smart.py
│   ├── .env
│   ├── vault_index.json
```

- `sync_vault_smart.py` – The main sync script.
- `.env` – Stores your API keys and config.
- `vault_index.json` – Tracks file UUIDs and hashes.

---

## 🧠 YAML Frontmatter Format

Each file must start with this format:

```yaml
---
id: a25e33e7-7cfa-4486-8c2b-d0a938a41f58
---
```

- Automatically inserted if missing.
- UUID persists even if the file is renamed or moved.

---

## 🔄 Sync Logic

### On Each Sync:

1. **Load all files** from the configured vault directory (`NOTES_FOLDER`).
2. **Read frontmatter** to get the UUID. If none:
   - Generate a new UUID.
   - Insert into both the file and `vault_index.json`.

3. **For each file**:
   - Normalize the path.
   - Hash the content (`content_hash`).
   - Compare against:
     - Local JSON index.
     - Supabase row (by UUID).

### Then:

| Condition                                             | Action                                                     |
|-------------------------------------------------------|------------------------------------------------------------|
| File is new (no UUID)                                 | Generate UUID, insert frontmatter, insert row              |
| File was renamed or moved                             | Update `filepath` and/or `title` in Supabase              |
| File content changed                                  | Recompute embedding, update `content` and `embedding`      |
| File was deleted locally                              | Mark corresponding Supabase row `archived: true`           |
| File missing in Supabase but exists in JSON & local   | Reinsert row using cached UUID                             |
| Supabase row is up-to-date                            | Skip                                                       |

---

## 🛠 Supabase Table Schema (note-chunks)

| Column       | Type    | Description                                   |
|--------------|---------|-----------------------------------------------|
| id           | UUID    | File-specific ID stored in YAML frontmatter   |
| filepath     | text    | Full file path                                |
| title        | text    | File name (no extension)                      |
| content      | text    | Markdown content                              |
| embedding    | vector  | 1536-float embedding from OpenAI              |
| content_hash | text    | SHA-256 hash of full content                  |
| archived     | boolean | Marks soft-deleted local files                |

✅ **All columns are nullable** except `id`.

---

## 🧪 Stress-Tested Scenarios

This system handles:
- 🧭 File renames (updates `title` + `filepath`)
- 📂 Folder moves (updates `filepath` for all affected files)
- ✍️ Content edits (recomputes hash and embedding)
- 🗑 File deletions (soft-archives in Supabase)
- 📦 Supabase wipe (auto reinsert if `vault_index.json` has UUID)
- 🔍 Print logs showing per-field differences on update

---

## 🆘 Emergency Recovery

If Supabase is wiped:
- `vault_index.json` contains UUID-to-file mappings.
- The script uses this to reinsert the correct rows without duplicates.

If `vault_index.json` is deleted:
- Script will regenerate UUIDs and insert them into both YAML and Supabase.
- You may get duplicates unless you archive the Supabase table manually beforehand.

---

## 🧼 Notes

- Embedding vectors are not printed in logs — only the count is shown.
- Archived rows are ignored during search unless explicitly queried.

---

## ✅ Example Log Output

```
📝 Updating file: Welcome.md
  - filepath: [C:/.../Old.md] → [C:/.../Welcome.md]
  - title: [Old] → [Welcome]
  - content: content updated
```

---

## 🚀 Recommendations

- Run `sync_vault_smart.py` manually, or automate it with a file watcher.
- Back up `vault_index.json` regularly.
- If you move your vault, keep relative paths and update your `.env`.
import os
import glob
import uuid
import hashlib
import json
import frontmatter
from supabase import create_client
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from datetime import datetime

# Load environment variables
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
NOTES_FOLDER = os.getenv("NOTES_FOLDER")
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE")
INDEX_FILE = "vault_index.json"

# Supabase client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Embedding model
model = SentenceTransformer('all-MiniLM-L6-v2')

# Load or initialize index
if os.path.exists(INDEX_FILE):
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        local_index = json.load(f)
else:
    local_index = {}

def compute_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def get_embedding(text):
    return model.encode(text).tolist()

def sync_file(file_path):
    rel_path = os.path.relpath(file_path, NOTES_FOLDER).replace("\\", "/")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            post = frontmatter.load(f)

        content = post.content.strip()
        title = os.path.splitext(os.path.basename(file_path))[0]
        content_hash = compute_hash(content)

        # Pull or assign UUID
        if "uuid" not in post.metadata:
            file_uuid = str(uuid.uuid4())
            post.metadata["uuid"] = file_uuid
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(frontmatter.dumps(post))
        else:
            file_uuid = post.metadata["uuid"]

        # Check if file exists in Supabase
        result = supabase.table(SUPABASE_TABLE).select("*").eq("id", file_uuid).execute()
        row = result.data[0] if result.data else None

        if row:
            updates = {}
            if row["filepath"] != rel_path:
                updates["filepath"] = f"{row['filepath']} → {rel_path}"
            if row["title"] != title:
                updates["title"] = f"{row['title']} → {title}"
            if row["content_hash"] != content_hash:
                updates["content"] = "content updated"
                updates["embedding"] = "updated"
                updates["content_hash"] = "updated"

            if updates:
                payload = {
                    "filepath": rel_path,
                    "title": title,
                    "content": content,
                    "embedding": get_embedding(content),
                    "content_hash": content_hash,
                    "archived": False
                }
                supabase.table(SUPABASE_TABLE).update(payload).eq("id", file_uuid).execute()
                print(f"🔄 Updated: {rel_path}")
                for key, val in updates.items():
                    print(f"  ⮕ {key}: {val}")
            else:
                print(f"⏭️ Unchanged: {rel_path}")
        else:
            # Insert new row
            payload = {
                "id": file_uuid,
                "filepath": rel_path,
                "title": title,
                "content": content,
                "embedding": get_embedding(content),
                "content_hash": content_hash,
                "archived": False
            }
            supabase.table(SUPABASE_TABLE).insert(payload).execute()
            print(f"🆕 Inserted: {rel_path}")

        # Update local index
        local_index[file_uuid] = {
            "id": file_uuid,
            "filepath": rel_path,
            "title": title,
            "content_hash": content_hash
        }

    except Exception as e:
        print(f"🔥 Error while syncing: {file_path}\n{e}")

def archive_missing_files():
    existing_ids = set()
    response = supabase.table(SUPABASE_TABLE).select("id").eq("archived", False).execute()
    for row in response.data:
        existing_ids.add(row["id"])

    active_ids = set(local_index.keys())
    missing_ids = existing_ids - active_ids

    for mid in missing_ids:
        try:
            supabase.table(SUPABASE_TABLE).update({"archived": True}).eq("id", mid).execute()
            print(f"📦 Archived: {mid}")
        except Exception as e:
            print(f"🔥 Archive error: {mid}\n{e}")

def save_index():
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(local_index, f, indent=2)

# --- Run ---
print(f"🔄 Sync started at {datetime.now().strftime('%H:%M:%S')}...\n")

# Sync all markdown files
for file_path in glob.glob(f"{NOTES_FOLDER}/**/*.md", recursive=True):
    sync_file(file_path)

# Archive missing
archive_missing_files()

save_index()
print("\n✅ Vault sync complete.")

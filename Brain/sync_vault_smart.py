import os
import glob
import json
import uuid
import hashlib
from dotenv import load_dotenv
from datetime import datetime
from supabase import create_client
from openai import OpenAI

# Load environment variables
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE")
NOTES_FOLDER = os.getenv("NOTES_FOLDER")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
openai = OpenAI(api_key=OPENAI_API_KEY)

INDEX_FILE = "vault_index.json"

# Load or initialize the local index
if os.path.exists(INDEX_FILE):
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        local_index = json.load(f)
else:
    local_index = {}

def normalize_path(path):
    return os.path.normpath(path).replace("\\", "/")

def get_embedding(text):
    response = openai.embeddings.create(
        input=[text],
        model="text-embedding-3-small"
    )
    return response.data[0].embedding

def hash_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def sync_file(filepath):
    normalized_path = normalize_path(filepath)
    filename = os.path.basename(filepath)
    title = os.path.splitext(filename)[0]
    uuid_entry = local_index.get(normalized_path)

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read().strip()

    # Set default hash if file is empty
    content_hash = hash_text(content) if content else ""
    embedding = get_embedding(content) if content else None

    # If this file has been seen before, update it
    if uuid_entry:
        existing = supabase.table(SUPABASE_TABLE).select("*").eq("id", uuid_entry["id"]).execute().data
        if existing:
            record = existing[0]
            updates = {}
            changes = []

            if record["filepath"] != normalized_path:
                updates["filepath"] = normalized_path
                changes.append(f"filepath: [{record['filepath']}] → [{normalized_path}]")
            if record["title"] != title:
                updates["title"] = title
                changes.append(f"title: [{record['title']}] → [{title}]")
            if content_hash != uuid_entry.get("content_hash"):
                updates["content"] = content
                updates["embedding"] = embedding if embedding else None
                changes.append("content: updated")
                if embedding:
                    changes.append(f"embedding: updated ({len(embedding)} floats)")

            if updates:
                supabase.table(SUPABASE_TABLE).update(updates).eq("id", record["id"]).execute()
                print(f"✏️ Updated ({normalized_path}):")
                for c in changes:
                    print(f"  - {c}")
                # Update local index
                uuid_entry["content_hash"] = content_hash
                uuid_entry["filepath"] = normalized_path
                uuid_entry["title"] = title
            else:
                print(f"✅ No changes: {normalized_path}")
        else:
            print(f"⚠️ UUID exists but Supabase row not found for: {normalized_path}")
    else:
        # Insert new record
        uid = str(uuid.uuid4())
        payload = {
            "id": uid,
            "filepath": normalized_path,
            "title": title,
            "content": content,
            "embedding": embedding if embedding else None,
            "archived": False
        }
        supabase.table(SUPABASE_TABLE).insert(payload).execute()
        print(f"🆕 Inserted: {normalized_path}")
        local_index[normalized_path] = {
            "id": uid,
            "filepath": normalized_path,
            "title": title,
            "content_hash": content_hash
        }

def archive_deleted_files():
    current_paths = set(normalize_path(f) for f in glob.glob(f"{NOTES_FOLDER}/**/*.md", recursive=True))
    archived_any = False

    for path in list(local_index.keys()):
        if path not in current_paths:
            uid = local_index[path]["id"]
            try:
                supabase.table(SUPABASE_TABLE).update({"archived": True}).eq("id", uid).execute()
                print(f"📦 Archived (missing): {path}")
                del local_index[path]
                archived_any = True
            except Exception as e:
                print(f"🔥 Supabase APIError while archiving: {path}\n{e}")
    if not archived_any:
        print("✅ No files to archive.")

def sync_all():
    print(f"🔄 Sync started at {datetime.now().strftime('%H:%M:%S')}...\n")
    files = glob.glob(f"{NOTES_FOLDER}/**/*.md", recursive=True)
    for file_path in files:
        sync_file(file_path)
    archive_deleted_files()
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(local_index, f, indent=2)
    print("\n✅ Vault sync complete.")

if __name__ == "__main__":
    sync_all()

import os
import json
import uuid
import hashlib
from dotenv import load_dotenv
from supabase import create_client
from sentence_transformers import SentenceTransformer

# Load environment variables
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
NOTES_FOLDER = os.getenv("NOTES_FOLDER") or "C:/ObsidianVaults/MasterVault"
TABLE_NAME = "note-chunks"
INDEX_FILE = ".vault_index.json"

# Initialize Supabase + model
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
model = SentenceTransformer("all-MiniLM-L6-v2")

# Load or initialize index
if os.path.exists(INDEX_FILE):
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        index = json.load(f)
else:
    index = {}

def hash_content(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def embed_text(text):
    return model.encode(text).tolist()

def sync_file(path):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    if not content:
        print(f"⚠️ Skipping empty file: {path}")
        return

    title = os.path.splitext(os.path.basename(path))[0]
    file_id = index.get(path, {}).get("id") or str(uuid.uuid4())
    new_hash = hash_content(content)
    old_entry = index.get(path)

    if old_entry:
        if old_entry.get("hash") == new_hash:
            return  # No changes

        # Content changed → update
        embedding = embed_text(content)
        supabase.table(TABLE_NAME).update({
            "title": title,
            "content": content,
            "embedding": embedding,
            "filepath": path.replace("\\", "/"),
            "archived": False
        }).eq("id", old_entry["id"]).execute()
        print(f"✏️ Updated: {path}")
    else:
        # New file → insert
        embedding = embed_text(content)
        supabase.table(TABLE_NAME).insert({
            "id": file_id,
            "filepath": path.replace("\\", "/"),
            "title": title,
            "content": content,
            "embedding": embedding,
            "archived": False
        }).execute()
        print(f"➕ Inserted: {path}")

    # Update index
    index[path] = {"id": file_id, "hash": new_hash}

def archive_missing_files():
    current_files = set()
    for root, _, files in os.walk(NOTES_FOLDER):
        for f in files:
            if f.endswith(".md"):
                current_files.add(os.path.join(root, f))

    known_files = set(index.keys())
    missing = known_files - current_files

    for path in missing:
        file_id = index[path]["id"]
        supabase.table(TABLE_NAME).update({"archived": True}).eq("id", file_id).execute()
        print(f"🗃️ Archived missing file: {path}")

if __name__ == "__main__":
    for root, _, files in os.walk(NOTES_FOLDER):
        for f in files:
            if f.endswith(".md"):
                full_path = os.path.join(root, f)
                sync_file(full_path)

    archive_missing_files()

    # Save updated index
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)

    print("✅ Vault sync complete.")

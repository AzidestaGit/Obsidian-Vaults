import os
import glob
import json
import uuid
import hashlib
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client
from sentence_transformers import SentenceTransformer
from postgrest.exceptions import APIError

# Load environment variables
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
NOTES_FOLDER = os.getenv("NOTES_FOLDER")
TABLE_NAME = os.getenv("SUPABASE_TABLE")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
model = SentenceTransformer("all-MiniLM-L6-v2")
index_path = Path(".vault_index.json")

# Load or create local index
if index_path.exists():
    with open(index_path, "r", encoding="utf-8") as f:
        local_index = json.load(f)
else:
    local_index = {}

# Helpers
def normalize_path(p):
    return str(Path(p).resolve().as_posix())

def get_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def safe_execute(call, payload, file_path, stage="insert", fail_if_missing=False):
    try:
        call.execute()
    except APIError as e:
        print(f"\n🔥 Supabase APIError during {stage}: {file_path}")
        print(f"Payload:\n{json.dumps(payload, indent=2)[:2000]}... [truncated]")
        print(f"Error: {e}")
        if fail_if_missing and file_path in local_index:
            del local_index[file_path]
            print(f"🧹 Removed from index: {file_path}")
    except Exception as e:
        print(f"\n💥 Unexpected error during {stage}: {file_path}")
        print(f"Payload:\n{json.dumps(payload, indent=2)[:2000]}... [truncated]")
        print(f"Error: {e}")

def sync_file(full_path):
    full_path = normalize_path(full_path)
    title = os.path.splitext(os.path.basename(full_path))[0]

    with open(full_path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    content = content or ""
    content_hash = get_hash(content)
    embedding = model.encode(content).tolist() if content else None

    if full_path in local_index:
        file_record = local_index[full_path]
        file_id = file_record["id"]

        if file_record["hash"] == content_hash:
            payload = {
                "filepath": full_path,
                "title": title,
                "archived": False
            }
            safe_execute(supabase.table(TABLE_NAME).update(payload).eq("id", file_id), payload, full_path, "rename/move")
            print(f"🔄 Moved/renamed: {full_path}")
        else:
            payload = {
                "filepath": full_path,
                "title": title,
                "content": content,
                "archived": False
            }
            safe_execute(supabase.table(TABLE_NAME).update(payload).eq("id", file_id), payload, full_path, "update-meta")

            if embedding is not None:
                emb_payload = {"embedding": embedding}
                safe_execute(supabase.table(TABLE_NAME).update(emb_payload).eq("id", file_id), emb_payload, full_path, "update-embedding")

            print(f"✏️ Updated: {full_path}")

        local_index[full_path]["hash"] = content_hash

    else:
        file_id = str(uuid.uuid4())
        payload = {
            "id": file_id,
            "filepath": full_path,
            "title": title,
            "content": content,
            "archived": False
        }

        safe_execute(supabase.table(TABLE_NAME).insert(payload), payload, full_path, "insert")

        if embedding is not None:
            emb_payload = {"embedding": embedding}
            safe_execute(supabase.table(TABLE_NAME).update(emb_payload).eq("id", file_id), emb_payload, full_path, "embed-on-insert")

        local_index[full_path] = {
            "id": file_id,
            "hash": content_hash
        }
        print(f"🆕 Inserted: {full_path}")

# Main sync loop
seen_paths = set()

for file_path in glob.glob(f"{NOTES_FOLDER}/**/*.md", recursive=True):
    full_path = normalize_path(file_path)
    sync_file(full_path)
    seen_paths.add(full_path)

# Archive deleted files
missing_paths = [path for path in list(local_index) if path not in seen_paths]

for missing in missing_paths:
    file_id = local_index[missing]["id"]
    payload = {"archived": True}
    safe_execute(supabase.table(TABLE_NAME).update(payload).eq("id", file_id), payload, missing, "archive", fail_if_missing=True)
    print(f"📦 Archived (missing): {missing}")

# Save index
with open(index_path, "w", encoding="utf-8") as f:
    json.dump(local_index, f, indent=2)

print("✅ Smart vault sync complete.")

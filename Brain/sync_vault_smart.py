# sync_vault_smart.py

import os
import glob
import json
import uuid
import hashlib
import openai
import tiktoken
import frontmatter
from supabase import create_client
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE")
NOTES_FOLDER = os.getenv("NOTES_FOLDER")
INDEX_FILE = "vault_index.json"

# Initialize Supabase and OpenAI
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
openai.api_key = os.getenv("OPENAI_API_KEY")
tokenizer = tiktoken.encoding_for_model("text-embedding-3-small")

# Load or initialize local index
if os.path.exists(INDEX_FILE):
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        local_index = json.load(f)
else:
    local_index = {}

def normalize_path(path):
    return os.path.normpath(path).replace("\\", "/")

def get_hash(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

def get_embedding(text):
    response = openai.embeddings.create(
        input=[text],
        model="text-embedding-3-small"
    )
    return list(response.data[0].embedding)

def get_or_set_uuid(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        post = frontmatter.load(f)
        file_uuid = post.get("uuid")

    if file_uuid:
        return file_uuid

    new_uuid = str(uuid.uuid4())
    post["uuid"] = new_uuid

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))

    return new_uuid

def sync_file(filepath):
    filepath = normalize_path(filepath)
    file_uuid = get_or_set_uuid(filepath)

    with open(filepath, "r", encoding="utf-8") as f:
        post = frontmatter.load(f)
        content = post.content.strip()
        title = os.path.splitext(os.path.basename(filepath))[0]
        content_hash = get_hash(content)

    response = supabase.table(SUPABASE_TABLE).select("*").eq("id", file_uuid).execute()
    supa_rows = response.data

    embedding = get_embedding(content) if content else None

    payload = {
        "id": file_uuid,
        "filepath": filepath,
        "title": title,
        "content": content if content else None,
        "embedding": embedding,
        "archived": False,
        "content_hash": content_hash
    }

    if not supa_rows:
        supabase.table(SUPABASE_TABLE).insert(payload).execute()
        print(f"🆕 Inserted: {filepath}")
    else:
        supa_row = supa_rows[0]
        update_fields = {}

        if normalize_path(supa_row["filepath"]) != filepath:
            update_fields["filepath"] = filepath
        if supa_row["title"] != title:
            update_fields["title"] = title
        if supa_row.get("content_hash") != content_hash:
            update_fields["content"] = content
            update_fields["embedding"] = embedding
            update_fields["content_hash"] = content_hash
        if supa_row["archived"]:
            update_fields["archived"] = False

        if update_fields:
            supabase.table(SUPABASE_TABLE).update(update_fields).eq("id", file_uuid).execute()
            print(f"✏️ Updated: {filepath}")
            for k, v in update_fields.items():
                if k == "content":
                    print("  ↪ content updated")
                elif k == "embedding":
                    print("  ↪ embedding updated")
                else:
                    print(f"  ↪ {k}: {supa_row.get(k, 'N/A')} → {v}")

    local_index[file_uuid] = {
        "id": file_uuid,
        "filepath": filepath,
        "title": title,
        "content_hash": content_hash
    }

# Start sync
print(f"🔄 Sync started at {datetime.now().strftime('%H:%M:%S')}...\n")

all_filepaths = glob.glob(f"{NOTES_FOLDER}/**/*.md", recursive=True)
all_filepaths = [normalize_path(p) for p in all_filepaths]

for file_path in all_filepaths:
    try:
        sync_file(file_path)
    except Exception as e:
        print(f"🔥 Error while syncing: {file_path}\n{e}")

# Archive files missing from disk
live_paths = set(all_filepaths)
for uuid_key, meta in local_index.items():
    saved_path = normalize_path(meta["filepath"])
    if saved_path not in live_paths:
        try:
            supabase.table(SUPABASE_TABLE).update({"archived": True}).eq("id", uuid_key).execute()
            print(f"📦 Archived (missing): {saved_path}")
        except Exception as e:
            print(f"🔥 Archive error: {saved_path}\n{e}")

with open(INDEX_FILE, "w", encoding="utf-8") as f:
    json.dump(local_index, f, indent=2)

print("\n✅ Vault sync complete.")

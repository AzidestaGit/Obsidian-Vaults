import os
import json
import time
import uuid
import hashlib
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from supabase import create_client
import tiktoken
import openai

# === Load environment variables ===
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE")
NOTES_FOLDER = os.getenv("NOTES_FOLDER")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# === Initialize clients ===
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
openai.api_key = OPENAI_API_KEY
tokenizer = tiktoken.encoding_for_model("text-embedding-3-small")

# === Local state cache ===
INDEX_FILE = ".vault_index.json"
if Path(INDEX_FILE).exists():
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        local_index = json.load(f)
else:
    local_index = {}

# === Helper: collapse long array in logs ===
def summarize_payload(payload):
    summarized = payload.copy()
    if "embedding" in summarized:
        summarized["embedding"] = f"[{len(summarized['embedding'])} floats]"
    return summarized

# === Helper: hash content for change tracking ===
def hash_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

# === Helper: split file into overlapping chunks ===
def chunk_text(text, max_tokens=500, overlap=50):
    tokens = tokenizer.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        chunk = tokenizer.decode(tokens[start:start+max_tokens])
        chunks.append(chunk)
        start += max_tokens - overlap
    return chunks or [""]  # Even empty files give one blank chunk

# === Generate vector embedding ===
def get_embedding(text):
    response = openai.embeddings.create(input=[text], model="text-embedding-3-small")
    return response.data[0].embedding

# === Sync a single file ===
def sync_file(filepath):
    filepath = str(Path(filepath).resolve())
    title = Path(filepath).stem

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read().strip()

    content_hash = hash_text(content)
    if local_index.get(filepath, {}).get("hash") == content_hash:
        return  # No change

    chunks = chunk_text(content)
    archived = False

    for i, chunk in enumerate(chunks):
        embedding = get_embedding(chunk) if chunk else None
        embedding_list = list(embedding) if embedding else None

        payload = {
            "filepath": filepath,
            "title": title,
            "content": chunk,
            "embedding": embedding_list,
            "archived": archived
        }

        existing = supabase.table(SUPABASE_TABLE).select("id").eq("filepath", filepath).execute().data
        try:
            if existing:
                payload["id"] = existing[0]["id"]
                print(f"🔁 Updating: {title}")
                supabase.table(SUPABASE_TABLE).update(payload).eq("id", payload["id"]).execute()
            else:
                payload["id"] = str(uuid.uuid4())
                print(f"🆕 Inserting: {title}")
                supabase.table(SUPABASE_TABLE).insert(payload).execute()
        except Exception as e:
            print(f"🔥 Supabase APIError while syncing: {filepath}")
            print("Payload:")
            print(json.dumps(summarize_payload(payload), indent=2))
            print(f"Error: {e}")

    local_index[filepath] = {"hash": content_hash, "timestamp": datetime.now().isoformat()}

# === Archive deleted files ===
def archive_deleted_files():
    current_files = {str(p.resolve()) for p in Path(NOTES_FOLDER).rglob("*.md")}
    indexed_files = set(local_index.keys())
    deleted_files = indexed_files - current_files

    for path in deleted_files:
        existing = supabase.table(SUPABASE_TABLE).select("id").eq("filepath", path).execute().data
        if existing:
            try:
                print(f"📦 Archiving (missing): {path}")
                supabase.table(SUPABASE_TABLE).update({"archived": True}).eq("id", existing[0]["id"]).execute()
                local_index[path]["archived"] = True
            except Exception as e:
                print(f"🔥 Archive error: {path}")
                print(f"Error: {e}")

# === Main Sync ===
for file_path in Path(NOTES_FOLDER).rglob("*.md"):
    sync_file(file_path)

archive_deleted_files()

with open(INDEX_FILE, "w", encoding="utf-8") as f:
    json.dump(local_index, f, indent=2)

print("✅ Smart sync complete.")

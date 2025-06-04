# sync_vault_smart.py
import os, json, uuid, hashlib
from datetime import datetime
from supabase import create_client
from dotenv import load_dotenv
import openai, tiktoken

# Load config
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE")
NOTES_FOLDER = os.getenv("NOTES_FOLDER")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
tokenizer = tiktoken.encoding_for_model("text-embedding-3-small")
INDEX_FILE = "vault_index.json"

# Load or initialize index
if os.path.exists(INDEX_FILE):
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        try:
            vault_index = json.load(f)
        except json.JSONDecodeError:
            vault_index = {}
else:
    vault_index = {}

def chunk_text(text, max_tokens=500, overlap=50):
    tokens = tokenizer.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = start + max_tokens
        chunk = tokenizer.decode(tokens[start:end])
        chunks.append(chunk)
        start += max_tokens - overlap
    return chunks

def get_embedding(text):
    return list(openai.embeddings.create(input=[text], model="text-embedding-3-small").data[0].embedding)

def compute_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def sync_file(filepath):
    rel_path = filepath.replace("\\", "/")
    title = os.path.splitext(os.path.basename(filepath))[0]

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read().strip()

    content_hash = compute_hash(content)
    is_blank = not content

    local = vault_index.get(rel_path)
    if isinstance(local, dict):
        file_uuid = local["id"]
    else:
        file_uuid = local if isinstance(local, str) else str(uuid.uuid4())

    supa_result = supabase.table(SUPABASE_TABLE).select("*").eq("id", file_uuid).execute().data
    is_new = not bool(supa_result)

    payload = {
        "id": file_uuid,
        "filepath": rel_path,
        "title": title,
        "content": content if not is_blank else None,
        "embedding": get_embedding(content) if not is_blank else None,
        "archived": False
    }

    if is_new:
        try:
            supabase.table(SUPABASE_TABLE).insert(payload).execute()
            print(f"🆕 Inserted: {rel_path}")
        except Exception as e:
            print(f"🔥 Supabase insert error: {rel_path}\n{e}")
    else:
        existing = supa_result[0]
        updates = {}
        logs = []

        if existing["filepath"] != rel_path:
            updates["filepath"] = rel_path
            logs.append(f"  • filepath: {existing['filepath']} → {rel_path}")
        if existing["title"] != title:
            updates["title"] = title
            logs.append(f"  • title: {existing['title']} → {title}")
        if not is_blank and compute_hash(existing.get("content", "")) != content_hash:
            updates["content"] = content
            updates["embedding"] = payload["embedding"]
            logs.append("  • content updated")

        if updates:
            try:
                supabase.table(SUPABASE_TABLE).update(updates).eq("id", file_uuid).execute()
                print(f"🔁 Updated: {rel_path}")
                for line in logs:
                    print(line)
            except Exception as e:
                print(f"🔥 Supabase update error: {rel_path}\n{e}")
        else:
            print(f"✅ No changes for: {rel_path}")

    vault_index[rel_path] = {
        "id": file_uuid,
        "filepath": rel_path,
        "title": title,
        "content_hash": content_hash
    }

# Main sync
print(f"🔄 Sync started at {datetime.now().strftime('%H:%M:%S')}...\n")
all_files = []
for root, dirs, files in os.walk(NOTES_FOLDER):
    for f in files:
        if f.endswith(".md"):
            all_files.append(os.path.join(root, f))

existing_paths = set(vault_index.keys())
current_paths = set(path.replace("\\", "/") for path in all_files)

for file_path in all_files:
    try:
        sync_file(file_path)
    except Exception as e:
        print(f"🔥 Unexpected error during sync: {file_path}\n{e}")

deleted_paths = existing_paths - current_paths
for path in deleted_paths:
    record = vault_index[path]
    file_uuid = record["id"] if isinstance(record, dict) else record
    try:
        supabase.table(SUPABASE_TABLE).update({"archived": True}).eq("id", file_uuid).execute()
        print(f"📦 Archived (missing): {path}")
        vault_index[path]["archived"] = True
    except Exception as e:
        print(f"🔥 Supabase archive error: {path}\n{e}")

with open(INDEX_FILE, "w", encoding="utf-8") as f:
    json.dump(vault_index, f, indent=2)

print("\n✅ Vault sync complete.")

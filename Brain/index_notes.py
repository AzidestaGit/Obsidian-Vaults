import os
import glob
import uuid
import openai
import tiktoken
from supabase import create_client
from dotenv import load_dotenv

# Load .env variables
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
openai.api_key = os.getenv("OPENAI_API_KEY")
NOTES_FOLDER = os.getenv("NOTES_FOLDER")
TABLE_NAME = "note-chunks"  # Make sure this matches your table

# Init clients
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
tokenizer = tiktoken.encoding_for_model("text-embedding-3-small")

# Helper to chunk text
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

# Generate OpenAI embedding
def get_embedding(text):
    response = openai.embeddings.create(
        input=[text],
        model="text-embedding-3-small"
    )
    return list(response.data[0].embedding)

# Start indexing
for file_path in glob.glob(f"{NOTES_FOLDER}/**/*.md", recursive=True):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    if not content:
        print(f"⚠️ Skipping empty file: {file_path}")
        continue

    file_title = os.path.splitext(os.path.basename(file_path))[0]
    chunks = chunk_text(content)

    for chunk in chunks:
        if not chunk.strip():
            continue

        try:
            embedding = get_embedding(chunk)

            payload = {
                "id": str(uuid.uuid4()),
                "filepath": file_path,
                "title": file_title,
                "content": chunk,
                "embedding": embedding
            }

            result = supabase.table(TABLE_NAME).insert(payload).execute()

            if hasattr(result, "error") and result.error:
                print(f"❌ Insert failed for {file_path}")
                print("Payload:", {k: v if k != "embedding" else "[embedding omitted]" for k, v in payload.items()})
                print("Error:", result.error)
            else:
                print(f"✅ Inserted: {file_path}")

        except Exception as e:
            print(f"🔥 Exception while inserting {file_path}: {e}")

"""
文档-->读取-->切片-->向量化-->存储

Author: Gongmin Wei
Date: 2026-4-24
"""
import os
import dotenv
from pathlib import Path
import logging
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from langchain_community.document_loaders import PyPDFLoader, TextLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

logging.getLogger("sentence_transformers").setLevel(logging.CRITICAL)
dotenv.load_dotenv()


BASE_DIR = Path(__file__).parent.parent.parent.parent
CHROMA_PERSIST_DIR = BASE_DIR / os.getenv("CHROMA_PERSIST_DIR")
CHROMA_PERSIST_DIR.mkdir(exist_ok=True)
CHROMA_PERSIST_DIR = str(CHROMA_PERSIST_DIR)

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP"))

COLLECTION_NAME = os.getenv("COLLECTION_NAME")

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")
model_path = str(BASE_DIR / "models" / EMBEDDING_MODEL)
embedding_function = SentenceTransformerEmbeddingFunction(
    model_name=model_path
)

# 创建 Chroma 客户端 (https://docs.chroma.org.cn/docs/overview/getting-started)
client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
collection = client.get_or_create_collection(
    name=COLLECTION_NAME,
    embedding_function=embedding_function
)

def process_doc(doc_path: str) -> str:
    """读取文档进行切片，向量化后存入Chroma向量库"""
    if not os.path.exists(doc_path):
        return f"Error: 文档 {doc_path} 不存在"

    ext = doc_path.split(".")[-1].lower()

    try:
        if ext == "pdf":
            loader = PyPDFLoader(doc_path)
        elif ext == "txt":
            loader = TextLoader(doc_path)
        elif ext == "docx":
            loader = Docx2txtLoader(doc_path)
        else:
            return f"Error: 文档格式 {ext} 不支持"
    except Exception as e:
        return f"Error: 加载器初始化失败-{e}"

    # 读取
    try:
        docs = loader.load()
    except Exception as e:
        return f"Error: 文档加载失败-{e}"

    # 切片
    try:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", "。", "！", "？", " "]
        )
        chunks = splitter.split_documents(docs)
        texts = [chunk.page_content for chunk in chunks]
    except Exception as e:
        return f"Error: 文档切片失败-{e}"

    # 向量化并存储 (Chroma自动向量化)
    try:
        collection.add(
            ids=[f"doc_{i}" for i in range(len(texts))],
            documents=texts
        )
    except Exception as e:
        return f"Error: 文档存储失败-{e}"

    return f"Success: 成功向 Chroma 添加 {len(texts)} 个文档"

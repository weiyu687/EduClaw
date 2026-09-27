"""
测试 tool: retrieve_knowledge 在向量数据库中进行检索，返回相关内容

Author: Gongmin Wei
Date: 2026-4-27
"""
import os
import dotenv
from pathlib import Path
import chromadb

dotenv.load_dotenv()


BASE_DIR = Path(__file__).parent.parent.parent.parent
CHROMA_PERSIST_DIR = BASE_DIR / os.getenv("CHROMA_PERSIST_DIR")
CHROMA_PERSIST_DIR.mkdir(exist_ok=True)
CHROMA_PERSIST_DIR = str(CHROMA_PERSIST_DIR)
COLLECTION_NAME = os.getenv("COLLECTION_NAME")

cient = chromadb.PersistentClient(path=os.getenv("CHROMA_PERSIST_DIR"))

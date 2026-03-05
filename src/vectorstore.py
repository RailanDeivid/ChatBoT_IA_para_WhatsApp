import logging
import os

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

from src.config import RAG_FILES_DIR, VECTOR_STORE_PATH

logger = logging.getLogger(__name__)


def load_documents():
    docs = []

    files = [
        os.path.join(RAG_FILES_DIR, f)
        for f in os.listdir(RAG_FILES_DIR)
        if f.endswith('.pdf') or f.endswith('.txt')
    ]

    for file in files:
        try:
            loader = PyPDFLoader(file) if file.endswith('.pdf') else TextLoader(file, encoding="utf-8")
            docs.extend(loader.load())
            os.remove(file)
            logger.info("Arquivo indexado e removido: %s", os.path.basename(file))
        except Exception as e:
            logger.error("Erro ao processar %s: %s", os.path.basename(file), e)

    return docs

def get_vectorstore():
    docs = load_documents()
    if docs:
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
        )
        splits = text_splitter.split_documents(docs)
        return Chroma.from_documents(
            documents=splits,
            embedding=OpenAIEmbeddings(),
            persist_directory=VECTOR_STORE_PATH,
        )

    # Só abre o índice existente se o diretório já tiver dados
    if os.path.isdir(VECTOR_STORE_PATH) and os.listdir(VECTOR_STORE_PATH):
        return Chroma(
            embedding_function=OpenAIEmbeddings(),
            persist_directory=VECTOR_STORE_PATH,
        )

    return None
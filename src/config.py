import os
from dotenv import load_dotenv


load_dotenv()

EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL")
EVOLUTION_INSTANCE_NAME = os.getenv("EVOLUTION_INSTANCE_NAME")
EVOLUTION_AUTHENTICATION_API_KEY = os.getenv("AUTHENTICATION_API_KEY")


VECTOR_STORE_PATH = os.getenv("VECTOR_STORE_PATH")
RAG_FILES_PATH = os.getenv("rag_files")
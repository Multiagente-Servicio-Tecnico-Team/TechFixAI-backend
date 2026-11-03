"""Configuración central del índice semántico multilingüe."""
from functools import lru_cache

from langchain_community.embeddings import FastEmbedEmbeddings

EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
CORPUS_VERSION = "v2"
COLLECTION_NAME = f"servicio_tecnico_{CORPUS_VERSION.replace('.', '_')}"


@lru_cache(maxsize=1)
def create_embeddings() -> FastEmbedEmbeddings:
    return FastEmbedEmbeddings(model_name=EMBEDDING_MODEL)

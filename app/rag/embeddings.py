"""Configuración central del índice semántico multilingüe."""
from functools import lru_cache

from langchain_community.embeddings import FastEmbedEmbeddings

from app.rag.constants import COLLECTION_NAME, CORPUS_VERSION, EMBEDDING_MODEL


@lru_cache(maxsize=1)
def create_embeddings() -> FastEmbedEmbeddings:
    return FastEmbedEmbeddings(model_name=EMBEDDING_MODEL)

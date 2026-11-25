"""Identificadores estables del corpus y del índice vectorial opcional."""

EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
CORPUS_VERSION = "v2"
COLLECTION_NAME = f"servicio_tecnico_{CORPUS_VERSION.replace('.', '_')}"

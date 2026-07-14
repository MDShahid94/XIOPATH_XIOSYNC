"""
GPU-Accelerated Embedding Engine for Colab Workers
===================================================
Optional module that leverages Colab's free GPU for:
    1. Fast semantic embeddings (Qwen3-Embedding / EmbeddingGemma)
    2. Local FAISS vector index (GPU-accelerated similarity search)

This replaces ChromaDB's default CPU embedder on Colab workers
while the central server continues to use ChromaDB normally.

Usage:
    embedder = GPUEmbedder(model_name="Qwen/Qwen3-Embedding-0.6B")
    vectors = embedder.encode(["click the login button", "fill username"])
    embedder.add_to_index(vectors, ids=["intent_1", "intent_2"])
    results = embedder.search("sign in", top_k=3)
"""

import os
import logging
import numpy as np
from typing import List, Optional, Dict, Any

logger = logging.getLogger("GPUEmbedder")


class GPUEmbedder:
    """
    GPU-accelerated embedding engine with optional FAISS local index.

    Supports multiple embedding models:
        - Qwen/Qwen3-Embedding-0.6B (lightweight, fast)
        - google/embedding-gemma-2b (higher quality, more VRAM)
        - sentence-transformers/all-MiniLM-L6-v2 (fallback, CPU-friendly)
    """

    # Supported models with their embedding dimensions
    MODEL_DIMS = {
        "Qwen/Qwen3-Embedding-0.6B": 1024,
        "google/embedding-gemma-2b": 2048,
        "sentence-transformers/all-MiniLM-L6-v2": 384,
    }

    def __init__(
        self,
        model_name: str = "Qwen/Qwen3-Embedding-0.6B",
        use_faiss: bool = True,
        faiss_gpu: bool = True,
    ):
        """
        Args:
            model_name: HuggingFace model ID for embeddings
            use_faiss: Whether to maintain a local FAISS index
            faiss_gpu: Whether to use GPU-accelerated FAISS (requires faiss-gpu)
        """
        self.model_name = model_name
        self.use_faiss = use_faiss
        self.faiss_gpu = faiss_gpu

        self._model = None
        self._tokenizer = None
        self._faiss_index = None
        self._id_map: Dict[int, str] = {}  # FAISS int index → string ID
        self._next_idx = 0

        self.embedding_dim = self.MODEL_DIMS.get(model_name, 768)

    @property
    def model(self):
        """Lazy-load the embedding model on first use."""
        if self._model is None:
            self._load_model()
        return self._model

    @property
    def tokenizer(self):
        """Lazy-load the tokenizer on first use."""
        if self._tokenizer is None:
            self._load_model()
        return self._tokenizer

    def _load_model(self):
        """Load the embedding model and tokenizer."""
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer

            logger.info(f"Loading embedding model: {self.model_name}...")

            self._tokenizer = AutoTokenizer.from_pretrained(
                self.model_name, trust_remote_code=True
            )
            self._model = AutoModel.from_pretrained(
                self.model_name, trust_remote_code=True
            )

            # Move to GPU if available
            if torch.cuda.is_available():
                self._model = self._model.cuda()
                logger.info(f"Model loaded on GPU ({torch.cuda.get_device_name(0)})")
            else:
                logger.info("Model loaded on CPU (no GPU detected)")

            self._model.eval()

        except ImportError:
            logger.warning(
                "transformers/torch not installed. "
                "Install with: pip install transformers torch"
            )
            raise
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise

    def _init_faiss_index(self):
        """Initialize FAISS index (GPU or CPU)."""
        try:
            import faiss

            index = faiss.IndexFlatIP(self.embedding_dim)  # Inner Product (cosine after L2 norm)

            if self.faiss_gpu:
                try:
                    res = faiss.StandardGpuResources()
                    self._faiss_index = faiss.index_cpu_to_gpu(res, 0, index)
                    logger.info("FAISS index initialized on GPU")
                except Exception:
                    self._faiss_index = index
                    logger.info("FAISS GPU failed, using CPU index")
            else:
                self._faiss_index = index
                logger.info("FAISS index initialized on CPU")

        except ImportError:
            logger.warning("FAISS not installed. Install with: pip install faiss-gpu")
            self.use_faiss = False

    # ================================================================
    # ENCODING
    # ================================================================

    def encode(self, texts: List[str], normalize: bool = True) -> np.ndarray:
        """
        Encode texts into embedding vectors.

        Args:
            texts: List of strings to embed
            normalize: L2-normalize vectors (required for cosine similarity in FAISS)

        Returns:
            numpy array of shape (len(texts), embedding_dim)
        """
        import torch

        inputs = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )

        if torch.cuda.is_available():
            inputs = {k: v.cuda() for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.model(**inputs)

        # Mean pooling over token embeddings
        attention_mask = inputs["attention_mask"]
        token_embeddings = outputs.last_hidden_state
        input_mask_expanded = (
            attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        )
        embeddings = torch.sum(
            token_embeddings * input_mask_expanded, 1
        ) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)

        vectors = embeddings.cpu().numpy()

        if normalize:
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            vectors = vectors / np.maximum(norms, 1e-9)

        return vectors

    # ================================================================
    # FAISS INDEX OPERATIONS
    # ================================================================

    def add_to_index(self, vectors: np.ndarray, ids: List[str]):
        """Add vectors to the FAISS index with string ID mapping."""
        if not self.use_faiss:
            return

        if self._faiss_index is None:
            self._init_faiss_index()

        vectors = vectors.astype(np.float32)
        self._faiss_index.add(vectors)

        for str_id in ids:
            self._id_map[self._next_idx] = str_id
            self._next_idx += 1

    def search(
        self, query: str, top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search the FAISS index for similar vectors.

        Returns:
            List of dicts with 'id' and 'score' keys, sorted by relevance
        """
        if not self.use_faiss or self._faiss_index is None:
            return []

        query_vec = self.encode([query]).astype(np.float32)
        scores, indices = self._faiss_index.search(query_vec, top_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx >= 0 and idx in self._id_map:
                results.append({
                    "id": self._id_map[idx],
                    "score": float(score),
                })

        return results

    # ================================================================
    # CHROMADB COMPATIBILITY
    # ================================================================

    def as_chromadb_function(self):
        """
        Return a callable compatible with ChromaDB's EmbeddingFunction interface.

        Usage:
            collection = chroma_client.get_or_create_collection(
                "memory", embedding_function=embedder.as_chromadb_function()
            )
        """

        embedder = self

        class _ChromaAdapter:
            def __call__(self, input: List[str]) -> List[List[float]]:
                vectors = embedder.encode(input)
                return vectors.tolist()

        return _ChromaAdapter()

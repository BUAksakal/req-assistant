from llama_index.core import VectorStoreIndex
from llama_index.core.schema import TextNode

from reqlens.llm import get_embed_model
from reqlens.models import Requirement


def build_index(requirements: list[Requirement]) -> VectorStoreIndex:
    """Turn requirements into embeddings so they can be searched by meaning."""
    nodes = [
        TextNode(text=req.text, id_=req.id, metadata={"page": req.page})
        for req in requirements
    ]
    return VectorStoreIndex(nodes, embed_model=get_embed_model())


def search(
    index: VectorStoreIndex, query: str, top_k: int = 3
) -> list[tuple[str, float]]:
    """Return the IDs of the most similar requirements and their scores."""
    results = index.as_retriever(similarity_top_k=top_k).retrieve(query)
    return [(r.node.id_, round(r.score, 2)) for r in results]

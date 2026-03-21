from loguru import logger

from backend.knowledge_library.facts_store import facts_store
from backend.knowledge_library.ragflow_client import ragflow
from backend.knowledge_library.sources_store import sources_store
from backend.schemas.knowledge_unit import KnowledgeUnit
from backend.schemas.research_result import Source


class KnowledgeRetriever:
    async def retrieve(self, query: str, use_ragflow: bool = True, top_k: int = 5) -> list[dict]:
        results = []

        local_facts = await facts_store.search(query)
        for fact in local_facts[:top_k]:
            results.append({"source": "local", "content": fact.content, "confidence": fact.confidence})

        if use_ragflow:
            try:
                chunks = await ragflow.search(query, top_k=top_k)
                for chunk in chunks:
                    results.append({
                        "source": "ragflow",
                        "content": chunk.get("content", ""),
                        "confidence": chunk.get("similarity", 0.5),
                    })
            except Exception as e:
                logger.warning(f"RAGFlow retrieval failed: {e}")

        results.sort(key=lambda x: x["confidence"], reverse=True)
        logger.info(f"Retrieved {len(results)} knowledge items for query")
        return results[:top_k]


retriever = KnowledgeRetriever()

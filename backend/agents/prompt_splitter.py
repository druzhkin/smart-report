from loguru import logger

from backend.pipeline.state import AgentState


async def run_prompt_splitter(state: AgentState) -> dict:
    logger.info("Prompt Splitter agent started")
    master = state.get("master_prompt")
    if not master:
        logger.warning("No master prompt found, skipping split")
        return {"current_agent": "prompt_splitter"}

    user_prompt = master.user_prompt
    sub_queries = [q.strip() for q in user_prompt.split("\n") if q.strip() and len(q.strip()) > 10]
    if len(sub_queries) <= 1:
        sub_queries = [user_prompt]

    logger.info(f"Prompt Splitter created {len(sub_queries)} sub-queries")
    return {
        "messages": state.get("messages", []) + [
            {"role": "prompt_splitter", "content": "\n---\n".join(sub_queries)}
        ],
        "current_agent": "prompt_splitter",
    }

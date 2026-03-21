import json
import re
from pathlib import Path

import httpx
from loguru import logger

from backend.config import settings
from backend.pipeline.model_router import AgentTask, get_model, estimate_cost
from backend.pipeline.state import AgentState
from backend.prompt_library.composer import compose_prompt, REGISTRY
from backend.schemas.master_prompt import (
    MasterPrompt,
    PromptTechnique,
    ReportSchema,
    SectionSchema,
)
from backend.utils.json_parse import parse_llm_json, supports_json_mode
from backend.utils.retry import llm_retry

KNOWLEDGE_BASE_DIR = Path("prompt_library/knowledge_base")
FEW_SHOT_DIR = KNOWLEDGE_BASE_DIR / "few_shot_examples"
ROLE_PERSONAS_PATH = KNOWLEDGE_BASE_DIR / "role_personas.json"
TASK_TEMPLATES_PATH = KNOWLEDGE_BASE_DIR / "task_templates.json"

TASK_TYPE_TO_TEMPLATE: dict[str, str] = {
    "investment_analysis": "investment_memo",
    "market_research": "market_analysis",
    "due_diligence": "due_diligence",
    "strategic_review": "strategic_review",
}

TASK_TYPE_TO_FEW_SHOT: dict[str, str] = {
    "investment_analysis": "investment_memo",
    "market_research": "market_analysis",
    "analytical_deep_dive": "market_analysis",
    "comparative_study": "market_analysis",
    "trend_forecast": "market_analysis",
    "technical_assessment": "scientific_review",
    "deep_exploratory": "market_analysis",
    "strategic_review": "market_analysis",
    "due_diligence": "investment_memo",
}


def _load_prompt(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning(f"Prompt file not found: {path}, using default")
        return (
            "You are the Prompt King. Compose a master research prompt and return JSON with "
            "these exact keys: system_prompt, user_prompt, master_prompt, techniques_applied "
            "(list of {name,weight,rationale}), report_schema ({title_template,sections,constraints,"
            "output_format,expected_length}), target_model, temperature.\n\n"
            "The master_prompt field MUST contain all four sections with these exact headers:\n"
            "## PROFILE\n<expert persona>\n\n"
            "## KNOWLEDGE\n<domain knowledge>\n\n"
            "## REASONING\n<analytical method>\n\n"
            "## RELIABILITY\n<quality standards>"
        )


def _load_json(path: Path) -> dict | list:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to load {path}: {e}")
        return {}


def _load_few_shot_examples(task_type: str) -> list[dict]:
    few_shot_key = TASK_TYPE_TO_FEW_SHOT.get(task_type, "market_analysis")
    few_shot_path = FEW_SHOT_DIR / f"{few_shot_key}.json"
    data = _load_json(few_shot_path)
    if isinstance(data, dict):
        return data.get("examples", [])
    return []


def _load_role_persona(domain: str) -> str:
    personas = _load_json(ROLE_PERSONAS_PATH)
    if isinstance(personas, dict):
        return personas.get(domain, personas.get("general", "a senior strategy consultant"))
    return "a senior strategy consultant"


def _load_task_template(task_type: str) -> dict:
    templates = _load_json(TASK_TEMPLATES_PATH)
    if isinstance(templates, dict):
        all_templates = templates.get("templates", templates)
        template_key = TASK_TYPE_TO_TEMPLATE.get(task_type)
        if template_key and template_key in all_templates:
            return all_templates[template_key]
    return {}


def _get_available_techniques() -> list[str]:
    return list(REGISTRY.keys())


@llm_retry()
async def _call_llm(system_prompt: str, user_message: str, model: str) -> str:
    # response_format: json_object is only supported by OpenAI-compatible models
    supports_json_mode = model.startswith("openai/") or model.startswith("google/")
    payload: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.4,
    }
    if supports_json_mode:
        payload["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def run_prompt_king(state: AgentState) -> dict:
    logger.info("Prompt King agent started")
    model = get_model(AgentTask.PROMPT_COMPOSITION)
    intake = state["intake_result"]

    router_result = state.get("router_result")
    selected_techniques = state.get("selected_techniques", [])

    if router_result:
        task_type = router_result.task_type
        if not selected_techniques:
            selected_techniques = router_result.techniques
    else:
        task_type = "deep_exploratory"
        router_msg = next(
            (m for m in state.get("messages", []) if m["role"] == "prompt_router"),
            None,
        )
        if router_msg:
            router_data = json.loads(router_msg["content"])
            task_type = router_data.get("task_type", task_type)
            selected_techniques = router_data.get("techniques", selected_techniques)

    few_shot_examples = _load_few_shot_examples(task_type)
    role_persona = _load_role_persona(intake.domain)
    task_template = _load_task_template(task_type)
    available_techniques = _get_available_techniques()

    technique_context = {}
    for tech_name in selected_techniques:
        if tech_name in REGISTRY:
            cls = REGISTRY[tech_name]
            technique_context[tech_name] = {
                "name": cls.name,
                "description": cls.description,
            }

    base_prompt = _load_prompt("prompts/prompt_king_system.txt")
    composed_base = compose_prompt(base_prompt, selected_techniques, {
        "intake": intake.model_dump(),
        "task_type": task_type,
        "domain": intake.domain,
    })

    context = {
        "intake": intake.model_dump(),
        "task_type": task_type,
        "selected_techniques": selected_techniques,
        "technique_details": technique_context,
        "available_techniques": available_techniques,
        "role_persona": role_persona,
        "task_template": task_template,
        "few_shot_examples": few_shot_examples,
        "master_prompt_sections": ["PROFILE", "KNOWLEDGE", "REASONING", "RELIABILITY"],
        "instructions": (
            "Compose the master_prompt with 4 clearly labeled sections: "
            "## PROFILE, ## KNOWLEDGE, ## REASONING, ## RELIABILITY. "
            f"The PROFILE section must use this persona: {role_persona}. "
            "The KNOWLEDGE section must reference frameworks relevant to the domain and include few-shot examples. "
            "The REASONING section must specify analytical methodology using the selected techniques. "
            "The RELIABILITY section must define quality guardrails, citation standards, and bias checks."
        ),
    }

    system_prompt = composed_base
    raw = await _call_llm(system_prompt, json.dumps(context, default=str), model)
    parsed = parse_llm_json(raw, context="prompt_king")

    techniques_applied = [
        PromptTechnique(**t) for t in parsed.get("techniques_applied", [])
    ]
    if not techniques_applied:
        techniques_applied = [
            PromptTechnique(name=t, weight=1.0 / len(selected_techniques), rationale="auto-applied")
            for t in selected_techniques
        ]

    report_schema_data = parsed.get("report_schema", {})
    if report_schema_data:
        def _coerce_section(s: dict | str) -> SectionSchema:
            if isinstance(s, str):
                return SectionSchema(title=s)
            # Coerce subsections: list[dict] → list[str]
            subs = s.get("subsections", [])
            s["subsections"] = [
                sub.get("title", str(sub)) if isinstance(sub, dict) else str(sub)
                for sub in subs
            ]
            return SectionSchema(**s)

        sections = [_coerce_section(s) for s in report_schema_data.get("sections", [])]
        raw_constraints = report_schema_data.get("constraints", [])
        if isinstance(raw_constraints, str):
            raw_constraints = [c.strip() for c in raw_constraints.split(".") if c.strip()]
        report_schema = ReportSchema(
            title_template=report_schema_data.get("title_template", ""),
            sections=sections,
            constraints=raw_constraints,
            output_format=report_schema_data.get("output_format", "markdown"),
            expected_length=report_schema_data.get("expected_length", ""),
        )
    elif task_template:
        sections = [
            SectionSchema(title=s, required=True)
            for s in task_template.get("sections", [])
        ]
        report_schema = ReportSchema(
            title_template="",
            sections=sections,
            expected_length=task_template.get("typical_length", ""),
        )
    else:
        report_schema = ReportSchema()

    master_prompt_text = parsed.get("master_prompt", "")
    if not master_prompt_text:
        master_prompt_text = parsed.get("system_prompt", "") + "\n\n" + parsed.get("user_prompt", "")

    # If the LLM still didn't include the required section headers, build them.
    required_headers = ("## PROFILE", "## KNOWLEDGE", "## REASONING", "## RELIABILITY")
    if not all(h in master_prompt_text for h in required_headers):
        master_prompt_text = (
            f"## PROFILE\n{role_persona}\n\n"
            f"## KNOWLEDGE\nDomain: {intake.domain}. Entities: {', '.join(intake.key_entities)}.\n"
            f"Query: {intake.cleaned_query}\n\n"
            f"## REASONING\nApply {', '.join(selected_techniques[:3])} techniques. "
            "Use structured, data-driven analysis.\n\n"
            "## RELIABILITY\nCite all sources. Validate facts against evidence. "
            "Flag uncertainty explicitly. Avoid hallucinations."
        )

    master = MasterPrompt(
        system_prompt=parsed.get("system_prompt", ""),
        user_prompt=parsed.get("user_prompt", ""),
        master_prompt=master_prompt_text,
        techniques_applied=techniques_applied,
        report_schema=report_schema,
        target_model=parsed.get("target_model", "anthropic/claude-sonnet-4"),
        temperature=parsed.get("temperature", 0.3),
    )

    cost = estimate_cost(
        AgentTask.PROMPT_COMPOSITION,
        len(json.dumps(context)) // 4,
        len(raw) // 4,
    )
    logger.info(
        f"Prompt King composed master prompt: {len(master.master_prompt)} chars, "
        f"{len(techniques_applied)} techniques, "
        f"{len(report_schema.sections)} report sections"
    )

    return {
        "master_prompt": master,
        "cost_usd": state.get("cost_usd", 0) + cost,
        "current_agent": "prompt_king",
    }

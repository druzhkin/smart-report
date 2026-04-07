from __future__ import annotations

from pydantic import BaseModel, Field

from backend.v2.models import ReportType, SourceType


class ReferenceSource(BaseModel):
    url: str
    title: str
    domain: str
    source_type: SourceType
    publisher: str
    published_at: str
    excerpt: str
    content: str


class ReferencePack(BaseModel):
    pack_id: str
    title: str
    report_type: ReportType
    keywords: list[str] = Field(default_factory=list)
    sample_prompt: str
    evaluation_dimensions: list[str] = Field(default_factory=list)
    must_cover_questions: list[str] = Field(default_factory=list)
    sources: list[ReferenceSource] = Field(default_factory=list)


REFERENCE_PACKS: list[ReferencePack] = [
    ReferencePack(
        pack_id="oss-coding-models",
        title="Open-source coding models for self-hosted assistants",
        report_type=ReportType.VENDOR_EVALUATION,
        keywords=["coding model", "self-hosted", "open-source llm", "coder model", "code assistant"],
        sample_prompt="Compare open-source coding models for a self-hosted code review assistant.",
        evaluation_dimensions=["code quality", "deployment flexibility", "licensing", "cost"],
        must_cover_questions=[
            "Which options are truly self-hostable?",
            "Which models show the strongest public coding signal?",
            "What are the main quality versus operations tradeoffs?",
        ],
        sources=[
            ReferenceSource(
                url="https://mistral.ai/news/codestral/",
                title="Codestral launch",
                domain="mistral.ai",
                source_type=SourceType.VENDOR_PAGE,
                publisher="Mistral AI",
                published_at="2024-05-29",
                excerpt="Mistral positions Codestral as a code-specialized model.",
                content="Codestral is positioned as a code-specialized model with fill-in-the-middle support and developer workflow focus. It is attractive when coding capability matters, but deployment flexibility and licensing need careful review in a self-hosted decision.",
            ),
            ReferenceSource(
                url="https://qwenlm.github.io/blog/qwen2.5-coder-family/",
                title="Qwen2.5-Coder family",
                domain="qwenlm.github.io",
                source_type=SourceType.OFFICIAL_DOCUMENTATION,
                publisher="Qwen",
                published_at="2024-11-12",
                excerpt="Qwen describes the Coder family as open-weight and tuned for code tasks.",
                content="Qwen2.5-Coder is described as an open-weight coding family with multilingual support and agent-style workflow fit. Its main upside is flexible self-hosting with community adoption. The main tradeoff is the need to validate quality and efficiency on the buyer's own workloads.",
            ),
            ReferenceSource(
                url="https://livebench.ai/",
                title="LiveBench leaderboard",
                domain="livebench.ai",
                source_type=SourceType.BENCHMARK,
                publisher="LiveBench",
                published_at="2025-02-01",
                excerpt="LiveBench provides public repeated eval signals.",
                content="LiveBench gives a useful independent benchmark layer. In a coding-model evaluation it should not replace task-specific testing, but it is valuable for checking whether vendor claims are directionally supported by repeated public eval performance.",
            ),
        ],
    ),
    ReferencePack(
        pack_id="llm-observability",
        title="LLM observability platforms",
        report_type=ReportType.VENDOR_EVALUATION,
        keywords=["llm observability", "langsmith", "langfuse", "helicone", "phoenix", "tracing"],
        sample_prompt="Evaluate LLM observability platforms for an enterprise document workflow product.",
        evaluation_dimensions=["trace depth", "evaluation tooling", "self-hosting", "governance"],
        must_cover_questions=[
            "Which platform is strongest for traceability and evals?",
            "Which options fit privacy-sensitive deployments?",
            "Which tools are best for fast operator debugging?",
        ],
        sources=[
            ReferenceSource(
                url="https://www.langchain.com/langsmith",
                title="LangSmith overview",
                domain="langchain.com",
                source_type=SourceType.VENDOR_PAGE,
                publisher="LangChain",
                published_at="2025-01-14",
                excerpt="LangSmith is positioned around traces, datasets, and experiments.",
                content="LangSmith focuses on trace inspection, dataset-backed evaluation, prompt comparisons, and production monitoring. It is strongest when a team wants one surface for debugging runs and measuring regression over time.",
            ),
            ReferenceSource(
                url="https://langfuse.com/docs",
                title="Langfuse documentation",
                domain="langfuse.com",
                source_type=SourceType.OFFICIAL_DOCUMENTATION,
                publisher="Langfuse",
                published_at="2025-01-10",
                excerpt="Langfuse documents tracing, scoring, and self-hosted deployment patterns.",
                content="Langfuse combines tracing and scoring with open-source and self-hosted deployment paths. It is attractive for teams that need observability plus privacy control and do not want to depend entirely on SaaS-only operations.",
            ),
            ReferenceSource(
                url="https://www.helicone.ai/docs",
                title="Helicone docs",
                domain="helicone.ai",
                source_type=SourceType.OFFICIAL_DOCUMENTATION,
                publisher="Helicone",
                published_at="2025-01-03",
                excerpt="Helicone emphasizes logging, caching, analytics, and cost visibility.",
                content="Helicone is strong when lightweight instrumentation and cost visibility matter more than a heavyweight evaluation stack. It is a practical fit for operational analytics, but less obviously the best choice when experiment rigor is the main buying criterion.",
            ),
        ],
    ),
    ReferencePack(
        pack_id="enterprise-rag",
        title="Enterprise RAG and knowledge platforms",
        report_type=ReportType.MARKET_LANDSCAPE,
        keywords=["rag platform", "enterprise rag", "knowledge platform", "ragflow", "llamaindex", "azure ai search"],
        sample_prompt="Map the enterprise RAG platform landscape for internal knowledge assistants.",
        evaluation_dimensions=["retrieval quality", "operational maturity", "enterprise controls", "integration surface"],
        must_cover_questions=[
            "Which offerings are managed platforms versus toolkits?",
            "Where do retrieval quality and workflow control diverge?",
            "What are the operational tradeoffs between turnkey and composable stacks?",
        ],
        sources=[
            ReferenceSource(
                url="https://azure.microsoft.com/products/ai-services/ai-search",
                title="Azure AI Search",
                domain="azure.microsoft.com",
                source_type=SourceType.VENDOR_PAGE,
                publisher="Microsoft",
                published_at="2025-01-08",
                excerpt="Azure positions AI Search as a managed retrieval foundation.",
                content="Azure AI Search is strong when enterprise control, managed infrastructure, and Microsoft ecosystem fit matter. It offers operational maturity but is infrastructure-first rather than a full research-workflow product by itself.",
            ),
            ReferenceSource(
                url="https://www.llamaindex.ai/",
                title="LlamaIndex overview",
                domain="llamaindex.ai",
                source_type=SourceType.VENDOR_PAGE,
                publisher="LlamaIndex",
                published_at="2024-12-11",
                excerpt="LlamaIndex focuses on composable connectors, indexing, and retrieval.",
                content="LlamaIndex is strongest as a composable toolkit for teams that want control over ingestion, indexing, routing, and retrieval behavior. The cost is higher engineering ownership and a greater need for internal evaluation discipline.",
            ),
            ReferenceSource(
                url="https://ragflow.io/",
                title="RAGFlow overview",
                domain="ragflow.io",
                source_type=SourceType.VENDOR_PAGE,
                publisher="RAGFlow",
                published_at="2024-11-20",
                excerpt="RAGFlow emphasizes document-centric retrieval workflows.",
                content="RAGFlow is positioned around document ingestion and retrieval workflow management rather than only low-level retrieval APIs. That makes it attractive for knowledge-heavy use cases where business users need more than a raw vector stack.",
            ),
        ],
    ),
    ReferencePack(
        pack_id="browser-agents",
        title="Browser automation stacks for AI agents",
        report_type=ReportType.COMPETITIVE_SCAN,
        keywords=["browser agent", "browser automation", "playwright", "browserbase", "stagehand", "web agent"],
        sample_prompt="Run a structured competitive scan of browser automation stacks for AI agents.",
        evaluation_dimensions=["browser reliability", "agent ergonomics", "security", "debuggability"],
        must_cover_questions=[
            "Which stacks are best for deterministic control versus agent abstraction?",
            "Where does hosted infrastructure reduce engineering load?",
            "What are the core security and observability tradeoffs?",
        ],
        sources=[
            ReferenceSource(
                url="https://playwright.dev/",
                title="Playwright documentation",
                domain="playwright.dev",
                source_type=SourceType.OFFICIAL_DOCUMENTATION,
                publisher="Microsoft",
                published_at="2025-01-16",
                excerpt="Playwright remains the baseline for deterministic browser automation.",
                content="Playwright is the control-stack benchmark: deterministic browser automation, strong debugging primitives, and broad engineering trust. Teams still need to build orchestration and sandboxing around it for full AI-agent products.",
            ),
            ReferenceSource(
                url="https://www.browserbase.com/",
                title="Browserbase overview",
                domain="browserbase.com",
                source_type=SourceType.VENDOR_PAGE,
                publisher="Browserbase",
                published_at="2025-01-09",
                excerpt="Browserbase emphasizes hosted browser infrastructure and session operations.",
                content="Browserbase is strongest when the bottleneck is operating browsers at scale rather than controlling them locally. It reduces infrastructure burden, but it introduces dependency on a hosted browser layer.",
            ),
            ReferenceSource(
                url="https://stagehand.dev/",
                title="Stagehand overview",
                domain="stagehand.dev",
                source_type=SourceType.VENDOR_PAGE,
                publisher="Stagehand",
                published_at="2025-01-06",
                excerpt="Stagehand positions itself as an LLM-native browser automation layer.",
                content="Stagehand sits in the agent-ergonomics bucket: it tries to make browser actions more natural for LLM-driven systems while still grounding on deterministic execution. The key question is whether that productivity gain justifies another abstraction layer.",
            ),
        ],
    ),
    ReferencePack(
        pack_id="web-search-deep-research-stacks",
        title="LLM and GitHub stacks for web search and deep research",
        report_type=ReportType.VENDOR_EVALUATION,
        keywords=[
            "web search",
            "deep research",
            "perplexity",
            "gpt-researcher",
            "open_deep_research",
            "sonar",
            "search stack",
            "github projects",
        ],
        sample_prompt="Choose the best LLM and GitHub stack for web search and deep research that can outperform Perplexity on quality and traceability.",
        evaluation_dimensions=["answer quality", "traceability", "controllability", "cost discipline", "implementation complexity"],
        must_cover_questions=[
            "Which managed models and APIs provide the strongest native web-search or deep-research capability for decision-grade reporting?",
            "Which GitHub projects are mature enough to use for orchestration, search integration, or deep research in production?",
            "Which architecture best beats Perplexity on answer quality, traceability, controllability, and cost discipline?",
            "What tradeoffs, failure modes, and recommendation-switch conditions matter most?",
        ],
        sources=[
            ReferenceSource(
                url="https://docs.gptr.dev/docs/gpt-researcher/gptr/deep_research",
                title="GPT Researcher deep research docs",
                domain="docs.gptr.dev",
                source_type=SourceType.OFFICIAL_DOCUMENTATION,
                publisher="GPT Researcher",
                published_at="2026-01-01",
                excerpt="GPT Researcher documents deep research mode with tree exploration, concurrent branches, and long-form output.",
                content="GPT Researcher is a strong open-source donor for long-form deep research. Its documented strengths are tree-like exploration, concurrent processing, long-form output packages, and a deep-research mode rather than simple one-shot search. As a GitHub project, GPT Researcher is mature enough for production pilots when the team wants orchestration, search integration, and report generation in one stack. The main caveat is that it remains report-first unless a separate evidence and audit layer is wrapped around it.",
            ),
            ReferenceSource(
                url="https://docs.gptr.dev/docs/gpt-researcher/search-engines",
                title="GPT Researcher search engine integrations",
                domain="docs.gptr.dev",
                source_type=SourceType.OFFICIAL_DOCUMENTATION,
                publisher="GPT Researcher",
                published_at="2026-01-01",
                excerpt="GPT Researcher supports Tavily, SearXNG, Serper, and other search backends.",
                content="GPT Researcher supports multiple search backends including SearXNG, Tavily, Serper, and other providers. That makes it useful as an orchestration layer when the product needs search-provider flexibility instead of a single fixed managed search API. The core tradeoff is that flexibility improves controllability, but it also creates failure modes around extraction quality, vendor integration, and operations.",
            ),
            ReferenceSource(
                url="https://github.com/langchain-ai/open_deep_research/blob/main/src/open_deep_research/configuration.py",
                title="open_deep_research configuration",
                domain="github.com",
                source_type=SourceType.OFFICIAL_DOCUMENTATION,
                publisher="LangChain",
                published_at="2026-01-01",
                excerpt="open_deep_research separates summarization, research, compression, and final report models.",
                content="LangChain's open_deep_research is a mature GitHub project for orchestration and evaluation-driven deep research. Its configuration makes the research model, summarization model, compression model, and final report model explicit. That is valuable for a Perplexity-on-steroids product because it supports cost routing, stage-specific quality control, and clearer recommendation-switch conditions.",
            ),
            ReferenceSource(
                url="https://github.com/zilliztech/deep-searcher",
                title="deep-searcher repository",
                domain="github.com",
                source_type=SourceType.OFFICIAL_DOCUMENTATION,
                publisher="Zilliz",
                published_at="2026-01-01",
                excerpt="deep-searcher focuses on private data plus web augmentation with vector database support.",
                content="deep-searcher is a GitHub project better suited to private-data retrieval plus web augmentation than to default public web research. It is mature enough for enterprise search integration when private knowledge is central, but it is a weaker default for broad public deep research. The tradeoff is stronger private-data retrieval versus weaker fit for open-web reporting workflows.",
            ),
            ReferenceSource(
                url="https://docs.searxng.org/dev/search_api.html",
                title="SearXNG search API",
                domain="docs.searxng.org",
                source_type=SourceType.OFFICIAL_DOCUMENTATION,
                publisher="SearXNG",
                published_at="2026-01-01",
                excerpt="SearXNG exposes a JSON search API and engine selection for self-hosted search.",
                content="SearXNG is the most attractive low-cost discovery layer when the goal is to cut search spend and keep control. It is not a complete deep-research backend by itself. It solves candidate discovery, but extraction quality, anti-bot handling, and downstream evidence assembly still need separate architecture. The key tradeoff is zero-cost search and controllability versus failure modes in extraction stability and operational burden.",
            ),
            ReferenceSource(
                url="https://docs.tavily.com/documentation/api-credits",
                title="Tavily API credits and pricing",
                domain="docs.tavily.com",
                source_type=SourceType.OFFICIAL_DOCUMENTATION,
                publisher="Tavily",
                published_at="2026-01-01",
                excerpt="Tavily documents API credits and usage for search, extract, and crawl workflows.",
                content="Tavily is valuable not only as search but as extraction and crawl infrastructure. In a Smart Report style product, Tavily is often more important as a quality extraction fallback than as the primary search engine. This is especially true when HTML search pages are noisy or unstable. The tradeoff is better extraction quality and fewer failure modes in exchange for vendor cost and dependency.",
            ),
            ReferenceSource(
                url="https://docs.perplexity.ai/docs/agent-api/quickstart",
                title="Perplexity Agent API quickstart",
                domain="docs.perplexity.ai",
                source_type=SourceType.OFFICIAL_DOCUMENTATION,
                publisher="Perplexity",
                published_at="2026-01-01",
                excerpt="Perplexity Agent API documents search, fetch, and agentic workflows.",
                content="Perplexity's Agent API is the strongest managed baseline for a Perplexity-like product because it already exposes search, fetch, and agentic workflows. It is best treated as the default managed substrate, but it still needs an external evidence ledger, critique loop, and audit harness to become a decision-grade reporting system. The main recommendation-switch condition is whether managed speed outweighs the loss of controllability.",
            ),
            ReferenceSource(
                url="https://docs.perplexity.ai/docs/admin/rate-limits-usage-tiers",
                title="Perplexity rate limits and usage tiers",
                domain="docs.perplexity.ai",
                source_type=SourceType.OFFICIAL_DOCUMENTATION,
                publisher="Perplexity",
                published_at="2026-01-01",
                excerpt="Perplexity documents usage tiers and lower throughput for deep research modes.",
                content="Perplexity deep-research style modes have worse throughput and higher operational friction than ordinary search models. That means deep-research modes should be escalation paths, not the default path for every report. The default architecture should stay on fast search-oriented models and add bounded critique and follow-up loops. The failure mode is using deep-research mode as the default and paying too much latency and throughput cost.",
            ),
            ReferenceSource(
                url="https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard",
                title="DeepResearch Bench leaderboard",
                domain="huggingface.co",
                source_type=SourceType.BENCHMARK,
                publisher="muset-ai",
                published_at="2026-01-01",
                excerpt="DeepResearch Bench compares web research agents and related systems.",
                content="DeepResearch Bench is useful as a comparative benchmark signal for research-agent quality. It should not be treated as the only decision criterion, but it is helpful for checking whether a stack choice has any public benchmark support beyond marketing claims. The tradeoff is that benchmark quality does not automatically equal traceability, controllability, or production maturity.",
            ),
        ],
    ),
    ReferencePack(
        pack_id="document-ai-workflows",
        title="AI document workflow platforms",
        report_type=ReportType.STRATEGIC_BRIEF,
        keywords=[
            "document workflow ai",
            "document workflow platform",
            "document workflow platforms",
            "document ai",
            "knowledge worker ai",
            "operations team",
            "notion ai",
            "glean",
            "box ai",
        ],
        sample_prompt="Prepare a strategic brief on AI document workflow platforms for an operations team.",
        evaluation_dimensions=["workflow depth", "knowledge access", "security", "adoption"],
        must_cover_questions=[
            "Which products act as knowledge assistants versus workflow operators?",
            "Where does integration breadth matter more than model sophistication?",
            "What are the main adoption and governance risks?",
        ],
        sources=[
            ReferenceSource(
                url="https://www.glean.com/",
                title="Glean overview",
                domain="glean.com",
                source_type=SourceType.VENDOR_PAGE,
                publisher="Glean",
                published_at="2025-01-11",
                excerpt="Glean focuses on enterprise knowledge access and connectors.",
                content="Glean is strongest when the core problem is knowledge access across enterprise tools and permissions. Its value is connector breadth and enterprise search positioning more than deep document workflow automation inside one content system.",
            ),
            ReferenceSource(
                url="https://www.box.com/ai",
                title="Box AI overview",
                domain="box.com",
                source_type=SourceType.VENDOR_PAGE,
                publisher="Box",
                published_at="2024-12-09",
                excerpt="Box AI frames value around content workflows and governance.",
                content="Box AI makes the strongest case where controlled document workflows and governance inside an existing content platform are the priority. It is structurally advantaged in document-centric operations.",
            ),
            ReferenceSource(
                url="https://www.notion.so/product/ai",
                title="Notion AI overview",
                domain="notion.so",
                source_type=SourceType.VENDOR_PAGE,
                publisher="Notion",
                published_at="2025-01-02",
                excerpt="Notion AI focuses on end-user productivity inside a workspace.",
                content="Notion AI is compelling when user adoption and low-friction workspace assistance matter more than heavyweight governance or cross-enterprise retrieval. It is strongest as a productivity layer, not as the single system of record for complex document operations.",
            ),
        ],
    ),
]


def match_reference_pack(query: str) -> ReferencePack | None:
    normalized = (query or "").lower()
    scored: list[tuple[int, ReferencePack]] = []
    for pack in REFERENCE_PACKS:
        score = sum(1 for keyword in pack.keywords if keyword in normalized)
        if score > 0:
            scored.append((score, pack))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]

# Smart Report MVP v3

Персональный аналитический движок по матричному методу: вопрос → матрица доменов × слоёв → блоки с источниками → кросс-доменные бисоциации.

**v3 — это clean-room rebuild v2.** См. `reference/BRAINSTORM_BRIEF.md` (10 дефектов v2) и `reference/SMART_REPORT_MVP_BRIEF.md` (продуктовая спецификация).

## Быстрый старт

```bash
cp .env.example .env
# вписать OPENROUTER_API_KEY и PERPLEXITY_API_KEY

uv sync  # или: pip install -e .

python run.py --dry-run "Что определяет успех девелопера в бизнес-сегменте Москвы — бренд, скорость или продукт?"
```

## Структура

```
smart-report-mvp-v3/
├── run.py                # CLI entrypoint
├── smart_report/         # core async pipeline
│   ├── orchestrator.py   # run full flow
│   ├── planner.py
│   ├── scout.py
│   ├── analyst.py
│   ├── bisociator.py
│   ├── models.py         # pydantic schemas
│   ├── llm.py            # OpenRouter wrapper
│   ├── search.py         # Perplexity wrapper
│   └── io.py             # prompts/artefacts IO
├── prompts/              # editable role prompts
├── eval/                 # bakeoffs + baselines
├── reference/            # reference reports + briefs
├── runs/                 # per-run artefacts (gitignored)
└── tests/
```

## Roles

| Role | Model | Responsibility |
| --- | --- | --- |
| Planner | `anthropic/claude-opus-4` | question → Matrix (domains × layers + scout tasks) |
| Scout | `anthropic/claude-haiku-4.5` | scout task → findings (claim + number + URL + quote) |
| Analyst | `anthropic/claude-sonnet-4.6` | cell + findings → Block (conclusion + gaps + entities) |
| Bisociator | `anthropic/claude-opus-4` | blocks → CrossLinks (named shared variable) |

## Ссылки

- `HANDOFF.md` — actual state, what's done, what's next
- `SCRATCHPAD.md` — live progress during parallel tracks
- `eval/scout_bakeoff.md` — which retrieval strategy won
- `eval/baseline.md` — comparison against Perplexity / OpenAI DR / v2

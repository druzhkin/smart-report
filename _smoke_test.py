"""Smoke test: build a minimal Report, render infographics, export docx+pptx."""
from pathlib import Path
from models import (
    Report, Matrix, Domain, Layer, Block, Finding, Connection,
    BlockHeader, ExecutiveSummary, TopFinding, TopConnection,
)
from infographics import render_all
from export_docx import export_mckinsey_docx
from export_pptx import export_pptx

r = Report(
    goal="Тестовая цель для проверки инфографики и экспорта",
    planner_question_type="exploratory",
    matrix=Matrix(
        goal="Тестовая цель",
        domains=[
            Domain(name="Технологии", rationale="Ключевой домен",
                   layers=[Layer(name="AI", description="ии"),
                           Layer(name="IoT", description="иот"),
                           Layer(name="Робототехника", description="роботы")]),
            Domain(name="Экономика", rationale="Макро",
                   layers=[Layer(name="ВВП", description="ввп"),
                           Layer(name="Инфляция", description="инфл")]),
            Domain(name="Демография", rationale="Люди",
                   layers=[Layer(name="Старение", description="старение"),
                           Layer(name="Миграция", description="миграция")]),
        ],
        cell_plans=[],
    ),
    blocks=[
        Block(cell="Технологии / AI",
              summary="AI растёт быстро. Это второй абзац про AI.",
              findings=[Finding(claim="Рынок AI достиг 500 млрд долл в 2025",
                                source="McKinsey 2025",
                                source_type="primary", has_numbers=True)],
              gaps=["Нет данных по РФ-сегменту"], key_entities=["AI"],
              assumptions=["Стабильный рост инвестиций"]),
        Block(cell="Экономика / ВВП",
              summary="ВВП РФ растёт на 2% в 2025.",
              findings=[Finding(claim="ВВП РФ 2 трлн долл в 2025",
                                source="Росстат", source_type="primary",
                                has_numbers=True)],
              gaps=["Прогноз до 2030 неизвестен"], key_entities=["ВВП"],
              assumptions=["Санкции сохраняются"]),
        Block(cell="Демография / Старение",
              summary="Население РФ стареет: 20% старше 65 к 2030.",
              findings=[Finding(claim="20% населения РФ старше 65 к 2030",
                                source="Росстат демография",
                                source_type="primary", has_numbers=True)],
              gaps=["Региональный разрез"], key_entities=["старение"],
              assumptions=["Продолжительность жизни растёт"]),
    ],
    connections=[
        Connection(domains=["Технологии", "Экономика"],
                   shared_entity="капитальные инвестиции", nature="causal_chain",
                   description="AI требует капитала, ВВП его ограничивает",
                   strength="strong", anchors=["500 млрд", "2 трлн"],
                   novelty="Связка видна только при сопоставлении масштабов"),
        Connection(domains=["Демография", "Технологии"],
                   shared_entity="рабочая сила", nature="paradox",
                   description="Старение снижает рабочую силу — AI замещает, но не везде",
                   strength="moderate", anchors=["20% старше 65"],
                   novelty="Парадокс: автоматизация идёт туда, где люди были не нужны"),
    ],
    exec_summary=ExecutiveSummary(
        goal_restate="Проверка работы всех экспортов",
        matrix_table_md="| Домен | Слои |\n|---|---|\n| Технологии | AI, IoT, Робо |\n| Экономика | ВВП, Инфляция |\n| Демография | Старение, Миграция |",
        top_findings=[
            TopFinding(headline="AI занимает 500 млрд долл мирового рынка", block_cell="Технологии / AI"),
            TopFinding(headline="Старение: 20% населения РФ >65 к 2030", block_cell="Демография / Старение"),
            TopFinding(headline="ВВП РФ стабилизирован на 2 трлн долл", block_cell="Экономика / ВВП"),
        ],
        top_connections=[
            TopConnection(headline="Капитал течёт туда, где стареет рабсила", domains=["Технологии","Демография"]),
            TopConnection(headline="ВВП ограничивает скорость AI", domains=["Технологии","Экономика"]),
        ],
        key_gaps=["Нет регионального разреза демографии", "Прогноз ВВП 2030 отсутствует"],
    ),
    block_headers=[
        BlockHeader(cell="Технологии / AI", one_liner="AI становится капиталоёмким рынком",
                    strongest_number="500 млрд долл в 2025", main_gap="нет РФ-данных",
                    priority="high", score_novelty=3, score_concreteness=3, score_applicability=3),
        BlockHeader(cell="Экономика / ВВП", one_liner="ВВП стагнирует",
                    strongest_number="2 трлн долл", main_gap="нет прогноза",
                    priority="medium", score_novelty=2, score_concreteness=2, score_applicability=2),
        BlockHeader(cell="Демография / Старение", one_liner="Старение ускоряется",
                    strongest_number="20% старше 65 к 2030", main_gap="нет регионов",
                    priority="high", score_novelty=2, score_concreteness=3, score_applicability=3),
    ],
)

imgs = render_all(r, stem="smoke-test")
print("IMAGES:")
for k, p in imgs.items():
    print(f"  {k}: exists={p.exists()} size={p.stat().st_size if p.exists() else 0} bytes")

out_docx = Path("reports/smoke-test.docx")
export_mckinsey_docx(r, out_docx, imgs)
print(f"DOCX: exists={out_docx.exists()} size={out_docx.stat().st_size}")

out_pptx = Path("reports/smoke-test.pptx")
export_pptx(r, out_pptx, imgs)
print(f"PPTX: exists={out_pptx.exists()} size={out_pptx.stat().st_size}")

print("SMOKE OK")

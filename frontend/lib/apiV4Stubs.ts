import type {
  AnalysisOutput,
  DetectedTool,
  FinalReport,
  ResearchPrompt,
  V4Session,
} from "./apiV4";

export function stubSession(id: string, question: string): V4Session {
  return {
    session_id: id,
    raw_question: question,
    research_prompt: null,
    source_reports: [],
    analysis: null,
    followup_reports: [],
    final_report: null,
    status: "created",
    created_at: new Date().toISOString(),
    total_cost_rub: 0,
  };
}

export const STUB_PROMPT: ResearchPrompt = {
  full_prompt:
    "Проведи глубокое исследование факторов успеха девелоперов в бизнес-сегменте Москвы (2023–2025). Назови по имени 6 крупнейших игроков (Донстрой, MR Group, Level Group, ПИК, Эталон, Sminex), для каждого приведи: (1) долю в продажах премиум-сегмента с источником, (2) NPS или эквивалентный замер удовлетворённости, (3) процент переноса срока сдачи на erzrf.ru. Сравни маркетинговые бюджеты (% от выручки) и скорость строительства (метров в квартал на объект). Структурируй ответ как: факты по каждому игроку → кросс-сравнение → интерпретация → ограничения данных.",
  reasoning:
    "Вопрос 'что определяет успех' слишком широкий без якорей. Этот промт навязывает: конкретные имена компаний (иначе получим tech-vendor bias), три обязательные метрики (иначе получим narrative без цифр), требование источников (иначе нельзя проверить), явную структуру (иначе модель растечётся).",
  expected_structure: [
    "По каждому из 6 девелоперов: доля / NPS / перенос срока",
    "Кросс-сравнение: маркетинг vs скорость vs продукт",
    "Интерпретация и ограничения данных",
  ],
  key_entities: ["Донстрой", "MR Group", "Level Group", "ПИК", "Эталон", "Sminex", "erzrf.ru"],
  tips_for_search:
    "Perplexity Deep Research — для конкретных цифр (доли, сроки); OpenAI Deep Research — для сравнительных обзоров; Claude — если нужно разобрать длинный отраслевой обзор целиком.",
};

export const STUB_ANALYSIS: AnalysisOutput = {
  per_source_summary: [
    {
      detected_tool: "perplexity",
      filename: "perplexity_developer_success.md",
      main_claims: [
        "Донстрой держит 0% переноса срока на erzrf.ru за 2025",
        "MR Group ~5.65%, Level ~8.67%",
      ],
      strengths: "Конкретные цифры с прямыми ссылками на erzrf.ru",
      weaknesses: "Слабая интерпретация — что эти цифры значат для покупателя",
    },
    {
      detected_tool: "openai_dr",
      filename: "openai_dr_moscow_developers.md",
      main_claims: [
        "Бренд важнее скорости в премиум-сегменте",
        "Sminex и Донстрой — лидеры по NPS",
      ],
      strengths: "Хороший разбор mechanism'а — почему бренд работает",
      weaknesses: "Мало конкретных цифр, выводы на 'эксперты считают'",
    },
  ],
  consensus: [
    {
      claim: "Донстрой и Sminex — лидеры по удовлетворённости покупателей бизнес-класса",
      supporting_sources: ["perplexity", "openai_dr"],
      confidence: "high",
    },
    {
      claim: "Перенос срока сдачи — критичный фактор доверия для премиум-покупателя",
      supporting_sources: ["openai_dr", "claude"],
      confidence: "medium",
    },
  ],
  conflicts: [
    {
      topic: "Главный фактор успеха",
      source_a: "perplexity",
      claim_a: "Скорость строительства — главный KPI (по поведению продаж)",
      source_b: "openai_dr",
      claim_b: "Бренд и продуктовая архитектура важнее скорости",
      resolution_hint:
        "Вероятно оба правы для разных сегментов — бренд решает в премиум, скорость в бизнесе. Нужны разрезы по сегменту.",
      importance: "critical",
    },
  ],
  gaps: [
    {
      topic: "Маркетинговые бюджеты как % от выручки",
      why_critical:
        "Без этого нельзя сравнить эффективность бренда — высокий NPS при 15% маркетинга и при 3% маркетинга значит разное.",
      what_to_find: "Годовые отчёты / SPARK-Interfax по 6 девелоперам за 2023–2024",
      candidate_sources: ["spark-interfax.ru", "годовые отчёты на сайтах компаний"],
    },
  ],
  unverified_numbers: [
    {
      value: "35.46%",
      metric: "перенос срока сдачи 2025",
      subject: "Эталон",
      source_tool: "perplexity",
      why_unverified:
        "Цифра выглядит завышенной относительно публичной отчётности — возможна путаница с 2024.",
    },
  ],
  quality_notes:
    "Три источника согласны в главном (лидеры = Донстрой+Sminex), расходятся в причинах (цифры vs нарратив). Один критический конфликт по роли скорости, один серьёзный gap по маркетинг-бюджетам.",
  // Canonical single consolidated prompt (v4.1+) — one DR session covers all gaps and conflicts.
  followup_prompt: {
    prompt_id: "fp_consolidated",
    intent: "fill_gap",
    prompt:
      "## Gap: Маркетинговые бюджеты девелоперов\n" +
      "Найди на spark-interfax.ru маркетинговые расходы как % от выручки за 2023 и 2024 для: Донстрой, MR Group, Level Group, ПИК, Эталон, Sminex. По каждому — абсолютная сумма расходов на маркетинг и процент от выручки со ссылкой на конкретную страницу отчётности.\n\n" +
      "## Gap: Верификация переноса Эталона\n" +
      "Проверь на erzrf.ru — какой процент переноса срока сдачи у Эталона за 2024 и 2025 отдельно? Нужны цифры по обоим годам со ссылкой на страницу девелопера на erzrf.ru. Цифра 35.46% за 2025 вызывает сомнения — уточни.\n\n" +
      "## Conflict: Главный фактор успеха (бренд vs скорость строительства)\n" +
      "Раздели анализ факторов успеха для двух сегментов отдельно: бизнес-класс (25–45 млн ₽) vs премиум (45+ млн ₽) в Москве 2023–2025. По каждому сегменту — какие факторы (бренд / скорость / продуктовая архитектура) имеют наибольшую корреляцию с долей рынка и ценовой премией к рынку? Нужны данные с источниками.",
    target_info: "2 gaps + 1 conflict",
    suggested_tool: "perplexity",
    suggested_source_site: "erzrf.ru",
    priority: "must",
    linked_to: "gap:маркетинг-бюджеты | gap:верификация-эталона | conflict:фактор-успеха",
  },
  // Legacy shim list — mirrors followup_prompt for backward-compat readers.
  followup_prompts: [
    {
      prompt_id: "fp_consolidated",
      intent: "fill_gap",
      prompt:
        "## Gap: Маркетинговые бюджеты девелоперов\n" +
        "Найди на spark-interfax.ru маркетинговые расходы как % от выручки за 2023 и 2024 для: Донстрой, MR Group, Level Group, ПИК, Эталон, Sminex. По каждому — абсолютная сумма расходов на маркетинг и процент от выручки со ссылкой на конкретную страницу отчётности.\n\n" +
        "## Gap: Верификация переноса Эталона\n" +
        "Проверь на erzrf.ru — какой процент переноса срока сдачи у Эталона за 2024 и 2025 отдельно? Нужны цифры по обоим годам со ссылкой на страницу девелопера на erzrf.ru. Цифра 35.46% за 2025 вызывает сомнения — уточни.\n\n" +
        "## Conflict: Главный фактор успеха (бренд vs скорость строительства)\n" +
        "Раздели анализ факторов успеха для двух сегментов отдельно: бизнес-класс (25–45 млн ₽) vs премиум (45+ млн ₽) в Москве 2023–2025. По каждому сегменту — какие факторы (бренд / скорость / продуктовая архитектура) имеют наибольшую корреляцию с долей рынка и ценовой премией к рынку? Нужны данные с источниками.",
      target_info: "2 gaps + 1 conflict",
      suggested_tool: "perplexity",
      suggested_source_site: "erzrf.ru",
      priority: "must",
      linked_to: "gap:маркетинг-бюджеты | gap:верификация-эталона | conflict:фактор-успеха",
    },
  ],
};

export function stubFinalReport(id: string, question: string): FinalReport {
  return {
    session_id: id,
    question: question || "Что определяет успех девелопера в бизнес-сегменте Москвы",
    research_prompt_used: STUB_PROMPT.full_prompt,
    executive_summary: {
      main_answer:
        "В премиум-сегменте Москвы доминируют бренд и ритуал сдачи (соблюдение сроков), в бизнес-классе — скорость и продуктовая связка. Донстрой и Sminex держат лидерство за счёт одновременной дисциплины сроков (0% переносов) и сильного бренда; скорость без бренда (как у ПИК) даёт объём, но не премию.",
      ranking: "Донстрой > Sminex > Level ≈ MR > Эталон > ПИК (по премии к бенчмарку)",
      top_findings: [
        "Донстрой — 0% переноса срока на erzrf.ru за 2025, единственный среди топ-6",
        "Эталон с переносом 35% требует верификации — возможно ошибка в одном из источников",
        "Маркетинг-бюджеты остаются gap'ом для количественного сравнения бренд-эффекта",
      ],
      key_numbers: [
        { value: "0%", metric: "перенос срока 2025", source: "erzrf.ru (Донстрой)" },
        { value: "5.65%", metric: "перенос срока 2025", source: "erzrf.ru (MR Group)" },
        { value: "8.67%", metric: "перенос срока 2025", source: "erzrf.ru (Level Group)" },
      ],
      confidence_note:
        "Высокая по цифрам переносов (erzrf.ru подтверждён в двух источниках). Средняя по интерпретации. Низкая по маркетинг-бюджетам — gap не закрыт.",
      what_meta_adds:
        "Ни один из трёх исходных отчётов в одиночку не синтезировал разрез бизнес vs премиум — это возникает только при сопоставлении конфликта OpenAI DR vs Perplexity.",
    },
    main_synthesis:
      "## Что определяет успех\n\nТри источника сходятся в том, что **Донстрой и Sminex — лидеры бизнес-сегмента Москвы**, но расходятся в объяснении причины: Perplexity выводит на первый план скорость (метрика — перенос срока), OpenAI DR делает ставку на бренд и продуктовую архитектуру. Конфликт разрешается через разрез по подсегменту — бренд доминирует в премиум (45+ млн ₽), скорость в бизнес-классе (25–45 млн ₽).\n\n**Критическая цифра**: 0% переносов у Донстроя за 2025 (erzrf.ru). В отрасли со средним переносом 8–10% это не просто операционная эффективность, это системный сигнал покупателю.\n\n**Неразрешённый вопрос**: маркетинг-бюджеты как процент выручки. Без этого нельзя измерить бренд-премию в рублях.",
    consensus_section:
      "- Донстрой и Sminex — лидеры по удовлетворённости (high confidence)\n- Перенос срока — критичный фактор доверия (medium confidence, два источника)",
    conflicts_section:
      "**Главный фактор успеха**: Perplexity vs OpenAI DR расходятся (скорость vs бренд). Резолюция: оба правы в разных подсегментах.",
    gaps_filled_section:
      "Gap по маркетинг-бюджетам остался незакрытым — требует добора по SPARK-Interfax.",
    all_sources: [
      { url: "https://erzrf.ru/zastroyschiki/moskva/donstroy", title: "Донстрой на ЕРЗ", origin: "perplexity" },
      { url: "https://erzrf.ru/zastroyschiki/moskva/mr-group", title: "MR Group на ЕРЗ", origin: "perplexity" },
    ],
    metadata: { stub: true, generated_at: new Date().toISOString() },
  };
}

export function detectTool(filename: string): DetectedTool {
  const f = filename.toLowerCase();
  if (f.includes("perplex") || f.includes("pplx")) return "perplexity";
  if (f.includes("openai") || f.includes("chatgpt") || f.includes("_dr")) return "openai_dr";
  if (f.includes("claude")) return "claude";
  return "other";
}

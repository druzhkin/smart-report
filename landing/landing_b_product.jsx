// Variant B — Product-led
function LandingB() {
  return (
    <>
      <window.Topbar variant="b" ctaLabel="Открыть демо" />

      {/* HERO with live demo */}
      <section className="vb-hero">
        <div className="lp-container">
          <div className="vb-hero-head">
            <div>
              <div className="lp-eyebrow">Research orchestrator · v.IV</div>
              <h1 className="vb-headline">
                AI с настоящим методом. <em>Видно прямо в продукте.</em>
              </h1>
            </div>
            <div>
              <p className="vb-sub">
                В промпты Smart Report зашиты четыре аналитических протокола: <strong>MECE</strong> декомпозирует ваш вопрос, <strong>ACH</strong> сравнивает гипотезы пяти DR в единой матрице, <strong>Key Assumptions Check</strong> ловит скрытые допущения, <strong>Pyramid Principle</strong> собирает финал. Не маркетинг — реальные инструкции. Ниже — как это выглядит в UI.
              </p>
              <p className="vb-sub-meta">↓ Промт → Промт-инженерия → 5 DR → Критика → Отчёт</p>
            </div>
          </div>

          <div className="vb-demo-frame">
            <div className="vb-demo-bar">
              <div className="vb-demo-dots"><span className="vb-demo-dot"></span><span className="vb-demo-dot"></span><span className="vb-demo-dot"></span></div>
              <div className="vb-demo-url">smartreport.io / s / e7d2 — Премиум-резиденции в Тбилиси</div>
              <div className="vb-demo-tag">Live · Phase 04</div>
            </div>

            <div className="vb-demo-screen">
              <div className="vb-demo-side">
                <div className="vb-demo-side-h">Сегодня</div>
                <div className="vb-demo-side-item active">
                  Премиум-резиденции, Тбилиси
                  <div className="vb-demo-side-meta">phase 04 · 8 мин</div>
                </div>
                <div className="vb-demo-side-item">EV-зарядки в РФ</div>
                <div className="vb-demo-side-item">Pet-food D2C</div>
                <div className="vb-demo-side-h" style={{marginTop: 16}}>Архив</div>
                <div className="vb-demo-side-item">B2B SaaS pricing</div>
                <div className="vb-demo-side-item">Lithium supply 2026</div>
                <div className="vb-demo-side-item">Кофе спешелти РФ</div>
              </div>

              <div className="vb-demo-chat">
                <div className="vb-demo-msg user">
                  Оцени рынок премиум-резиденций (от $400k) в Тбилиси на 2026. Кто игроки, какая динамика, какие риски для покупателя из РФ.
                </div>
                <div className="vb-demo-msg system">
                  <strong>MECE-декомпозиция.</strong> Развернул вопрос в 12 непересекающихся подвопросов · покрытие проверено. Запускаю 5 DR.
                </div>
                <div className="vb-demo-msg system">
                  <strong>ACH — Analysis of Competing Hypotheses.</strong> Найдено <span style={{color: "var(--accent-ink)", fontWeight: 600}}>3 расхождения гипотез</span>: объём рынка ($1.2B vs $4.1B), доля русскоязычных покупателей (18% vs 41%), регуляторные риски — налог на нерезидентов. Все версии в матрице доказательств.<span className="vb-demo-cite">[12]</span>
                </div>
                <div className="vb-demo-msg system">
                  <strong>Key Assumptions Check.</strong> Выписаны 7 неявных допущений · 2 помечены как критичные. Запустил 8 узконаправленных проб для верификации. <span style={{fontFamily: "var(--mono)", color: "var(--ink-3)", fontSize: 11}}>3/8 завершено · ETA 2 мин</span>
                </div>
                <div className="vb-demo-stepper">
                  <div className="vb-demo-step done">01 Вопрос</div>
                  <div className="vb-demo-step done">02 MECE</div>
                  <div className="vb-demo-step done">03 ACH</div>
                  <div className="vb-demo-step active">04 KAC</div>
                  <div className="vb-demo-step">05 Pyramid</div>
                </div>
              </div>

              <div className="vb-demo-art">
                <div className="vb-demo-art-h">Финальный отчёт · превью</div>
                <div className="vb-demo-art-title">Премиум-резиденции в Тбилиси: рынок, игроки и риски для покупателя из РФ</div>
                <div className="vb-demo-art-meta">7 разделов · 38 страниц · 214 цитат</div>

                <div className="vb-demo-art-h3">1. Объём и динамика <span style={{fontFamily: "var(--mono)", fontSize: 9, color: "var(--ink-3)", marginLeft: 8, fontWeight: 500}}>▰▰▰▰ ТОЧНО</span></div>
                <p>Рынок резиденций &gt; $400k оценивается в <span className="vb-demo-art-num">$1.4–1.7B</span>{' '}на 2026 год после нормализации источников.<span className="vb-demo-cite">[03]</span></p>

                <div className="vb-demo-art-h3">2. Игроки <span style={{fontFamily: "var(--mono)", fontSize: 9, color: "var(--ink-3)", marginLeft: 8, fontWeight: 500}}>▰▰▰▱ СКОРЕЕ ВСЕГО</span></div>
                <p>15 девелоперов с проектами от $400k. Top-5 контролируют <span className="vb-demo-art-num">61%</span>{' '}предложения, лидер — 22%.<span className="vb-demo-cite">[07]</span></p>

                <div className="vb-demo-art-h3">3. Покупатель из РФ <span style={{fontFamily: "var(--mono)", fontSize: 9, color: "var(--ink-3)", marginLeft: 8, fontWeight: 500}}>▰▰▱▱ ЕСТЬ МНЕНИЕ</span></div>
                <p>Доля — <span className="vb-demo-art-num">28%</span>{' '}(после согласования источников). Расхождение по источникам ×2.3.<span className="vb-demo-cite">[11]</span></p>

                <div className="vb-demo-art-h3">4. Ключевые допущения <span style={{fontFamily: "var(--mono)", fontSize: 9, color: "var(--accent-ink)", marginLeft: 8, fontWeight: 500}}>KAC · 2 КРИТИЧНЫХ</span></div>
                <p>Сохранение SWIFT-ограничений на 2026. Стабильность валюты. Если меняется — выводы по разделу 3 пересматриваются.</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="vb-spacer"></div>

      {/* FEATURES */}
      <section className="lp-section-tight">
        <div className="lp-container">
          <div className="lp-section-head">
            <div className="lp-eyebrow">Что внутри</div>
            <div>
              <h2 className="lp-section-title">Аналитический метод — <em style={{fontFamily: "var(--serif)", fontStyle: "italic", fontWeight: 400, color: "var(--accent-ink)"}}>видно в каждом компоненте</em>.</h2>
              <p className="lp-section-sub">Каждая фича — это конкретный шаг настоящего исследования, который один Deep Research не делает в принципе.</p>
            </div>
          </div>

          <div className="vb-features">
            <div className="vb-feature">
              <div className="vb-feature-icon">M</div>
              <h4>MECE-декомпозиция</h4>
              <p>Перед поиском раскладываем вопрос на 10–14 непересекающихся подвопросов, в сумме покрывающих всё пространство задачи. Стандарт McKinsey.</p>
              <div className="vb-feature-meta">Mutually Exclusive · Collectively Exhaustive</div>
            </div>
            <div className="vb-feature">
              <div className="vb-feature-icon">⊥</div>
              <h4>ACH — конкурирующие гипотезы</h4>
              <p>Когда 5 DR расходятся, не выбираем «лучший». Сводим версии в матрицу гипотез × доказательств — методом Analysis of Competing Hypotheses из аналитической традиции.</p>
              <div className="vb-feature-meta">Матрица гипотез · все версии видны</div>
            </div>
            <div className="vb-feature">
              <div className="vb-feature-icon">?</div>
              <h4>Key Assumptions Check</h4>
              <p>В конце каждого аналитического блока выписываем неявные допущения и помечаем критичные. Самая опасная часть вывода — то, что считалось «и так понятно».</p>
              <div className="vb-feature-meta">Реестр критичных допущений</div>
            </div>
            <div className="vb-feature">
              <div className="vb-feature-icon">▲</div>
              <h4>Pyramid Principle (Минто)</h4>
              <p>Финал собран по принципу пирамиды Минто: главный вывод сверху, обоснования ниже по убыванию веса. Так устроены все слайд-доки McKinsey, BCG, Bain.</p>
              <div className="vb-feature-meta">Главный вывод → обоснования</div>
            </div>
            <div className="vb-feature">
              <div className="vb-feature-icon">▰</div>
              <h4>4 уровня доказательности</h4>
              <p>У каждого утверждения — уровень: <strong>точно</strong> (≥2 авторитетных источника), <strong>скорее всего</strong>, <strong>есть мнение</strong>, <strong>только догадка</strong>. Большинство AI-инструментов подают всё одной интонацией уверенности.</p>
              <div className="vb-feature-meta">Точно · Скорее всего · Есть мнение · Догадка</div>
            </div>
            <div className="vb-feature">
              <div className="vb-feature-icon">▣</div>
              <h4>Готовая презентация</h4>
              <p>Не только отчёт — но и полноценный PPTX-deck. Структура, тезисы, графики, цитаты. Открывается в PowerPoint, Keynote, Google Slides.</p>
              <div className="vb-feature-meta">Один клик — готовая презентация</div>
            </div>
            <div className="vb-feature">
              <div className="vb-feature-icon">[ ]</div>
              <h4>Цитируемые источники</h4>
              <p>200+ цитат на отчёт. Каждый тезис — со ссылкой на конкретный источник. Унифицированная библиография в конце.</p>
              <div className="vb-feature-meta">Научные базы + открытые данные</div>
            </div>
            <div className="vb-feature">
              <div className="vb-feature-icon">RU</div>
              <h4>Платежи в рублях</h4>
              <p>Карта РФ, СБП, ЮKassa, Тинькофф, USDT. Без зарубежных подписок и танцев с виртуальными картами.</p>
              <div className="vb-feature-meta">Также — BYOK с подпиской ₽2 500</div>
            </div>
          </div>
        </div>
      </section>

      {/* TOUR */}
      <section className="lp-section">
        <div className="lp-container">
          <div className="lp-eyebrow" style={{marginBottom: 24}}>Тур по продукту</div>

          <div className="vb-tour-row">
            <div className="vb-tour-text">
              <div className="lp-eyebrow">Phase 01 — Вопрос</div>
              <h3>Опишите задачу как <em>старшему аналитику</em>.</h3>
              <p>Контекст, гипотезы, ограничения. Прикрепите файлы — внутренние данные, презентации, отчёты конкурентов. Никаких «магических» промтов от вас не требуется.</p>
              <ul className="vb-tour-list">
                <li><span>Длина</span><span>2–3 абзаца достаточно</span></li>
                <li><span>Файлы</span><span>PDF, DOCX, XLSX, CSV, изображения</span></li>
                <li><span>Контекст</span><span>Сохраняется в проекте — следующий вопрос продолжает</span></li>
              </ul>
            </div>
            <div className="vb-tour-art">
              <div className="vb-tour-art-h">Phase 01 · вопрос</div>
              <div style={{fontFamily: "var(--sans)", fontSize: 13, color: "var(--ink)", lineHeight: 1.55}}>
                <strong>Задача:</strong> Оценить рынок премиум-резиденций (&gt; $400k) в Тбилиси на 2026 год.<br/><br/>
                <strong>Гипотеза:</strong> рынок насыщается, но доля российских покупателей растёт.<br/><br/>
                <strong>Что нужно на выходе:</strong> объём, top-игроки, риски для покупателя из РФ, прогноз на 2027.<br/><br/>
                <span style={{color: "var(--ink-3)"}}>📎 NAPR_q3_2025.pdf · GaltTaggart_RealEstate.pdf</span>
              </div>
            </div>
          </div>

          <div className="vb-tour-row">
            <div className="vb-tour-text">
              <div className="lp-eyebrow">Phase 03 — ACH</div>
              <h3>Все гипотезы видны. <em>Не одна.</em></h3>
              <p>5 DR редко полностью согласны. Один источник пишет «$4B», другой — «$1.2B». Большинство AI-инструментов выбирают «более уверенный» ответ — и теряют главное. Мы используем <strong>Analysis of Competing Hypotheses</strong> — методику, разработанную в аналитической традиции разведки: все версии сводятся в одну матрицу, где видно, какие доказательства какой гипотезе соответствуют.</p>
              <ul className="vb-tour-list">
                <li><span>Метод</span><span>ACH · Heuer, 1999</span></li>
                <li><span>Матрица</span><span>Гипотезы × доказательства</span></li>
                <li><span>Отчёт</span><span>Все версии — отдельным разделом</span></li>
              </ul>
            </div>
            <div className="vb-tour-art">
              <div className="vb-tour-art-h">Phase 03 · противоречия (3)</div>
              <div style={{fontFamily: "var(--sans)", fontSize: 12, color: "var(--ink-2)", lineHeight: 1.55}}>
                <div style={{borderBottom: "1px solid var(--rule)", paddingBottom: 12, marginBottom: 12}}>
                  <strong style={{color: "var(--ink)"}}>⊥ Объём рынка</strong><br/>
                  <span style={{fontFamily: "var(--mono)", fontSize: 10, color: "var(--ink-3)"}}>Источник A · $4.1B</span><br/>
                  <span style={{fontFamily: "var(--mono)", fontSize: 10, color: "var(--ink-3)"}}>Источник B · $1.2B</span><br/>
                  <span style={{fontFamily: "var(--mono)", fontSize: 10, color: "var(--accent-ink)"}}>→ запущен добор</span>
                </div>
                <div style={{borderBottom: "1px solid var(--rule)", paddingBottom: 12, marginBottom: 12}}>
                  <strong style={{color: "var(--ink)"}}>⊥ Доля RU-покупателей</strong><br/>
                  <span style={{fontFamily: "var(--mono)", fontSize: 10, color: "var(--ink-3)"}}>Источник C · 18%</span><br/>
                  <span style={{fontFamily: "var(--mono)", fontSize: 10, color: "var(--ink-3)"}}>Источник D · 41%</span>
                </div>
                <div>
                  <strong style={{color: "var(--ink)"}}>⊥ Налог нерезидентов</strong><br/>
                  <span style={{fontFamily: "var(--mono)", fontSize: 10, color: "var(--ink-3)"}}>2 источника · противоречат</span>
                </div>
              </div>
            </div>
          </div>

          <div className="vb-tour-row">
            <div className="vb-tour-text">
              <div className="lp-eyebrow">Phase 05 — Pyramid Principle</div>
              <h3>Pyramid Principle. <em>Главный вывод сверху.</em></h3>
              <p>Финальный отчёт собран по принципу пирамиды Минто: главный вывод сверху, обоснования — ниже по убыванию веса. Каждый тезис помечен уровнем доказательности: <strong>точно / скорее всего / есть мнение / догадка</strong>. Готовая презентация в PPTX — в один клик.</p>
              <ul className="vb-tour-list">
                <li><span>Метод</span><span>Pyramid Principle · Minto</span></li>
                <li><span>Доказательность</span><span>4 уровня у каждого тезиса</span></li>
                <li><span>Презентация</span><span>Executive-deck · PPTX</span></li>
                <li><span>Экспорт</span><span>PDF · DOCX · PPTX · Notion · MD · Google Docs</span></li>
              </ul>
            </div>
            <div className="vb-tour-art">
              <div className="vb-tour-art-h">Phase 05 · отчёт + презентация</div>
              <div style={{fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-2)", lineHeight: 1.7}}>
                <div style={{color: "var(--ink)", fontWeight: 600, marginBottom: 8}}>0 · EXECUTIVE SUMMARY</div>
                <div>1 · Объём и динамика</div>
                <div>2 · Игроки и доли</div>
                <div>3 · Покупатель из РФ — портрет и риски</div>
                <div>4 · Регуляторика на 2026</div>
                <div>5 · Прогноз на 2027</div>
                <div style={{color: "var(--accent-ink)"}}>6 · Противоречия в источниках (3)</div>
                <div>7 · Источники и методология</div>
                <div style={{color: "var(--ink-4)", marginTop: 8}}>А · Полные цитаты (214)</div>
                <div style={{color: "var(--ink-4)"}}>Б · Сырые ответы 5 DR</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Pricing strip — minimal under product-led */}
      <section id="price" className="lp-section-tight" style={{background: "var(--paper-2)"}}>
        <div className="lp-container">
          <div className="lp-section-head">
            <div className="lp-eyebrow">Цена</div>
            <div>
              <h2 className="lp-section-title">Один отчёт — <em style={{fontFamily: "var(--serif)", fontStyle: "italic", fontWeight: 400, color: "var(--accent-ink)"}}>₽10 000</em>.</h2>
              <p className="lp-section-sub">Без подписки, без токенов, без лимитов на длину документа. Один платёж — один полноценный исследовательский процесс.</p>
            </div>
          </div>

          <div className="va-pricing-grid">
            <div className="va-price-card">
              <div className="va-price-tag">Single</div>
              <h3 className="va-price-name">₽10 000 / отчёт</h3>
              <p className="va-price-desc">Заплатили — получили. Идеально для разовых задач.</p>
              <button className="lp-btn lp-btn-ghost">Заказать</button>
            </div>
            <div className="va-price-card">
              <div className="va-price-tag">Pack 5</div>
              <h3 className="va-price-name">₽39 000 / 5 отчётов</h3>
              <p className="va-price-desc">₽7 800 за отчёт. Для команд, которые исследуют регулярно.</p>
              <button className="lp-btn lp-btn-ghost">Купить пакет</button>
            </div>
            <div className="va-price-card">
              <div className="va-price-tag">BYOK</div>
              <h3 className="va-price-name">₽2 500 / месяц</h3>
              <p className="va-price-desc">Свои ключи. Безлимитная оркестрация. API.</p>
              <button className="lp-btn lp-btn-ghost">Подключить</button>
            </div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="va-final">
        <div className="lp-container">
          <h2>Поручите вопрос <em>методу</em>, а не AI-чату.</h2>
          <p>MECE → 5 DR → ACH → Key Assumptions Check → Pyramid Principle. Четыре аналитических протокола в каждом отчёте, прямо в промптах. ₽10 000 — один отчёт.</p>
          <div className="va-cta-row">
            <button className="lp-btn">Заказать отчёт <span className="lp-btn-arrow">→</span></button>
            <button className="lp-btn lp-btn-ghost">Посмотреть структуру</button>
          </div>
        </div>
      </section>

      <window.Footer />
    </>
  );
}

window.LandingB = LandingB;

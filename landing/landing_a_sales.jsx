// Variant A — Sales-heavy
const { useState: useStateA, useEffect: useEffectA, useRef: useRefA } = React;

// ---------------------------------------------------------------------------
// Lead modal — opens for every CTA. Posts to /api/lead. Auth on the landing
// is admin/admin (HTTP Basic) so the form is only visible to authed users.
// ---------------------------------------------------------------------------

function LeadModal({ open, packageId, onClose }) {
  const [name, setName] = useStateA("");
  const [email, setEmail] = useStateA("");
  const [message, setMessage] = useStateA("");
  const [status, setStatus] = useStateA("idle"); // idle | sending | ok | error
  const [errorText, setErrorText] = useStateA("");

  useEffectA(() => {
    if (!open) {
      setStatus("idle"); setErrorText("");
      setName(""); setEmail(""); setMessage("");
    }
  }, [open]);

  // Esc to close
  useEffectA(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const PACKAGE_TITLES = {
    start:        "Standard · ₽10 000 (разовый отчёт)",
    single:       "Single · ₽10 000 (разовый отчёт)",
    pack5:        "Pack 5 · ₽39 000 (5 отчётов)",
    subscription: "Subscription · ₽2 500/мес (BYOK)",
    generic:      "Запрос — Smart Report",
  };
  const subjectTitle = PACKAGE_TITLES[packageId] || PACKAGE_TITLES.generic;

  const submit = async (e) => {
    e.preventDefault();
    if (status === "sending") return;
    if (!email.trim()) { setStatus("error"); setErrorText("Укажите email"); return; }
    setStatus("sending"); setErrorText("");
    try {
      const r = await fetch("/api/lead", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          package: packageId || "generic",
          package_title: subjectTitle,
          name: name.trim(),
          email: email.trim(),
          message: message.trim(),
          source: "landing_a_sales",
          ts_iso: new Date().toISOString(),
        }),
      });
      if (!r.ok) {
        const txt = await r.text();
        setStatus("error"); setErrorText(`HTTP ${r.status}: ${txt.slice(0, 160)}`);
        return;
      }
      setStatus("ok");
    } catch (err) {
      setStatus("error"); setErrorText(String(err).slice(0, 160));
    }
  };

  return (
    <div className="lead-modal-backdrop" onClick={onClose}>
      <div className="lead-modal" onClick={(e) => e.stopPropagation()}>
        <button className="lead-modal-close" onClick={onClose} aria-label="Закрыть">×</button>

        {status === "ok" ? (
          <div className="lead-modal-success">
            <div className="lead-modal-eyebrow">Принято</div>
            <h3>Свяжемся в течение рабочего дня.</h3>
            <p>На <strong>{email}</strong> придёт подтверждение. Если что — напишите в Telegram, контакт в подвале.</p>
            <button className="lp-btn" onClick={onClose}>Закрыть</button>
          </div>
        ) : (
          <>
            <div className="lead-modal-eyebrow">Заявка</div>
            <h3>{subjectTitle}</h3>
            <p className="lead-modal-sub">Оставьте контакт — пришлём счёт и стартовый бриф. Никакой рассылки, только по этой заявке.</p>
            <form onSubmit={submit} className="lead-form">
              <label>
                <span>Имя</span>
                <input type="text" value={name} onChange={(e) => setName(e.target.value)}
                       placeholder="Как к вам обращаться" autoFocus />
              </label>
              <label>
                <span>Email <em>*</em></span>
                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                       placeholder="you@company.ru" required />
              </label>
              <label>
                <span>Что нужно (опционально)</span>
                <textarea rows="4" value={message} onChange={(e) => setMessage(e.target.value)}
                          placeholder="Опишите задачу одной-двумя фразами" />
              </label>
              {status === "error" && (
                <div className="lead-modal-error">{errorText || "Что-то пошло не так"}</div>
              )}
              <div className="lead-modal-actions">
                <button type="button" className="lp-btn lp-btn-ghost" onClick={onClose}>Отмена</button>
                <button type="submit" className="lp-btn" disabled={status === "sending"}>
                  {status === "sending" ? "Отправляем…" : "Отправить заявку →"}
                </button>
              </div>
            </form>
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Smooth scroll helper for in-page anchor buttons
// ---------------------------------------------------------------------------

function _scrollToId(id) {
  const el = document.getElementById(id);
  if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
}

function LandingA() {
  // SaaS pivot: "Заказать"/"Купить"/"Подключить"/"Оплатить" CTAs no longer
  // open a lead-capture modal. Smart Report is a self-serve SaaS — clicking
  // any purchase intent CTA jumps to /app/signup so the user creates an
  // account and runs the report themselves. Pre-Apr-26 the buttons opened
  // a "leave email, we'll contact" form; user feedback: "при чем тут
  // заявка и свяжутся. это саас".
  const goSignup = () => { window.location.href = "/app/signup.html"; };
  const goDashboard = () => { window.location.href = "/app/dashboard.html"; };

  // Topbar's CTA delegates to window.__landingCta — set so the shared
  // header doesn't need a prop drill into this component.
  useEffectA(() => { window.__landingCta = goSignup; return () => { delete window.__landingCta; }; }, []);

  return (
    <>
      <window.Topbar variant="a" />

      {/* HERO */}
      <section className="va-hero">
        <div className="lp-container">
          <div className="va-hero-grid">
            <div>
              <div className="va-tag-row">
                <span className="va-tag va-tag-accent">Research orchestrator</span>
                <span className="va-tag">5 параллельных DR</span>
                <span className="va-tag">Презентация в один клик</span>
                <span className="va-tag">RU · карты · СБП · USDT</span>
              </div>
              <h1 className="va-headline">
                AI с настоящим <em>аналитическим методом</em> — не просто поиском.
              </h1>
              <p className="va-sub">
                Smart Report — это не «AI с веб-поиском». Это система, в промпты которой зашиты четыре проверенных временем аналитических протокола: <strong>ACH</strong>, <strong>Key Assumptions Check</strong>, <strong>MECE</strong> и <strong>Pyramid Principle</strong>. То же самое, что senior-аналитик делает руками — на каждом отчёте, без пропусков. На выходе — документ, где у каждого утверждения помечен уровень доказательности.
              </p>
              <div className="va-cta-row">
                <button className="lp-btn" onClick={goSignup}>Заказать отчёт за ₽10 000 <span className="lp-btn-arrow">→</span></button>
                <button className="lp-btn lp-btn-ghost" onClick={() => _scrollToId("how")}>Посмотреть структуру отчёта</button>
                <span className="va-cta-meta">12–20 минут · 5 DR · 4 протокола · ₽10 000</span>
              </div>
            </div>

            {/* hero card */}
            <div className="va-hero-card">
              <span className="va-hero-card-tag">Старт</span>
              <div className="lp-eyebrow" style={{marginBottom: 8}}>Разовый отчёт</div>
              <h3>Smart Report · Standard</h3>
              <div className="va-hero-card-price">₽<em>10 000</em></div>
              <div className="va-hero-card-price-meta">за один полный отчёт · без подписки</div>
              <ul className="va-hero-card-list">
                <li>4 аналитических протокола в промптах: ACH · KAC · MECE · Pyramid</li>
                <li>Уровень доказательности у каждого утверждения</li>
                <li>5 параллельных Deep Research + критика + добор</li>
                <li>Честное «нет данных» вместо красивой выдумки</li>
                <li>Отчёт + презентация · все основные форматы</li>
              </ul>
              <button className="lp-btn" onClick={goSignup}>Оплатить и начать <span className="lp-btn-arrow">→</span></button>
            </div>
          </div>
        </div>
      </section>

      {/* FACTS STRIP */}
      <section className="lp-container" style={{marginTop: -1}}>
        <div className="va-facts">
          <div className="va-fact">
            <div className="va-fact-num"><em>×4</em></div>
            <div className="va-fact-label">Аналитических протокола</div>
            <div className="va-fact-desc">ACH, Key Assumptions Check, MECE, Pyramid Principle — четыре стандарта стратегического анализа, зашитых в промпты. Не маркетинг — реальные инструкции.</div>
          </div>
          <div className="va-fact">
            <div className="va-fact-num">214</div>
            <div className="va-fact-label">Цитат в среднем</div>
            <div className="va-fact-desc">Каждое утверждение в отчёте опирается на конкретный источник. Унифицированный список в конце — методологически корректная библиография.</div>
          </div>
          <div className="va-fact">
            <div className="va-fact-num">3<em>×</em></div>
            <div className="va-fact-label">Слоя анализа</div>
            <div className="va-fact-desc">Промт-инженерия превращает вопрос в 10–14 sub-questions. Фаза критики выявляет противоречия. Фаза добора — закрывает их. Это не поиск, это исследование.</div>
          </div>
          <div className="va-fact">
            <div className="va-fact-num">12–20<em> мин</em></div>
            <div className="va-fact-label">До готового документа</div>
            <div className="va-fact-desc">Глубина, на которую у живой команды ушло бы 4–6 часов. Не за счёт упрощения — за счёт параллелизации.</div>
          </div>
        </div>
      </section>

      {/* PROBLEM */}
      <section className="lp-section">
        <div className="lp-container">
          <div className="lp-section-head">
            <div className="lp-eyebrow">01 · Проблема</div>
            <div>
              <h2 className="lp-section-title">«AI с поиском» — это не аналитик. <br/>Это <em>стажёр с гуглом</em>.</h2>
              <p className="lp-section-sub">
                Любой современный AI-агент умеет искать в вебе и пересказывать найденное. Полезно — но это не анализ. Настоящая аналитика устроена иначе: метод декомпозиции вопроса, явное сравнение конкурирующих гипотез, проверка скрытых допущений, иерархия вывода и обоснований. Это инструменты, которые столетие назад изобрели разведка и стратегический консалтинг — и которые мы зашили в промпты Smart Report.
              </p>
            </div>
          </div>

          <div className="va-problem-grid">
            <div className="va-problem-card">
              <div className="va-problem-card-num">01 / 04</div>
              <h4>Нет декомпозиции вопроса</h4>
              <p>Стажёр получает большой вопрос и сразу гуглит. Аналитик первые 30 минут раскладывает его на подвопросы, проверяет на пересечения и полноту покрытия (метод MECE). Smart Report делает это до того, как открыть первый источник.</p>
            </div>
            <div className="va-problem-card">
              <div className="va-problem-card-num">02 / 04</div>
              <h4>Нет конкурирующих гипотез</h4>
              <p>AI-чат склонен выбрать одну версию и подкрепить её. Аналитик из разведки делает наоборот: <strong>ACH</strong> — Analysis of Competing Hypotheses — заставляет рассмотреть несколько версий одновременно и оценить их по одной матрице доказательств.</p>
            </div>
            <div className="va-problem-card">
              <div className="va-problem-card-num">03 / 04</div>
              <h4>Нет проверки допущений</h4>
              <p>Самая опасная часть любого вывода — то, что считалось «и так понятно». Стандарт стратегической аналитики — <strong>Key Assumptions Check</strong>: в конце каждого аналитического блока выписать неявные допущения и пометить, какие из них критичны для вывода.</p>
            </div>
            <div className="va-problem-card">
              <div className="va-problem-card-num">04 / 04</div>
              <h4>Нет иерархии вывода</h4>
              <p>«Поток мыслей» — это не структура. Pyramid Principle (Барбара Минто, McKinsey) ставит главный вывод сверху, обоснования — ниже, по убыванию значимости. Так устроены все слайд-доки больших консалтингов.</p>
            </div>
          </div>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section id="how" className="lp-section" style={{background: "var(--paper-2)"}}>
        <div className="lp-container">
          <div className="lp-section-head">
            <div className="lp-eyebrow">02 · Как это работает</div>
            <div>
              <h2 className="lp-section-title">Пять фаз. <em style={{fontFamily: "var(--serif)", fontStyle: "italic", fontWeight: 400, color: "var(--accent-ink)"}}>Каждая — отдельный аналитический акт.</em></h2>
              <p className="lp-section-sub">
                Это не «отправил вопрос — получил ответ». Это пять интеллектуальных операций подряд: MECE-декомпозиция → пять параллельных исследований → критика по ACH → проверка допущений (KAC) → синтез по Pyramid Principle. Никакого чёрного ящика — вы видите, что происходит на каждом слое.
              </p>
            </div>
          </div>

          <div className="va-phases">
            <div className="va-phase">
              <div className="va-phase-num">01 · Вопрос</div>
              <h4>Постановка задачи</h4>
              <p>Описываете задачу как старшему аналитику. Контекст, гипотезы, прикрепляете файлы.</p>
              <ul className="va-phase-list">
                <li>~ 2 минуты</li>
                <li>Любые форматы: PDF, DOCX, XLSX</li>
              </ul>
            </div>
            <div className="va-phase">
              <div className="va-phase-num">02 · Декомпозиция</div>
              <h4>MECE-разбор вопроса</h4>
              <p>Раскладываем формулировку на 10–14 подвопросов по принципу MECE (McKinsey): не пересекаются, в сумме покрывают всё пространство задачи.</p>
              <ul className="va-phase-list">
                <li>10–14 подвопросов</li>
                <li>Покрытие проверено · MECE</li>
              </ul>
            </div>
            <div className="va-phase">
              <div className="va-phase-num">03 · ACH</div>
              <h4>Конкурирующие гипотезы</h4>
              <p>Запускаем 5 DR параллельно. По методу ACH (Analysis of Competing Hypotheses) сопоставляем выводы агентов в единой матрице доказательств — не выбираем «лучший», а показываем все версии.</p>
              <ul className="va-phase-list">
                <li>5 параллельных агентов</li>
                <li>Матрица гипотез × доказательств</li>
              </ul>
            </div>
            <div className="va-phase">
              <div className="va-phase-num">04 · KAC</div>
              <h4>Проверка допущений</h4>
              <p>Key Assumptions Check: выписываем неявные допущения каждого вывода, помечаем критичные. По противоречиям и слабым допущениям запускаем точечные дозапросы.</p>
              <ul className="va-phase-list">
                <li>До 30 узконаправленных проб</li>
                <li>Реестр критичных допущений</li>
              </ul>
            </div>
            <div className="va-phase">
              <div className="va-phase-num">05 · Pyramid</div>
              <h4>Синтез по Минто</h4>
              <p>Финальный отчёт собран по Pyramid Principle: главный вывод сверху, обоснования ниже по убыванию веса. Каждое утверждение помечено уровнем доказательности. Готовая презентация в PPTX — в один клик.</p>
              <ul className="va-phase-list">
                <li>Single-pager + полный отчёт</li>
                <li>4 уровня доказательности у каждого тезиса</li>
                <li>PPTX · PDF · DOCX · Notion · Google Docs</li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* COMPARE */}
      <section id="compare" className="lp-section">
        <div className="lp-container">
          <div className="lp-section-head">
            <div className="lp-eyebrow">03 · Сравнение</div>
            <div>
              <h2 className="lp-section-title">Поиск vs <em style={{fontFamily: "var(--serif)", fontStyle: "italic", fontWeight: 400, color: "var(--accent-ink)"}}>метод</em>.</h2>
              <p className="lp-section-sub">
                AI-чат и сборка вручную дают вам найденные данные. Smart Report даёт аналитику — позицию, прошедшую через четыре протокола: декомпозицию, конкурирующие гипотезы, проверку допущений и иерархический синтез. Сравните по методу, а не по цене.
              </p>
            </div>
          </div>

          <div className="va-compare">
            <div className="va-compare-row va-compare-head">
              <div>Параметр</div>
              <div>Один AI-чат</div>
              <div>Своя сборка вручную</div>
              <div className="va-compare-us">Smart Report</div>
            </div>
            <div className="va-compare-row">
              <div>Стоимость одного отчёта</div>
              <div className="va-cell-bad">$20/мес + время</div>
              <div className="va-cell-bad">$80–120/мес + 4–6 часов</div>
              <div className="va-compare-us va-cell-ok">₽10 000 разово</div>
            </div>
            <div className="va-compare-row">
              <div>Параллельные DR</div>
              <div className="va-cell-bad">1</div>
              <div className="va-cell-bad">4 — но руками</div>
              <div className="va-compare-us va-cell-ok">5 — автоматически</div>
            </div>
            <div className="va-compare-row">
              <div>Аналитический метод</div>
              <div className="va-cell-bad">Нет</div>
              <div className="va-cell-bad">Зависит от вас</div>
              <div className="va-compare-us va-cell-ok">ACH · KAC · MECE · Pyramid</div>
            </div>
            <div className="va-compare-row">
              <div>Уровни доказательности</div>
              <div className="va-cell-bad">Всё одной интонацией</div>
              <div className="va-cell-bad">Ваша оценка</div>
              <div className="va-compare-us va-cell-ok">4 уровня у каждого тезиса</div>
            </div>
            <div className="va-compare-row">
              <div>Выявление противоречий</div>
              <div className="va-cell-bad">Нет</div>
              <div className="va-cell-bad">Только если заметили</div>
              <div className="va-compare-us va-cell-ok">Матрица ACH · с цитатами</div>
            </div>
            <div className="va-compare-row">
              <div>Финальный документ</div>
              <div className="va-cell-bad">Сырой текст</div>
              <div className="va-cell-bad">Ваша работа</div>
              <div className="va-compare-us va-cell-ok">Отчёт + готовая презентация</div>
            </div>
            <div className="va-compare-row">
              <div>Верификация фактов</div>
              <div className="va-cell-bad">Галлюцинации возможны</div>
              <div className="va-cell-bad">Проверяете руками</div>
              <div className="va-compare-us va-cell-ok">Cross-check 5 моделей + добор</div>
            </div>
            <div className="va-compare-row">
              <div>Источники и цитирование</div>
              <div className="va-cell-bad">Частично</div>
              <div className="va-cell-bad">Перемешаны между сервисами</div>
              <div className="va-compare-us va-cell-ok">Унифицированный список, 200+</div>
            </div>
            <div className="va-compare-row">
              <div>Российские способы оплаты</div>
              <div className="va-cell-bad">Нужен зарубежный счёт</div>
              <div className="va-cell-bad">Везде — зарубежные счета</div>
              <div className="va-compare-us va-cell-ok">Карта РФ, СБП, USDT</div>
            </div>
            <div className="va-compare-row">
              <div>Время до результата</div>
              <div className="va-cell-bad">~ 1 час + сборка</div>
              <div className="va-cell-bad">4–6 часов</div>
              <div className="va-compare-us va-cell-ok">12 минут</div>
            </div>
          </div>
        </div>
      </section>

      {/* PRICING */}
      <section id="price" className="lp-section" style={{background: "var(--paper-2)"}}>
        <div className="lp-container">
          <div className="lp-section-head">
            <div className="lp-eyebrow">04 · Цены</div>
            <div>
              <h2 className="lp-section-title">Простой прайс. <br/>Никаких скрытых платежей.</h2>
              <p className="lp-section-sub">
                Платите за результат — за отчёт. Нет подписки, нет токенов, нет лимитов на длину документа.
              </p>
            </div>
          </div>

          <div className="va-pricing-grid">
            <div className="va-price-card">
              <div className="va-price-tag">01 · Trial</div>
              <h3 className="va-price-name">Single</h3>
              <p className="va-price-desc">Один отчёт. Самый честный способ попробовать.</p>
              <div className="va-price-num">₽<em>10 000</em></div>
              <div className="va-price-num-meta">за отчёт · разово</div>
              <ul className="va-price-list">
                <li>5 параллельных Deep Research</li>
                <li>Фаза критики и добора</li>
                <li>Калибровка уверенности у каждого тезиса</li>
                <li>Отчёт + презентация · все основные форматы</li>
              </ul>
              <button className="lp-btn lp-btn-ghost" onClick={goSignup}>Заказать отчёт</button>
            </div>

            <div className="va-price-card va-featured">
              <div className="va-price-tag">02 · Популярный · −22%</div>
              <h3 className="va-price-name">Pack 5</h3>
              <p className="va-price-desc">Пять отчётов в течение года. Для команд, которые исследуют регулярно.</p>
              <div className="va-price-num">₽<em>39 000</em></div>
              <div className="va-price-num-meta">пакет · ₽7 800 за отчёт <span style={{textDecoration: "line-through", color: "var(--ink-4)", marginLeft: 6}}>₽10 000</span></div>
              <ul className="va-price-list">
                <li>Скидка ₽11 000 против пятёрки Single</li>
                <li>Приоритетная очередь (старт за 1 минуту)</li>
                <li>Командный аккаунт до 5 человек</li>
                <li>Архив отчётов с полнотекстовым поиском</li>
                <li>Менеджер на связи в Telegram</li>
              </ul>
              <button className="lp-btn" onClick={goSignup}>Купить пакет</button>
            </div>

            <div className="va-price-card">
              <div className="va-price-tag">03 · Pro</div>
              <h3 className="va-price-name">Subscription</h3>
              <p className="va-price-desc">Безлимитная оркестрация на ваших ключах. Платите только за нашу работу.</p>
              <div className="va-price-num">₽<em>2 500</em></div>
              <div className="va-price-num-meta">в месяц · BYOK</div>
              <ul className="va-price-list">
                <li>Безлимитные отчёты</li>
                <li>Свои ключи к любым моделям</li>
                <li>API и веб-хуки</li>
                <li>Командные роли и SSO</li>
              </ul>
              <button className="lp-btn lp-btn-ghost" onClick={goSignup}>Подключить</button>
            </div>
          </div>
        </div>
      </section>

      {/* WHO IT'S FOR — proof in numbers, not fake quotes */}
      <section className="lp-section-tight">
        <div className="lp-container">
          <div className="lp-eyebrow" style={{marginBottom: 32}}>Для кого мы это делаем</div>
          <div className="va-quotes">
            <div className="va-quote">
              <div className="va-quote-mark" style={{fontFamily: "var(--mono)", fontStyle: "normal"}}>01</div>
              <p>Стратегические консультанты и in-house аналитики. Готовите слайд-документ через 6 часов — экономите 4 на background research, цитаты не нужно перепроверять.</p>
              <div className="va-quote-by">
                <strong>Консалтинг и аналитика</strong>
                от бутиков до in-house team
              </div>
            </div>
            <div className="va-quote">
              <div className="va-quote-mark" style={{fontFamily: "var(--mono)", fontStyle: "normal"}}>02</div>
              <p>VC, PE и corp-dev. Тезис проверяется быстрее. Противоречия в данных — отдельный сигнал на due diligence, а не «странность одного источника».</p>
              <div className="va-quote-by">
                <strong>Инвестиционные команды</strong>
                от тезиса до DD-меморандума
              </div>
            </div>
            <div className="va-quote">
              <div className="va-quote-mark" style={{fontFamily: "var(--mono)", fontStyle: "normal"}}>03</div>
              <p>Продакт-менеджеры, маркетологи, основатели. Конкурентный анализ, оценка ниш, customer research — без сборки данных по полу-десятку источников вручную.</p>
              <div className="va-quote-by">
                <strong>Продуктовые команды</strong>
                research при принятии решений
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="lp-section">
        <div className="lp-container">
          <div className="lp-section-head">
            <div className="lp-eyebrow">05 · FAQ</div>
            <div>
              <h2 className="lp-section-title">Что обычно спрашивают.</h2>
            </div>
          </div>

          <div className="va-faq">
            {[
              ["01", "Чем это отличается от ChatGPT с веб-поиском?",
               "ChatGPT с поиском — это retrieval + пересказ. Smart Report — это retrieval + четыре аналитических протокола: MECE-декомпозиция вопроса, ACH-сравнение конкурирующих гипотез, Key Assumptions Check, синтез по Pyramid Principle. Это разница между «нашёл и пересказал» и «проанализировал и обосновал»."],
              ["02", "Что такое уровни доказательности?",
               "Каждое утверждение в отчёте помечено одним из четырёх уровней: «точно» (≥2 авторитетных источника совпадают), «скорее всего» (один сильный источник или согласие нескольких слабых), «есть мнение» (встречается в источниках, но не подтверждено), «только догадка» (экстраполяция, помечена явно). Большинство AI-инструментов подают всё одной интонацией уверенности — мы нет."],
              ["03", "А если данных по теме нет?",
               "Получаете отчёт с явным флагом «недостаточно источников» по тем подвопросам, где не нашлось двух авторитетных источников. Не выдумываем. Честное «нет данных» — отдельное УТП."],
              ["04", "Что такое презентация на выходе?",
               "Готовый PPTX — со структурой отчёта, ключевыми тезисами, графиками и цитатами. Открывается в PowerPoint, Keynote, Google Slides. Каждый слайд — со ссылкой на источник."],
              ["05", "Можно ли использовать свои ключи?",
               "Да — на тарифе Subscription. Если у вас уже есть свои подписки на DR-сервисы, мы используем их и берём ₽2 500 в месяц только за оркестрацию. В разы дешевле, чем покупать каждый отчёт."],
              ["06", "Какие способы оплаты?",
               "Российские карты, СБП, ЮKassa, Тинькофф, USDT. Без зарубежных счетов и подписок."],
              ["07", "Подходит ли для конфиденциальных задач?",
               "Документы шифруются на загрузке, обрабатываются в изолированном workspace и удаляются через 30 дней. Логи DR не передаются третьим сторонам. Для крупных команд — on-prem."],
            ].map(([n, q, a]) => (
              <div key={n} className="va-faq-item">
                <div className="va-faq-num">{n}</div>
                <div>
                  <h4>{q}</h4>
                  <p>{a}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* FINAL CTA */}
      <section className="va-final">
        <div className="lp-container">
          <h2>Закажите <em>метод</em>, не текст.</h2>
          <p>Опишите задачу. Через 12–20 минут получите документ, прошедший через MECE-декомпозицию, ACH, Key Assumptions Check и Pyramid Principle. Каждое утверждение помечено уровнем доказательности. ₽10 000 разово, без подписки.</p>
          <div className="va-cta-row">
            <button className="lp-btn" onClick={goSignup}>Заказать отчёт <span className="lp-btn-arrow">→</span></button>
            <button className="lp-btn lp-btn-ghost" onClick={() => _scrollToId("how")}>Посмотреть структуру отчёта</button>
          </div>
        </div>
      </section>

      <window.Footer />
    </>
  );
}

window.LandingA = LandingA;

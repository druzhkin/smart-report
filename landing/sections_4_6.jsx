// Smart Report v.IV — ReportArtifact (final report in right panel with sticky TOC)

const { useState, useEffect, useRef } = React;

function ReportArtifact({ report, openSource }) {
  const [active, setActive] = useState(report.toc[0].id);
  const scrollRef = useRef(null);

  useEffect(() => {
    const root = scrollRef.current;
    if (!root) return;
    const obs = new IntersectionObserver((entries) => {
      entries.forEach(e => { if (e.isIntersecting) setActive(e.target.id.replace("r-", "")); });
    }, { root, rootMargin: "-10% 0% -70% 0%", threshold: 0 });
    report.toc.forEach(t => {
      const el = root.querySelector("#r-" + t.id);
      if (el) obs.observe(el);
    });
    return () => obs.disconnect();
  }, [report.toc]);

  const scrollTo = (id) => {
    const el = scrollRef.current?.querySelector("#r-" + id);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="report-wrap">
      <aside className="report-toc">
        <div className="title">Содержание</div>
        {report.toc.map(t => (
          <button
            key={t.id}
            className={"toc-item depth-" + t.depth + (active === t.id ? " active" : "")}
            onClick={() => scrollTo(t.id)}
          >
            {t.label}
          </button>
        ))}
        <div className="title" style={{ marginTop: 18 }}>Контекст</div>
        <div style={{ fontSize: 11, color: "var(--ink-2)", padding: "4px 6px 4px 10px", fontFamily: "var(--mono)", lineHeight: 1.8, letterSpacing: "0.02em" }}>
          00:47:12<br/>
          14 вызовов Opus<br/>
          5 + 1 внешних отчётов<br/>
          уверенность 0.81
        </div>
      </aside>

      <div className="report-scroll" ref={scrollRef}>
        <div className="report-inner">
          <section id="r-exec" className="cover">
            <div className="eyebrow">Отчёт уровня акционера · апрель 2026</div>
            <h1>{report.title}</h1>
            <p style={{ color: "var(--ink-2)", fontSize: 15 }}>
              Ответ на вопрос о спросе, экономике и международных практиках аменитис в бизнес-
              и премиум-новостройках Москвы. 7 из 8 подвопросов закрыты с уверенностью A/B.
            </p>
            <dl className="cover-meta">
              <div><dt>Подвопросы</dt><dd>7 / 8</dd></div>
              <div><dt>Источников</dt><dd>74</dd></div>
              <div><dt>Уверенность</dt><dd>0.81</dd></div>
              <div><dt>Стоимость</dt><dd>₽ 847</dd></div>
            </dl>
          </section>

          <section id="r-qa">
            <h2>Прямые ответы</h2>
            <p>Семь из восьми подвопросов закрыты с уверенностью A или B. Один (поведенческий разрез IT vs традиционный бизнес) — на уровне C с явным ограничением.</p>
            <div style={{ display: "grid", gap: 0, marginTop: 10 }}>
              {[
                ["Что реально используется?", "Фитнес, двор, консьерж, детские.", "A"],
                ["Эластичность цены?", "3–5% (детские) → 12–18% (архитектор).", "A"],
                ["Когда не окупается?", "При потере GLA > 1.2% от пятна.", "B"],
                ["Мёртвые аменитис?", "Сигарная, виски-рум, кинозал.", "A"],
                ["Что приживается из мира?", "Hotel-lobby, консьерж. Не приживается: pool-deck.", "B"],
                ["Оптимум для маржи?", "См. insight 4 ниже.", "A"]
              ].map(([q, a, c], i) => (
                <div key={i} style={{ display: "grid", gridTemplateColumns: "auto 1fr 1fr auto", gap: 14, padding: "12px 0", borderBottom: "1px solid var(--rule)", alignItems: "baseline" }}>
                  <span className="claim-n">Q{i + 1}</span>
                  <div style={{ fontSize: 13, fontWeight: 500 }}>{q}</div>
                  <div style={{ fontSize: 13, color: "var(--ink-2)" }}>{a}</div>
                  <span className={"confidence " + c.toLowerCase()}>{c}</span>
                </div>
              ))}
            </div>
          </section>

          <section id="r-headline">
            <h2>Ключевые цифры</h2>
            <div className="headline-grid">
              {report.headline.map((h, i) => (
                <div key={i} className="headline-cell">
                  <div className="headline-big">{h.big}</div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 8 }}>
                    <div className="headline-lbl">{h.label}</div>
                    <Cite n={h.n} openSource={openSource} />
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section id="r-ranking">
            <h2>Ранжирование факторов</h2>
            <p>Вес — композитный индекс влияния на прайс и скорость продаж.</p>
            <div style={{ marginTop: 10 }}>
              {report.ranking.map((r, i) => (
                <div key={i} className="ranking-row">
                  <div>
                    <div className="name">{r.factor}</div>
                    <div className="band">{r.band}</div>
                  </div>
                  <div className="ranking-bar">
                    <div className={"ranking-bar-fill" + (i < 4 ? " accent" : "")} style={{ width: (r.weight * 100) + "%" }}></div>
                  </div>
                  <div className="ranking-weight">{r.weight.toFixed(2)}</div>
                </div>
              ))}
            </div>
          </section>

          <section id="r-narrative">
            <h2>Основной нарратив</h2>
            {report.narrative.map((n, i) => (
              <div key={i} id={"r-" + n.id}>
                <h3>{i + 1}. {n.heading}</h3>
                {n.paras.map((p, j) => <p key={j}>{renderWithCites(p, openSource)}</p>)}
              </div>
            ))}
          </section>

          <section id="r-tables">
            <h2>Сводные таблицы</h2>
            <h3>Окупаемость по аменитис</h3>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Амения</th>
                  <th>CAPEX, млн ₽</th>
                  <th>Потеря GLA</th>
                  <th>Прайс, %</th>
                  <th>Окупаемость</th>
                  <th>Исп.</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ["Фитнес 400 м²", "18–24", "400 м²", "3.8–5.2", "4.1 года", "84%"],
                  ["Бассейн 25 м", "42–58", "350 м²", "4.0–7.0", "11–14 лет", "15%"],
                  ["Детские (3 зоны)", "8–14", "180 м²", "3.0–5.0", "2.3 года", "92%"],
                  ["Коворкинг 150 м²", "6–10", "150 м²", "2.1–3.4", "3.7 года", "62%"],
                  ["Wellness компакт.", "14–22", "180 м²", "2.8–4.1", "6.2 года", "28%"],
                  ["Сигарная", "18–28", "90 м²", "0.4–0.9", "> 20 лет", "6%"]
                ].map((row, i) => (
                  <tr key={i}>{row.map((v, j) => <td key={j} className={j > 0 ? "num" : ""}>{v}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </section>

          <section id="r-charts">
            <h2>Графики</h2>
            <p style={{ color: "var(--ink-3)", fontSize: 13 }}>В полной версии — 3 сравнительных графика: стоимость по сегментам, декларация vs использование, международная плотность аменитис. В этом прототипе — placeholder.</p>
            <div style={{ height: 180, background: "var(--paper-2)", border: "1px solid var(--rule)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--ink-3)", fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>
              [ placeholder · 3 chart slots ]
            </div>
          </section>

          <section id="r-insights">
            <h2>Ключевые insight'ы</h2>
            <ol className="insights-list">
              {report.insights.map((ins, i) => <li key={i}>{ins}</li>)}
            </ol>
          </section>

          <section id="r-biblio">
            <h2>Источники</h2>
            <p>Показаны 13 из 74 источников. Нумерация сквозная.</p>
            <div style={{ marginTop: 10 }}>
              {report.bibliography.map(b => (
                <div key={b.n} className="biblio-row">
                  <span className="biblio-n">[{b.n}]</span>
                  <div style={{ fontWeight: 500, fontSize: 12 }}>{b.title}</div>
                  <span className="biblio-meta">{b.date}</span>
                  <span className="biblio-meta">{b.type}</span>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { ReportArtifact });

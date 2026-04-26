// Smart Report v.IV — Prompt, Upload, Critique artifacts (render in right panel)

const { useState, useEffect, useRef, useMemo } = React;

// ========== PromptArtifact (full, prose — for right panel) ==========
function PromptArtifact({ mock, openSource }) {
  const { promptSections, promptMeta } = mock;
  const [copied, setCopied] = useState(false);

  const flatText = useMemo(() => {
    return promptSections.map(s => {
      const body = s.body ? s.body : (s.bullets ? s.bullets.map(b => "— " + b).join("\n") : "");
      return `## ${s.title}\n\n${body}`;
    }).join("\n\n");
  }, [promptSections]);

  const copy = () => {
    try { navigator.clipboard.writeText(flatText); } catch(e) {}
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  return (
    <div className="prompt-doc">
      <h1>Research-промт</h1>
      <div className="prompt-subhead">
        <span>{promptMeta.words.toLocaleString("ru-RU")} слов</span>
        <span>·</span>
        <span>6 разделов</span>
        <span>·</span>
        <span>рекомендован Claude Research</span>
      </div>

      <div className="prompt-rec-block">
        <div className="rec-label">Куда запустить</div>
        <div className="prompt-rec-tools">
          <span className="rec-tool top">
            <span className="star">★</span>
            Claude Research
            <span className="score">92</span>
          </span>
          <span className="rec-tool">Perplexity DR <span className="score">78</span></span>
          <span className="rec-tool">OpenAI DR <span className="score">74</span></span>
        </div>
        <div className="rec-reasoning">{promptMeta.reasoning}</div>
      </div>

      {promptSections.map(s => (
        <div key={s.id} id={"prompt-" + s.id} className="prompt-section">
          <h2>{s.title}</h2>
          {s.body && <p>{s.body}</p>}
          {s.bullets && (
            <ul>{s.bullets.map((b, i) => <li key={i}>{b}</li>)}</ul>
          )}
        </div>
      ))}
    </div>
  );
}

// ========== UploadArtifact ==========
function UploadArtifact({ files, totalWords }) {
  return (
    <div className="upload-doc">
      <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: "-0.015em", margin: "0 0 6px 0" }}>
        Загружено {files.length} внешних отчёта
      </h1>
      <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-3)", letterSpacing: "0.04em", marginBottom: 16 }}>
        {totalWords.toLocaleString("ru-RU")} слов · извлечено 312 утверждений · 94 числовые метрики
      </div>

      <div className="upload-dropzone">
        <div className="big">Перетащите файлы или нажмите, чтобы добавить</div>
        <div className="small">.md, .txt, .pdf · до 2 МБ · до 10 файлов</div>
      </div>

      <div style={{ fontFamily: "var(--mono)", fontSize: 10, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--ink-3)", marginTop: 18, marginBottom: 8 }}>
        Принятые файлы
      </div>
      <div className="upload-grid">
        {files.map((f, i) => (
          <div key={i} className="upload-card">
            <div className="fn">{f.name}</div>
            <div className="meta">
              <span>{f.size} · {f.words.toLocaleString("ru-RU")} сл.</span>
              <span className="check">✓ принят</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ========== CritiqueArtifact ==========
function CritiqueArtifact({ critique, openSource }) {
  const [tab, setTab] = useState("contradictions");

  return (
    <div className="crit-doc">
      <div className="crit-summary">
        <h2>Критика и сверка</h2>
        <div className="lead">
          По 5 отчётам найдено {critique.agreements.length} согласий, {critique.contradictions.length} противоречий,{" "}
          {critique.gaps.length} пробелов и {critique.unverified.length} неподтверждённые цифры.
          Противоречия — главное: ниже — резолюция по каждому.
        </div>
      </div>

      <div className="crit-tabs-row">
        {[
          ["contradictions", "Противоречия", critique.contradictions.length],
          ["agreements", "Согласия", critique.agreements.length],
          ["gaps", "Пробелы", critique.gaps.length],
          ["unverified", "Неподтв. цифры", critique.unverified.length]
        ].map(([key, label, n]) => (
          <button key={key} className={"crit-tab-btn" + (tab === key ? " active" : "")} onClick={() => setTab(key)}>
            {label} <span className="n">{n}</span>
          </button>
        ))}
      </div>

      <div className="crit-content">
        {tab === "contradictions" && critique.contradictions.map(c => (
          <div key={c.id} className="duel">
            <div className="duel-topic">
              <span className="duel-id">{c.id}</span>
              <span>{c.topic}</span>
            </div>
            <div className="duel-stack">
              <div className="duel-side">
                <div className="duel-side-name">{c.a.src}</div>
                {c.a.body}
              </div>
              <div className="duel-side">
                <div className="duel-side-name">{c.b.src}</div>
                {c.b.body}
              </div>
            </div>
            <div className="duel-res">
              <div className="duel-res-label">Резолюция</div>
              {c.resolution}
            </div>
          </div>
        ))}

        {tab === "agreements" && critique.agreements.map((a, i) => (
          <div key={i} className="claim-row">
            <span className="claim-n">A{String(i + 1).padStart(2, "0")}</span>
            <div>
              {a.claim}
              <span style={{ color: "var(--ink-3)", fontFamily: "var(--mono)", fontSize: 10, marginLeft: 8 }}>
                · {a.sources} источн.
              </span>
            </div>
            <span className={"confidence " + a.confidence.toLowerCase()}>{a.confidence}</span>
          </div>
        ))}

        {tab === "gaps" && critique.gaps.map((g, i) => (
          <div key={i} className="claim-row">
            <span className="claim-n">G{String(i + 1).padStart(2, "0")}</span>
            <div>{g}</div>
            <span></span>
          </div>
        ))}

        {tab === "unverified" && critique.unverified.map((u, i) => (
          <div key={i} className="claim-row">
            <span className="claim-n" style={{ color: "var(--bad)", fontWeight: 600, fontSize: 11 }}>{u.n}</span>
            <div>
              {u.claim}
              <div style={{ fontSize: 11, color: "var(--ink-3)", fontFamily: "var(--mono)", marginTop: 2 }}>
                {u.source}
              </div>
            </div>
            <span className="confidence c">C</span>
          </div>
        ))}
      </div>
    </div>
  );
}

Object.assign(window, { PromptArtifact, UploadArtifact, CritiqueArtifact });

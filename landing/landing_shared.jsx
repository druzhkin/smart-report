// Shared landing primitives
const { useState, useEffect } = React;

function VariantSwitcher({ value, onChange }) {
  const variants = [
    { id: "a", num: "A", label: "Sales" },
    { id: "b", num: "B", label: "Product" },
    { id: "c", num: "C", label: "Content" },
  ];
  return (
    <div className="variant-switcher" role="tablist">
      {variants.map(v => (
        <button
          key={v.id}
          className={value === v.id ? "active" : ""}
          onClick={() => onChange(v.id)}
          role="tab"
        >
          <span className="vs-num">{v.num}</span>
          <span>{v.label}</span>
        </button>
      ))}
    </div>
  );
}

function Topbar({ ctaLabel = "Заказать отчёт", variant = "a", onCtaClick }) {
  // Smooth-scroll for in-page anchors. Falls back to native jump if the
  // section id isn't on the current page.
  const navJump = (e, id) => {
    const el = document.getElementById(id);
    if (el) { e.preventDefault(); el.scrollIntoView({ behavior: "smooth", block: "start" }); }
  };

  // Default CTA: open the global lead modal (LandingA exposes window.__openLeadModal).
  const handleCta = () => {
    if (typeof onCtaClick === "function") return onCtaClick();
    if (typeof window.__openLeadModal === "function") return window.__openLeadModal("start");
  };

  return (
    <header className="lp-topbar">
      <div className="lp-brand">
        <div className="lp-brand-mark">SR</div>
        <div>
          <div className="lp-brand-name">Smart Report</div>
          <div className="lp-brand-meta">v.IV · research orchestrator</div>
        </div>
      </div>
      <nav className="lp-nav">
        <a href="#how" onClick={(e) => navJump(e, "how")}>Как это работает</a>
        <a href="#how" onClick={(e) => navJump(e, "how")}>Пример отчёта</a>
        <a href="#compare" onClick={(e) => navJump(e, "compare")}>Сравнение</a>
        <a href="#price" onClick={(e) => navJump(e, "price")}>Цены</a>
        <a href="#faq" onClick={(e) => navJump(e, "faq")}>FAQ</a>
      </nav>
      <button className="lp-cta-mini" onClick={handleCta}>{ctaLabel} →</button>
    </header>
  );
}

function Footer() {
  return (
    <footer className="lp-foot">
      <div className="lp-container">
        <div className="lp-foot-grid">
          <div>
            <div className="lp-brand">
              <div className="lp-brand-mark">SR</div>
              <div className="lp-brand-name">Smart Report</div>
            </div>
            <p className="lp-foot-tagline">
              Оркестратор глубоких исследований. Один вопрос — пять параллельных DR — отчёт уровня старшего аналитика.
            </p>
          </div>
          <div className="lp-foot-col">
            <h5>Продукт</h5>
            <ul>
              <li>Как это работает</li>
              <li>Пример отчёта</li>
              <li>Цены</li>
              <li>Безопасность</li>
            </ul>
          </div>
          <div className="lp-foot-col">
            <h5>Применение</h5>
            <ul>
              <li>Консалтинг</li>
              <li>M&A / стратегия</li>
              <li>Венчур и PE</li>
              <li>Продакт и маркетинг</li>
            </ul>
          </div>
          <div className="lp-foot-col">
            <h5>Контакты</h5>
            <ul>
              <li>hello@smartreport.io</li>
              <li>Telegram</li>
              <li>Документация</li>
              <li>Условия</li>
            </ul>
          </div>
        </div>
        <div className="lp-foot-bottom">
          <span>© 2026 Smart Report · Москва</span>
          <span>v.IV · 04 / 2026</span>
        </div>
      </div>
    </footer>
  );
}

Object.assign(window, { VariantSwitcher, Topbar, Footer });

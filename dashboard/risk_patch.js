(() => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const load = async (u) => { try { const r = await fetch(u, { cache: "no-store" }); return r.ok ? await r.json() : null; } catch { return null; } };
  const esc = (v) => String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");

  function badge(level) {
    const value = String(level || "보통");
    const cls = value.includes("높") ? "risk-high" : value.includes("낮") ? "risk-low" : "risk-mid";
    return `<span class="risk-badge ${cls}">${esc(value)}</span>`;
  }

  function renderRiskCard(item) {
    const factors = Array.isArray(item.risk_factors) ? item.risk_factors.slice(0, 3) : [];
    return `<article class="risk-card">
      <div class="risk-head"><div><span class="candidate-code">${esc(item.code)}</span><strong>${esc(item.name)}</strong><small>${esc(item.session || "")}</small></div>${badge(item.risk_level)}</div>
      <p>${esc(item.summary || "리스크 요약 대기")}</p>
      <ul>${factors.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
      <small class="risk-watch">확인: ${esc(item.watch || "공시, 거래량, 지수 흐름")}</small>
    </article>`;
  }

  async function renderRisks() {
    const section = document.querySelector(".prism-results");
    if (!section || document.getElementById("riskPanel")) return;
    const data = await load("./recommendation_risks.json");
    const panel = document.createElement("section");
    panel.id = "riskPanel";
    panel.className = "risk-panel";
    if (!data || data.ok === false) {
      panel.innerHTML = `<div class="panel-head"><h2>추천주 리스크 요약</h2><span>${esc(data?.updated_at || "대기")}</span></div><div class="empty-state">${esc(data?.detail || "아직 OpenAI 리스크 요약이 없습니다.")}</div>`;
    } else {
      panel.innerHTML = `<div class="panel-head"><h2>추천주 리스크 요약</h2><span>OpenAI + 웹검색 · ${esc(data.updated_at || "")}</span></div><div class="risk-grid">${(data.risks || []).map(renderRiskCard).join("")}</div>`;
      if (Array.isArray(data.sources) && data.sources.length) {
        const sources = document.createElement("div");
        sources.className = "risk-sources";
        sources.innerHTML = `<strong>참고 출처</strong>${data.sources.slice(0, 6).map((s) => `<a href="${esc(s.url)}" target="_blank" rel="noreferrer">${esc(s.title || s.url)}</a>`).join("")}`;
        panel.appendChild(sources);
      }
    }
    section.insertAdjacentElement("afterend", panel);
  }

  function style() {
    if (document.getElementById("risk-style")) return;
    const s = document.createElement("style");
    s.id = "risk-style";
    s.textContent = `.risk-panel{margin-top:16px;padding:18px;background:#fff;border:1px solid var(--line);border-radius:8px;box-shadow:var(--shadow)}.risk-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}.risk-card{border:1px solid var(--line);border-radius:8px;background:var(--surface-3);padding:14px;display:grid;gap:10px}.risk-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.risk-head strong{display:block;margin-top:4px}.risk-card p{margin:0;line-height:1.5;color:var(--text);font-size:14px}.risk-card ul{margin:0;padding-left:18px;color:var(--muted);font-size:13px;line-height:1.5}.risk-watch{color:var(--muted)}.risk-badge{display:inline-flex;align-items:center;height:26px;padding:0 9px;border-radius:999px;font-size:12px;font-weight:800;white-space:nowrap}.risk-high{background:#f7e7e4;color:#9a362b}.risk-mid{background:#fff2d7;color:#8a5a0a}.risk-low{background:#e5f2ed;color:#287c61}.risk-sources{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px;padding-top:12px;border-top:1px solid var(--line);font-size:12px}.risk-sources strong{margin-right:6px}.risk-sources a{color:var(--blue);text-decoration:none}`;
    document.head.appendChild(s);
  }

  async function run() { await sleep(900); style(); await renderRisks(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run); else run();
})();

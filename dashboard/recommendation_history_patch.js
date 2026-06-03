(() => {
  const load = async (u) => { try { const r = await fetch(u, { cache: "no-store" }); return r.ok ? await r.json() : null; } catch { return null; } };
  const esc = (v) => String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  const num = (v, d = 2) => Number.isFinite(Number(v)) ? Number(v).toFixed(d) : "-";
  const price = (v) => Number.isFinite(Number(v)) && Number(v) > 0 ? Math.round(Number(v)).toLocaleString("ko-KR") : "-";

  function rows(item) {
    const sections = item?.sections || {};
    return Object.entries(sections).flatMap(([section, values]) => Array.isArray(values) ? values.map((x) => ({ ...x, section })) : []);
  }

  function card(x) {
    const rawScore = Number(x.ai_win_score);
    const percentile = num(x.ai_win_score_100 ?? x.adaptive_profit_score ?? x.profit_score, 1);
    const score = Number.isFinite(rawScore) ? rawScore.toFixed(2) : percentile;
    const scoreLabel = Number.isFinite(rawScore) ? `백분위 ${percentile}` : "백분위";
    const previousClose = price(x.previous_close_price ?? x.signal_price ?? x.current_price);
    const stop = `${num(x.stop_loss_pct, 2)}% / ${price(x.stop_loss_price)}`;
    const target = `${num(x.target_return_pct ?? x.take_profit_trigger_pct, 2)}% / ${price(x.target_price)}`;
    return `<article class="candidate-card"><div class="candidate-main"><span class="candidate-code">${esc(x.code)}</span><strong>${esc(x.name)}</strong><small>${esc(x.entry_plan || x.buy_at || "시초가 진입")}</small></div><div class="candidate-score"><span>AI WIN 원점수</span><strong>${esc(score)}</strong><small>${esc(scoreLabel)}</small></div><dl class="candidate-facts"><div><dt>전일종가</dt><dd>${esc(previousClose)}</dd></div><div><dt>등락</dt><dd>${esc(num(x.change_rate,2))}%</dd></div><div><dt>손절</dt><dd>${esc(stop)}</dd></div><div><dt>목표</dt><dd>${esc(target)}</dd></div></dl></article>`;
  }

  async function render() {
    const root = document.getElementById("candidateList");
    const tabRoot = document.querySelector(".result-tabs");
    if (!root || !tabRoot) return;
    const history = await load("./recommendation_history.json");
    const items = (history?.items || []).slice(-10).reverse();
    if (!items.length) return;

    tabRoot.innerHTML = items.map((item, i) => `<button type="button" class="tab ${i === 0 ? "active" : ""}" data-history-index="${i}">${esc(item.date)}</button>`).join("");

    function show(index) {
      const item = items[index] || items[0];
      tabRoot.querySelectorAll("[data-history-index]").forEach((button) => button.classList.toggle("active", Number(button.dataset.historyIndex) === index));
      const meta = document.getElementById("prismResultMeta");
      if (meta) meta.textContent = `${item.metadata?.signal_at || item.date} 기준 · ${item.metadata?.buy_at || item.date + " 시초가"} 진입 · AI WIN 원점수는 날짜별 종목 고유 점수, 백분위는 해당일 후보군 내 순위`;
      const list = rows(item);
      root.innerHTML = list.length ? list.map(card).join("") : '<div class="empty-state">추천 후보 대기</div>';
    }

    tabRoot.querySelectorAll("[data-history-index]").forEach((button) => button.addEventListener("click", () => show(Number(button.dataset.historyIndex))));
    show(0);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", render); else render();
})();

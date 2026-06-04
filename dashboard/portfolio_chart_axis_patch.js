(() => {
  const parsePctLocal = (value) => {
    const number = Number(String(value ?? "0").replace("%", ""));
    return Number.isFinite(number) ? number / 100 : 0;
  };

  const formatPctLocal = (value) => `${(value * 100).toFixed(2)}%`;

  async function loadPortfolio() {
    try {
      const response = await fetch("./portfolio_status.json", { cache: "no-store" });
      return response.ok ? await response.json() : null;
    } catch (_error) {
      return null;
    }
  }

  function chartDates(curve, portfolio) {
    const first = curve[0]?.date || portfolio?.start_date || "";
    const last = curve[curve.length - 1]?.date || portfolio?.end_date || "";
    return { first, last };
  }

  window.drawPortfolioCanvas = function patchedDrawPortfolioCanvas(curve, portfolio = null) {
    const canvas = document.getElementById("portfolioCanvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    const left = 46;
    const right = canvas.width - 46;
    const top = 28;
    const bottom = canvas.height - 48;

    ctx.strokeStyle = "#d9e0dc";
    ctx.lineWidth = 1;
    for (let y = top + 12; y <= bottom; y += 42) {
      ctx.beginPath();
      ctx.moveTo(left, y);
      ctx.lineTo(right, y);
      ctx.stroke();
    }

    if (!curve || !curve.length) {
      ctx.fillStyle = "#62706c";
      ctx.font = "15px system-ui";
      ctx.fillText("포트폴리오 수익률 데이터 대기", left, 130);
      return;
    }

    const values = curve.map((row) => parsePctLocal(row.return_pct));
    const min = Math.min(...values, 0);
    const max = Math.max(...values, 0.01);
    const range = max - min || 0.01;

    ctx.strokeStyle = "#287c61";
    ctx.lineWidth = 3;
    ctx.beginPath();
    values.forEach((value, index) => {
      const x = left + ((right - left) * index) / Math.max(values.length - 1, 1);
      const y = bottom - ((value - min) / range) * (bottom - top);
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    const { first, last } = chartDates(curve, portfolio);
    ctx.fillStyle = "#17201d";
    ctx.font = "13px system-ui";
    ctx.textAlign = "left";
    ctx.fillText(`최저 ${formatPctLocal(min)} · 최고 ${formatPctLocal(max)}`, left, 18);
    ctx.fillText(first, left, canvas.height - 14);
    ctx.textAlign = "right";
    ctx.fillText(last, right, canvas.height - 14);
    ctx.textAlign = "center";
    ctx.fillStyle = "#62706c";
    ctx.fillText("시작", left, canvas.height - 30);
    ctx.fillText("최근", right, canvas.height - 30);
    ctx.textAlign = "left";
  };

  async function redraw() {
    const portfolio = await loadPortfolio();
    if (!portfolio) return;
    window.drawPortfolioCanvas(portfolio.equity_curve || [], portfolio);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", redraw);
  } else {
    redraw();
  }
  setTimeout(redraw, 500);
  setTimeout(redraw, 1500);
})();

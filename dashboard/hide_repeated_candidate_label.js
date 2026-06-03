(() => {
  const hiddenLabels = new Set([
    "AI WIN 전일종가 모멘텀 상위주",
    "AI WIN 일간 추천 후보",
  ]);

  function cleanCandidateLabels(root = document) {
    root.querySelectorAll(".candidate-main small").forEach((node) => {
      if (hiddenLabels.has(node.textContent.trim())) node.remove();
    });
  }

  cleanCandidateLabels();
  const observer = new MutationObserver(() => cleanCandidateLabels());
  observer.observe(document.documentElement, { childList: true, subtree: true });
  setInterval(cleanCandidateLabels, 1000);
})();

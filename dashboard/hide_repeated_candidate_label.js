(() => {
  const hiddenLabels = [
    "AI WIN 전일종가 모멘텀 상위주",
    "AI WIN 일간 추천 후보",
  ];

  function cleanCandidateLabels(root = document) {
    root.querySelectorAll(".candidate-main small, .candidate-card small, .candidate-card span, .candidate-card div").forEach((node) => {
      const text = node.textContent.trim();
      if (hiddenLabels.includes(text)) {
        node.remove();
        return;
      }
      for (const label of hiddenLabels) {
        if (node.childNodes.length === 1 && node.firstChild?.nodeType === Node.TEXT_NODE && text.includes(label)) {
          node.textContent = text.replaceAll(label, "").replace(/\s+·\s+$/g, "").trim();
        }
      }
    });
  }

  cleanCandidateLabels();
  const observer = new MutationObserver(() => cleanCandidateLabels());
  observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
  setInterval(cleanCandidateLabels, 500);
})();

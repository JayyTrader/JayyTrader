(function () {
  "use strict";
  const DATA_URL = "data/realized-cap-hodl-waves.json";
  async function refresh() {
    try {
      const response = await fetch(DATA_URL, { cache: "no-store" });
      if (!response.ok) throw new Error("HTTP " + response.status);
      const payload = await response.json();
      if (payload.status !== "available" || !Number.isFinite(payload.bandPercent) ||
          !Number.isFinite(payload.score) || payload.score < -2 || payload.score > 2 ||
          !payload.sourceDate || !payload.validation ||
          payload.validation.ageDays < 0 || payload.validation.ageDays > payload.validation.maxAllowedAgeDays) {
        throw new Error("HODL Waves payload failed validation");
      }
      window.__hodlPayload = payload;
    } catch (error) {
      window.__hodlPayload = null;
      console.warn("Realized Cap HODL Waves unavailable:", error.message);
    }
    window.dispatchEvent(new Event("hodl-data-updated"));
  }
  void refresh();
  window.setInterval(refresh, 15 * 60 * 1000);
})();

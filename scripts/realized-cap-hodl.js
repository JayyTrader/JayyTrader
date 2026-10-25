(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.RealizedCapHODL = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  // User-defined linear map: 10% => +2, 30% => 0, 50% => -2.
  // Clamp at the framework limits. The percentage is manually read from the public chart.
  function scoreFromPercent(percent) {
    if (!Number.isFinite(percent)) return 0;
    const boundedPercent = Math.max(0, Math.min(100, percent));
    return Math.max(-2, Math.min(2, 3 - boundedPercent / 10));
  }
  return { scoreFromPercent };
});

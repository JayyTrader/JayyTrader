(function () {
  const table = document.getElementById("source-table");
  const status = document.getElementById("source-data-status");

  function escapeHTML(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[char]);
  }

  function linksFor(item) {
    const sources = [
      [item.source, item.sourceName || "Observation source"],
      [item.referenceSource, "Indicator reference"],
      [item.sourceComparison && item.sourceComparison.source, "Published value check"],
      [item.attributionUrl, "Required attribution"]
    ];
    const seen = new Set();
    return sources.filter(([url]) => {
      if (typeof url !== "string" || !/^https:\/\//i.test(url) || seen.has(url)) return false;
      seen.add(url);
      return true;
    }).map(([url, label]) => `<a class="source-link" href="${escapeHTML(url)}" target="_blank" rel="noopener noreferrer">${escapeHTML(label)} ↗</a>`).join("") || '<span class="source-label">No source recorded</span>';
  }

  fetch(`data/sdca-latest.json?t=${Date.now()}`, { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then((data) => {
      if (!Array.isArray(data.indicators)) throw new TypeError("Indicator metadata is missing");
      table.innerHTML = data.indicators.map((item) => {
        const observed = item.sourceTimestamp || item.lastUpdated || "Unavailable";
        const itemStatus = item.status || "Unverified";
        return `<tr><th scope="row">${escapeHTML(item.name)}</th><td>${linksFor(item)}</td><td>${escapeHTML(observed)}</td><td>${escapeHTML(itemStatus)}</td></tr>`;
      }).join("");
      status.textContent = `${data.indicators.length} indicator records · attribution only`;
    })
    .catch((error) => {
      table.innerHTML = '<tr><td colspan="4">Source metadata unavailable. No source attribution has been inferred.</td></tr>';
      status.textContent = `Source metadata unavailable: ${error.message}`;
    });
}());

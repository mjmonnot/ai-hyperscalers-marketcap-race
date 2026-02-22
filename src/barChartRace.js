// src/barChartRace.js
// Static "latest-month" bar chart, but robust to uneven end-dates across series.
//
// Key change vs your current file:
// - Instead of taking the single global max(date), we pick the most recent date
//   that has the MOST companies present (ideally all of them).
//
// This prevents "only NVDA" when other series end earlier.

export async function renderBarChartRace({ el, dataUrl, metricLabel = "Market Cap ($B)" }) {
  const data = await d3.csv(dataUrl, d3.autoType);

  // Ensure date is a Date and value is numeric
  const rows = data
    .map(d => ({
      date: d.date instanceof Date ? d.date : new Date(d.date),
      name: String(d.name),
      value: +d.value,
      category: d.category ?? "Unknown"
    }))
    .filter(d => d.date instanceof Date && !Number.isNaN(d.date) && Number.isFinite(d.value));

  // Group by date and count how many companies exist at each date
  const byDate = d3.rollups(
    rows,
    v => ({
      count: new Set(v.map(d => d.name)).size,
      rows: v
    }),
    d => +d.date
  ).sort((a, b) => d3.ascending(a[0], b[0])); // sort by date

  if (byDate.length === 0) {
    el.innerHTML = "<p>No data found.</p>";
    return;
  }

  // Pick the most recent date with the maximum coverage (most companies)
  const maxCoverage = d3.max(byDate, d => d[1].count);
  const candidates = byDate.filter(d => d[1].count === maxCoverage);
  const [bestDateMillis, best] = candidates[candidates.length - 1]; // most recent among max coverage
  const bestDate = new Date(bestDateMillis);

  // Use that date's rows, sorted desc
  const snapshot = best.rows
    .slice()
    .sort((a, b) => d3.descending(a.value, b.value));

  // Basic chart sizing
  const width = 1000;
  const height = 600;
  const margin = { top: 60, right: 30, bottom: 40, left: 220 };

  // Clear + build SVG
  el.innerHTML = "";
  const svg = d3.select(el).append("svg")
    .attr("viewBox", [0, 0, width, height])
    .style("width", "100%")
    .style("height", "auto");

  // Title + date
  const fmtDate = d3.utcFormat("%Y-%m-%d");
  svg.append("text")
    .attr("x", margin.left)
    .attr("y", 28)
    .attr("font-size", 18)
    .attr("font-weight", 600)
    .text("AI Hyperscalers + AI Infra — Market Cap");

  svg.append("text")
    .attr("x", margin.left)
    .attr("y", 48)
    .attr("font-size", 12)
    .attr("fill", "#555")
    .text(`Snapshot date: ${fmtDate(bestDate)} (showing ${maxCoverage} companies)`);

  // Scales
  const x = d3.scaleLinear()
    .domain([0, d3.max(snapshot, d => d.value) || 1])
    .nice()
    .range([margin.left, width - margin.right]);

  const y = d3.scaleBand()
    .domain(snapshot.map(d => d.name))
    .range([margin.top, height - margin.bottom])
    .padding(0.12);

  // Axis
  svg.append("g")
    .attr("transform", `translate(0,${margin.top})`)
    .call(d3.axisTop(x).ticks(width / 120).tickFormat(d3.format(",.0f")))
    .call(g => g.select(".domain").remove());

  svg.append("text")
    .attr("x", width - margin.right)
    .attr("y", margin.top - 22)
    .attr("text-anchor", "end")
    .attr("font-size", 12)
    .attr("fill", "#555")
    .text(metricLabel);

  svg.append("g")
    .attr("transform", `translate(${margin.left},0)`)
    .call(d3.axisLeft(y).tickSize(0))
    .call(g => g.select(".domain").remove());

  // Bars
  svg.append("g")
    .selectAll("rect")
    .data(snapshot)
    .join("rect")
      .attr("x", x(0))
      .attr("y", d => y(d.name))
      .attr("height", y.bandwidth())
      .attr("width", d => x(d.value) - x(0))
      .attr("fill", "#4682B4");

  // Values
  svg.append("g")
    .selectAll("text.value")
    .data(snapshot)
    .join("text")
      .attr("class", "value")
      .attr("x", d => x(d.value) + 6)
      .attr("y", d => y(d.name) + y.bandwidth() / 2)
      .attr("alignment-baseline", "middle")
      .attr("font-size", 11)
      .attr("fill", "#333")
      .text(d => d3.format(",.0f")(d.value));
}

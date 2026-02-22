// src/barChartRace.js
// D3 Bar Chart Race (monthly frames) for data/processed/marketcap_monthly.csv
//
// Expected CSV columns:
//   date (YYYY-MM-DD), name, value, category
//
// Usage (already in index.html):
//   import { renderBarChartRace } from "./src/barChartRace.js";
//   renderBarChartRace({ el: ..., dataUrl: "...", n: 10, duration: 250, metricLabel: "Market Cap ($B)" });

export async function renderBarChartRace({
  el,
  dataUrl,
  n = 10,               // number of bars shown
  duration = 300,       // ms per frame
  k = 6,                // interpolation steps between months (smoothness)
  metricLabel = "Value"
} = {}) {
  // ---- Load + normalize data ----
  const raw = await d3.csv(dataUrl, d3.autoType);

  const data = raw
    .map(d => ({
      date: d.date instanceof Date ? d.date : new Date(d.date),
      name: String(d.name),
      value: +d.value,
      category: d.category ?? "Unknown"
    }))
    .filter(d => d.date instanceof Date && !Number.isNaN(+d.date) && Number.isFinite(d.value))
    .sort((a, b) => d3.ascending(a.date, b.date));

  // Category color palette
  const categories = Array.from(new Set(data.map(d => d.category)));
  const color = d3.scaleOrdinal(categories, d3.schemeTableau10);

  // ---- Helpers ----
  const formatNumber = d3.format(",.0f");
  const formatDate = d3.utcFormat("%Y-%m");

  // Build (date -> Map(name -> value))
  const dateValues = Array.from(
    d3.rollup(
      data,
      v => d3.rollup(v, ([d]) => d.value, d => d.name),
      d => +d.date
    ),
    ([date, values]) => [new Date(date), values]
  ).sort((a, b) => d3.ascending(a[0], b[0]));

  // Rank function (top-n with rank index for y positioning)
  function rank(valueByName) {
    const arr = Array.from(valueByName, ([name, value]) => ({ name, value }));
    arr.sort((a, b) => d3.descending(a.value, b.value));
    for (let i = 0; i < arr.length; ++i) arr[i].rank = Math.min(n, i);
    return arr;
  }

  // Interpolate between adjacent months for smooth animation
  function keyframes(dateValues, k) {
    const frames = [];
    for (let i = 0; i < dateValues.length - 1; ++i) {
      const [dateA, valuesA] = dateValues[i];
      const [dateB, valuesB] = dateValues[i + 1];

      for (let j = 0; j < k; ++j) {
        const t = j / k;
        const values = new Map();
        for (const name of new Set([...valuesA.keys(), ...valuesB.keys()])) {
          const a = valuesA.get(name) ?? 0;
          const b = valuesB.get(name) ?? 0;
          values.set(name, a * (1 - t) + b * t);
        }
        frames.push([new Date(dateA * (1 - t) + dateB * t), rank(values)]);
      }
    }
    // last frame
    const [lastDate, lastValues] = dateValues[dateValues.length - 1];
    frames.push([lastDate, rank(lastValues)]);
    return frames;
  }

  const frames = keyframes(dateValues, k);

  // For smooth enter/exit transitions, track prev/next rank/value per name
  const names = Array.from(new Set(data.map(d => d.name)));
  const nameFrames = new Map(names.map(name => [name, []]));
  for (const [date, ranked] of frames) {
    for (const d of ranked) nameFrames.get(d.name).push({ ...d, date });
  }

  const prev = new Map();
  const next = new Map();
  for (const [, arr] of nameFrames) {
    for (let i = 1; i < arr.length; i++) prev.set(arr[i], arr[i - 1]);
    for (let i = 0; i < arr.length - 1; i++) next.set(arr[i], arr[i + 1]);
  }

  // ---- Layout ----
  const width = 1000;
  const barSize = 42;
  const margin = { top: 20, right: 40, bottom: 20, left: 20 };
  const height = margin.top + barSize * n + margin.bottom;

  const x = d3.scaleLinear([0, 1], [margin.left, width - margin.right]);
  const y = d3.scaleBand()
    .domain(d3.range(n + 1))
    .rangeRound([margin.top, margin.top + barSize * (n + 1)])
    .padding(0.1);

  // Clear container and render SVG
  el.innerHTML = "";
  const svg = d3.select(el)
    .append("svg")
    .attr("viewBox", [0, 0, width, height])
    .style("width", "100%")
    .style("height", "auto");

  // Axis layer
  const axisG = svg.append("g").attr("transform", `translate(0,${margin.top})`);

  // Bars + labels layer
  const barsG = svg.append("g");
  const labelsG = svg.append("g").attr("font-size", 12).attr("font-weight", 500);

  // Ticker (date) in top-right
  const ticker = svg.append("text")
    .attr("x", width - margin.right)
    .attr("y", margin.top + 8)
    .attr("text-anchor", "end")
    .attr("font-size", 28)
    .attr("font-weight", 700)
    .attr("dy", "0.35em");

  // Metric label
  svg.append("text")
    .attr("x", width - margin.right)
    .attr("y", margin.top - 6)
    .attr("text-anchor", "end")
    .attr("font-size", 12)
    .attr("fill", "#555")
    .text(metricLabel);

  function updateAxis([, ranked], transition) {
    x.domain([0, ranked[0]?.value ?? 1]).nice();

    const ticks = x.ticks(width / 160);
    const tick = axisG.selectAll("g.tick").data(ticks, d => d);

    tick.exit().remove();

    const tickEnter = tick.enter().append("g").attr("class", "tick");
    tickEnter.append("line").attr("stroke", "#eee");
    tickEnter.append("text").attr("fill", "#777").attr("font-size", 11).attr("text-anchor", "middle").attr("y", -6);

    const tickMerge = tickEnter.merge(tick);

    tickMerge
      .attr("transform", d => `translate(${x(d)},0)`);

    tickMerge.select("line")
      .attr("y1", 0)
      .attr("y2", height - margin.top - margin.bottom);

    tickMerge.select("text")
      .text(d3.format(",")(d));

    axisG.selectAll(".domain").remove();
  }

  function updateBars([, ranked], transition) {
    const top = ranked.slice(0, n);

    const bar = barsG.selectAll("rect").data(top, d => d.name);

    bar.exit()
      .transition(transition)
      .attr("y", d => y((next.get(d) || d).rank))
      .attr("width", d => x((next.get(d) || d).value) - x(0))
      .remove();

    bar.enter().append("rect")
      .attr("x", x(0))
      .attr("y", d => y((prev.get(d) || d).rank))
      .attr("height", y.bandwidth())
      .attr("fill", d => color(d.category))
      .attr("width", d => x((prev.get(d) || d).value) - x(0))
      .merge(bar)
      .transition(transition)
      .attr("y", d => y(d.rank))
      .attr("width", d => x(d.value) - x(0));
  }

  function updateLabels([, ranked], transition) {
    const top = ranked.slice(0, n);

    const label = labelsG.selectAll("text.label").data(top, d => d.name);

    label.exit()
      .transition(transition)
      .attr("transform", d => `translate(${x((next.get(d) || d).value)},${y((next.get(d) || d).rank)})`)
      .remove();

    const labelEnter = label.enter().append("text")
      .attr("class", "label")
      .attr("transform", d => `translate(${x((prev.get(d) || d).value)},${y((prev.get(d) || d).rank)})`)
      .attr("y", y.bandwidth() / 2)
      .attr("x", 6)
      .attr("dy", "0.35em");

    labelEnter.append("tspan").attr("class", "name").text(d => d.name);
    labelEnter.append("tspan")
      .attr("class", "value")
      .attr("fill", "#666")
      .attr("font-weight", 400)
      .attr("dx", "0.8em");

    labelEnter.merge(label)
      .transition(transition)
      .attr("transform", d => `translate(${x(d.value)},${y(d.rank)})`)
      .select("tspan.value")
      .tween("text", function(d) {
        const a = (prev.get(d) || d).value;
        const b = d.value;
        const i = d3.interpolateNumber(a, b);
        return function(t) {
          this.textContent = formatNumber(i(t));
        };
      });
  }

  // ---- Animate ----
  for (const frame of frames) {
    const [date] = frame;
    const transition = svg.transition().duration(duration).ease(d3.easeLinear);

    ticker.text(formatDate(date));

    updateAxis(frame, transition);
    updateBars(frame, transition);
    updateLabels(frame, transition);

    await transition.end();
  }
}

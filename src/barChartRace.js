// src/barChartRace.js
// Full-feature D3 Bar Chart Race with:
// - play/pause/restart
// - speed control
// - window selector (last N years / full)
// - top-N selector
// - category filtering
// - tooltip (hover)
// - legend metadata export
//
// CSV columns expected: date (YYYY-MM-DD), name, value, category
// value in $B recommended.

export async function createBarChartRace({
  el,
  tooltipEl = null,
  dataUrl,
  n = 10,
  duration = 120,
  k = 2,
  windowYears = 8,
  metricLabel = "Value",
  onStatus = null
} = {}) {
  if (!el) throw new Error("createBarChartRace: missing el");
  if (!dataUrl) throw new Error("createBarChartRace: missing dataUrl");

  const setStatus = (s) => { if (typeof onStatus === "function") onStatus(s); };

  setStatus("Loading CSV…");
  const raw = await d3.csv(dataUrl, d3.autoType);

  const baseData = raw
    .map(d => ({
      date: d.date instanceof Date ? d.date : new Date(d.date),
      name: String(d.name),
      value: +d.value,
      category: d.category ?? "Unknown"
    }))
    .filter(d => d.date instanceof Date && !Number.isNaN(+d.date) && Number.isFinite(d.value))
    .sort((a, b) => d3.ascending(a.date, b.date));

  if (baseData.length === 0) throw new Error("No rows loaded from CSV.");

  // Categories + color
  const categoryNames = Array.from(new Set(baseData.map(d => d.category)));
  const color = d3.scaleOrdinal(categoryNames, d3.schemeTableau10);

  // Tooltip helpers
  const fmtNum = d3.format(",.0f");
  const fmtDate = d3.utcFormat("%Y-%m");

  let state = {
    n,
    duration,
    k,
    windowYears,
    categories: new Set(categoryNames),
    playing: false,
    restartRequested: false,
    stopRequested: false
  };

  // ---------- Rendering scaffolding ----------
  const width = 1000;
  const barSize = 42;
  const margin = { top: 26, right: 46, bottom: 18, left: 20 };
  let height = margin.top + barSize * state.n + margin.bottom;

  el.innerHTML = "";
  const svg = d3.select(el)
    .append("svg")
    .attr("viewBox", [0, 0, width, height])
    .style("width", "100%")
    .style("height", "auto");

  const axisG = svg.append("g").attr("transform", `translate(0,${margin.top})`);
  const barsG = svg.append("g");
  const labelsG = svg.append("g").attr("font-size", 12).attr("font-weight", 500);

  const ticker = svg.append("text")
    .attr("x", width - margin.right)
    .attr("y", margin.top + 6)
    .attr("text-anchor", "end")
    .attr("font-size", 28)
    .attr("font-weight", 700)
    .attr("dy", "0.35em");

  svg.append("text")
    .attr("x", width - margin.right)
    .attr("y", margin.top - 10)
    .attr("text-anchor", "end")
    .attr("font-size", 12)
    .attr("fill", "#555")
    .text(metricLabel);

  const x = d3.scaleLinear([0, 1], [margin.left, width - margin.right]);
  const y = d3.scaleBand()
    .domain(d3.range(state.n + 1))
    .rangeRound([margin.top, margin.top + barSize * (state.n + 1)])
    .padding(0.1);

  function resizeForN() {
    height = margin.top + barSize * state.n + margin.bottom;
    svg.attr("viewBox", [0, 0, width, height]);
    y.domain(d3.range(state.n + 1))
      .rangeRound([margin.top, margin.top + barSize * (state.n + 1)]);
  }

  // ---------- Data transforms (recomputed on window/category/n changes) ----------
  function buildDateValues(data) {
    return Array.from(
      d3.rollup(
        data,
        v => d3.rollup(v, ([d]) => d.value, d => d.name),
        d => +d.date
      ),
      ([date, values]) => [new Date(date), values]
    ).sort((a, b) => d3.ascending(a[0], b[0]));
  }

  function applyWindow(dateValues) {
    if (!state.windowYears || state.windowYears <= 0) return dateValues;
    const last = dateValues[dateValues.length - 1][0];
    const cutoff = new Date(Date.UTC(last.getUTCFullYear() - state.windowYears, last.getUTCMonth(), 1));
    return dateValues.filter(([d]) => d >= cutoff);
  }

  function rank(valueByName) {
    const arr = Array.from(valueByName, ([name, value]) => ({ name, value }));
    arr.sort((a, b) => d3.descending(a.value, b.value));
    for (let i = 0; i < arr.length; ++i) arr[i].rank = Math.min(state.n, i);
    return arr;
  }

  function buildKeyframes(dateValues) {
    const frames = [];
    const K = Math.max(1, state.k);

    for (let i = 0; i < dateValues.length - 1; ++i) {
      const [dateA, valuesA] = dateValues[i];
      const [dateB, valuesB] = dateValues[i + 1];

      for (let j = 0; j < K; ++j) {
        const t = j / K;
        const values = new Map();
        for (const name of new Set([...valuesA.keys(), ...valuesB.keys()])) {
          const a = valuesA.get(name) ?? 0;
          const b = valuesB.get(name) ?? 0;
          values.set(name, a * (1 - t) + b * t);
        }
        frames.push([new Date(dateA * (1 - t) + dateB * t), rank(values)]);
      }
    }

    const [lastDate, lastValues] = dateValues[dateValues.length - 1];
    frames.push([lastDate, rank(lastValues)]);
    return frames;
  }

  function buildPrevNext(frames) {
    // build per-name arrays of frame objects (identity stable by reference)
    const byName = d3.group(frames.flatMap(([, arr]) => arr), d => d.name);

    const prev = new Map();
    const next = new Map();
    for (const [, arr] of byName) {
      for (let i = 1; i < arr.length; i++) prev.set(arr[i], arr[i - 1]);
      for (let i = 0; i < arr.length - 1; i++) next.set(arr[i], arr[i + 1]);
    }
    return { prev, next };
  }

  function filteredData() {
    return baseData.filter(d => state.categories.has(d.category));
  }

  let frames = [];
  let prevNext = { prev: new Map(), next: new Map() };

  function rebuildFrames() {
    const data = filteredData();
    let dv = buildDateValues(data);
    dv = applyWindow(dv);
    frames = buildKeyframes(dv);
    prevNext = buildPrevNext(frames);
  }

  rebuildFrames();
  resizeForN();

  // ---------- Tooltip ----------
  function showTooltip(evt, d, dateStr, rank) {
    if (!tooltipEl) return;
    tooltipEl.style.opacity = 1;
    tooltipEl.innerHTML = `
      <div class="t">${d.name}</div>
      <div class="m">${fmtNum(d.value)} B</div>
      <div class="k">${d.category} • Rank #${rank + 1} • ${dateStr}</div>
    `;
    moveTooltip(evt);
  }

  function moveTooltip(evt) {
    if (!tooltipEl) return;
    const rect = el.getBoundingClientRect();
    const x = evt.clientX - rect.left;
    const y = evt.clientY - rect.top;
    tooltipEl.style.left = `${x}px`;
    tooltipEl.style.top = `${y}px`;
  }

  function hideTooltip() {
    if (!tooltipEl) return;
    tooltipEl.style.opacity = 0;
  }

  // ---------- Update functions ----------
  function updateAxis([, ranked]) {
    x.domain([0, ranked[0]?.value ?? 1]).nice();

    const ticks = x.ticks(width / 160);
    const tick = axisG.selectAll("g.tick").data(ticks, t => t);

    tick.exit().remove();

    const tickEnter = tick.enter().append("g").attr("class", "tick");
    tickEnter.append("line").attr("stroke", "#eee");
    tickEnter.append("text")
      .attr("fill", "#777")
      .attr("font-size", 11)
      .attr("text-anchor", "middle")
      .attr("y", -6);

    const tickMerge = tickEnter.merge(tick);
    tickMerge.attr("transform", t => `translate(${x(t)},0)`);
    tickMerge.select("line")
      .attr("y1", 0)
      .attr("y2", height - margin.top - margin.bottom);
    tickMerge.select("text")
      .text(t => d3.format(",")(t));
  }

  function updateBars([date, ranked], transition) {
    const top = ranked.slice(0, state.n);
    const { prev, next } = prevNext;
    const dateStr = fmtDate(date);

    const bar = barsG.selectAll("rect").data(top, d => d.name);

    bar.exit()
      .on("mousemove", null)
      .on("mouseenter", null)
      .on("mouseleave", null)
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
      .on("mousemove", function(evt, d) {
        const r = top.findIndex(x => x.name === d.name);
        showTooltip(evt, d, dateStr, r >= 0 ? r : d.rank);
      })
      .on("mouseenter", function(evt, d) {
        const r = top.findIndex(x => x.name === d.name);
        showTooltip(evt, d, dateStr, r >= 0 ? r : d.rank);
      })
      .on("mouseleave", hideTooltip)
      .merge(bar)
      .transition(transition)
      .attr("y", d => y(d.rank))
      .attr("width", d => x(d.value) - x(0));
  }

  function updateLabels([, ranked], transition) {
    const top = ranked.slice(0, state.n);
    const { prev, next } = prevNext;

    const label = labelsG.selectAll("text.label").data(top, d => d.name);

    label.exit()
      .transition(transition)
      .attr("transform", d => `translate(${x((next.get(d) || d).value)},${y((next.get(d) || d).rank)})`)
      .remove();

    const enter = label.enter().append("text")
      .attr("class", "label")
      .attr("transform", d => `translate(${x((prev.get(d) || d).value)},${y((prev.get(d) || d).rank)})`)
      .attr("y", y.bandwidth() / 2)
      .attr("x", 6)
      .attr("dy", "0.35em");

    enter.append("tspan").attr("class", "name").text(d => d.name);
    enter.append("tspan")
      .attr("class", "value")
      .attr("fill", "#666")
      .attr("font-weight", 400)
      .attr("dx", "0.8em");

    enter.merge(label)
      .transition(transition)
      .attr("transform", d => `translate(${x(d.value)},${y(d.rank)})`)
      .select("tspan.value")
      .tween("text", function(d) {
        const a = (prev.get(d) || d).value;
        const b = d.value;
        const i = d3.interpolateNumber(a, b);
        return function(t) { this.textContent = fmtNum(i(t)); };
      });
  }

  // ---------- Animation loop (controllable) ----------
  let frameIndex = 0;

  function ensureFrames() {
    if (!frames || frames.length === 0) rebuildFrames();
    if (!frames || frames.length === 0) throw new Error("No frames available after filtering/windowing.");
  }

  async function runLoop() {
    ensureFrames();
    state.stopRequested = false;
    state.restartRequested = false;

    setStatus(`Running… (${fmtDate(frames[0][0])} → ${fmtDate(frames[frames.length - 1][0])})`);

    while (!state.stopRequested) {
      // pause gate
      while (!state.playing && !state.stopRequested) {
        await new Promise(r => setTimeout(r, 50));
      }
      if (state.stopRequested) break;

      if (state.restartRequested) {
        state.restartRequested = false;
        frameIndex = 0;
      }

      const frame = frames[frameIndex];
      const [date] = frame;

      ticker.text(fmtDate(date));
      updateAxis(frame);

      const transition = svg.transition().duration(state.duration).ease(d3.easeLinear);
      updateBars(frame, transition);
      updateLabels(frame, transition);

      setStatus(`Running… ${fmtDate(date)}`);
      await transition.end();

      frameIndex += 1;
      if (frameIndex >= frames.length) {
        // finish
        state.playing = false;
        setStatus("Done (press Restart to replay).");
        break;
      }
    }
  }

  // Start loop (idle until play)
  runLoop().catch(err => {
    state.playing = false;
    setStatus("Error.");
    throw err;
  });

  // ---------- Controller API ----------
  const controller = {
    getMeta() {
      return {
        categories: categoryNames.map(name => ({ name, color: color(name) }))
      };
    },
    play() { state.playing = true; },
    pause() { state.playing = false; },
    restart() { state.restartRequested = true; frameIndex = 0; },
    stop() { state.stopRequested = true; state.playing = false; },
    setSpeed(ms) { state.duration = Math.max(20, +ms || 120); },
    setWindowYears(y) {
      state.windowYears = +y || 0;
      rebuildFrames();
      frameIndex = 0;
    },
    setTopN(newN) {
      state.n = Math.max(3, +newN || 10);
      resizeForN();
      rebuildFrames();
      frameIndex = 0;
    },
    setCategories(list) {
      state.categories = new Set(list && list.length ? list : categoryNames);
      rebuildFrames();
      frameIndex = 0;
      hideTooltip();
    }
  };

  setStatus("Ready (press Play).");
  return controller;
}

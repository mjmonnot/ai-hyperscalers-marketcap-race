export async function renderBarChartRace({ el, dataUrl, metricLabel }) {
  const data = await d3.csv(dataUrl, d3.autoType);
  const width = 900, height = 600;
  const svg = d3.select(el).append("svg")
    .attr("width", width)
    .attr("height", height);

  const latestDate = d3.max(data, d => d.date);
  const latest = data.filter(d => d.date === latestDate);

  const x = d3.scaleLinear()
    .domain([0, d3.max(latest, d => d.value)])
    .range([0, width - 200]);

  const y = d3.scaleBand()
    .domain(latest.map(d => d.name))
    .range([50, height - 50])
    .padding(0.1);

  svg.selectAll("rect")
    .data(latest)
    .enter()
    .append("rect")
    .attr("x", 150)
    .attr("y", d => y(d.name))
    .attr("width", d => x(d.value))
    .attr("height", y.bandwidth())
    .attr("fill", "#4682B4");

  svg.selectAll("text.label")
    .data(latest)
    .enter()
    .append("text")
    .attr("class","label")
    .attr("x", 145)
    .attr("y", d => y(d.name) + y.bandwidth()/2)
    .attr("text-anchor","end")
    .attr("alignment-baseline","middle")
    .text(d => d.name);

  svg.append("text")
    .attr("x", width - 10)
    .attr("y", 30)
    .attr("text-anchor","end")
    .text(metricLabel);
}

import { useEffect, useRef } from "react";
import * as d3 from "d3";

/**
 * The Galaxy — a force-directed constellation of thought bubbles.
 *
 * This is the heart of the demo, so it's tuned for feeling, not just function:
 *  - bubbles drift gently (low alphaDecay) so the map feels alive, not frozen
 *  - new bubbles fade + scale in rather than popping
 *  - connections are soft curved links, weighted by relationship
 *  - color encodes type; size encodes priority
 *
 * Props:
 *   nodes:  [{id, text, type, priority, connections:[id]}]
 *   onTap:  (node) => void   — tapping a bubble asks for guidance (M2)
 */

const TYPE_COLORS = {
  task: "#5B8DEF",     // calm blue — things to do
  emotion: "#E8896B",  // warm terracotta — feelings
  idea: "#9B7EDE",     // soft violet — future intent
};

export default function Galaxy({ nodes, onTap }) {
  const svgRef = useRef(null);
  const simRef = useRef(null);
  const dataRef = useRef({ nodes: [], links: [] });

  // init once
  useEffect(() => {
    const svg = d3.select(svgRef.current);
    const width = svgRef.current.clientWidth;
    const height = svgRef.current.clientHeight;

    svg.selectAll("*").remove();
    const linkLayer = svg.append("g").attr("class", "links");
    const nodeLayer = svg.append("g").attr("class", "nodes");

    const sim = d3
      .forceSimulation()
      .force("charge", d3.forceManyBody().strength(-340))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide().radius((d) => radius(d) + 10))
      .force("link", d3.forceLink().id((d) => d.id).distance(130).strength(0.25))
      .alphaDecay(0.02); // slow decay = gently alive

    sim.on("tick", () => {
      linkLayer
        .selectAll("path")
        .attr("d", (d) => {
          const dx = d.target.x - d.source.x;
          const dy = d.target.y - d.source.y;
          const dr = Math.hypot(dx, dy) * 1.6;
          return `M${d.source.x},${d.source.y}A${dr},${dr} 0 0,1 ${d.target.x},${d.target.y}`;
        });
      nodeLayer.selectAll("g.bubble").attr("transform", (d) => `translate(${d.x},${d.y})`);
    });

    simRef.current = { sim, linkLayer, nodeLayer, width, height };
    return () => sim.stop();
  }, []);

  // update when nodes change
  useEffect(() => {
    if (!simRef.current) return;
    const { sim, linkLayer, nodeLayer, width, height } = simRef.current;

    // merge: keep existing positions, add new nodes near center
    const prev = new Map(dataRef.current.nodes.map((n) => [n.id, n]));
    const merged = nodes.map((n) => {
      const old = prev.get(n.id);
      return old
        ? Object.assign(old, n)
        : { ...n, x: width / 2 + (Math.random() - 0.5) * 60, y: height / 2 + (Math.random() - 0.5) * 60 };
    });

    const idset = new Set(merged.map((n) => n.id));
    const links = [];
    merged.forEach((n) =>
      (n.connections || []).forEach((t) => {
        if (idset.has(t)) links.push({ source: n.id, target: t });
      })
    );
    dataRef.current = { nodes: merged, links };

    // ── links ──
    const linkSel = linkLayer.selectAll("path").data(links, (d) => `${d.source.id || d.source}-${d.target.id || d.target}`);
    linkSel.exit().remove();
    linkSel
      .enter()
      .append("path")
      .attr("fill", "none")
      .attr("stroke", "rgba(255,255,255,0.18)")
      .attr("stroke-width", 1.5);

    // ── bubbles ──
    const bsel = nodeLayer.selectAll("g.bubble").data(merged, (d) => d.id);
    bsel.exit().transition().duration(300).style("opacity", 0).remove();

    const enter = bsel
      .enter()
      .append("g")
      .attr("class", "bubble")
      .style("cursor", "pointer")
      .style("opacity", 0)
      .on("click", (_e, d) => onTap && onTap(d))
      .call(
        d3.drag()
          .on("start", (e, d) => { if (!e.active) sim.alphaTarget(0.2).restart(); d.fx = d.x; d.fy = d.y; })
          .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
          .on("end", (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; })
      );

    // glow
    enter
      .append("circle")
      .attr("class", "glow")
      .attr("r", (d) => radius(d) + 8)
      .attr("fill", (d) => TYPE_COLORS[d.type])
      .attr("opacity", 0.18);
    // body
    enter
      .append("circle")
      .attr("class", "body")
      .attr("r", (d) => radius(d))
      .attr("fill", (d) => TYPE_COLORS[d.type])
      .attr("stroke", "rgba(255,255,255,0.5)")
      .attr("stroke-width", 1.5);
    // label
    enter
      .append("text")
      .text((d) => d.text)
      .attr("text-anchor", "middle")
      .attr("dy", "0.35em")
      .attr("fill", "white")
      .attr("font-size", "12px")
      .attr("font-weight", 600)
      .style("pointer-events", "none")
      .call(wrap, 90);

    enter.transition().duration(450).style("opacity", 1);

    sim.nodes(merged);
    sim.force("link").links(links);
    sim.alpha(0.7).restart();
  }, [nodes, onTap]);

  return <svg ref={svgRef} style={{ width: "100%", height: "100%" }} />;
}

function radius(d) {
  return 26 + (d.priority || 0) * 6;
}

// simple SVG text wrapping
function wrap(text, width) {
  text.each(function () {
    const t = d3.select(this);
    const words = t.text().split(/\s+/).reverse();
    let word, line = [], lineNo = 0;
    const lineHeight = 1.1, y = t.attr("y") || 0, dy = 0;
    let tspan = t.text(null).append("tspan").attr("x", 0).attr("y", y).attr("dy", dy + "em");
    while ((word = words.pop())) {
      line.push(word);
      tspan.text(line.join(" "));
      if (tspan.node().getComputedTextLength() > width && line.length > 1) {
        line.pop();
        tspan.text(line.join(" "));
        line = [word];
        tspan = t.append("tspan").attr("x", 0).attr("y", y).attr("dy", ++lineNo * lineHeight + "em").text(word);
      }
    }
    // vertical center the block
    const count = lineNo + 1;
    t.selectAll("tspan").attr("dy", (_, i) => `${(i - (count - 1) / 2) * lineHeight + 0.35}em`);
  });
}

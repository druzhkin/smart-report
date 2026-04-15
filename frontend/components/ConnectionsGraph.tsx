"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";
import type { Connection } from "@/lib/api";

type Node = { id: string; x?: number; y?: number; fx?: number | null; fy?: number | null };
type Link = { source: string | Node; target: string | Node; conn: Connection };

const natureColors: Record<string, string> = {
  paradox: "#dc2626",
  causal_chain: "#2563eb",
  unexpected_confirmation: "#16a34a",
  shared_variable: "#7c3aed",
};
const strengthWidth: Record<string, number> = {
  strong: 3,
  moderate: 2,
  speculative: 1.2,
};

export function ConnectionsGraph({
  domains,
  connections,
}: {
  domains: string[];
  connections: Connection[];
}) {
  const ref = useRef<SVGSVGElement | null>(null);
  const [hover, setHover] = useState<Connection | null>(null);

  const { nodes, links } = useMemo(() => {
    const nodes: Node[] = domains.map((d) => ({ id: d }));
    const nodeSet = new Set(domains);
    const links: Link[] = [];
    for (const c of connections) {
      if (c.domains.length < 2) continue;
      const [a, b] = c.domains;
      if (!nodeSet.has(a) || !nodeSet.has(b)) continue;
      links.push({ source: a, target: b, conn: c });
    }
    return { nodes, links };
  }, [domains, connections]);

  useEffect(() => {
    if (!ref.current) return;
    const svg = d3.select(ref.current);
    const width = ref.current.clientWidth;
    const height = 320;
    svg.attr("viewBox", `0 0 ${width} ${height}`);
    svg.selectAll("*").remove();

    if (nodes.length === 0) return;

    const sim = d3
      .forceSimulation<Node>(nodes as any)
      .force(
        "link",
        d3.forceLink<Node, Link>(links as any).id((d: any) => d.id).distance(90).strength(0.6)
      )
      .force("charge", d3.forceManyBody().strength(-220))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide(36));

    const link = svg
      .append("g")
      .selectAll("line")
      .data(links)
      .enter()
      .append("line")
      .attr("stroke", (d) => natureColors[d.conn.nature] || "#94a3b8")
      .attr("stroke-opacity", 0.8)
      .attr("stroke-width", (d) => strengthWidth[d.conn.strength] || 1.5)
      .attr("cursor", "pointer")
      .on("mouseenter", (_e, d) => setHover(d.conn))
      .on("mouseleave", () => setHover(null));

    const node = svg
      .append("g")
      .selectAll("g")
      .data(nodes)
      .enter()
      .append("g")
      .call(
        d3
          .drag<any, Node>()
          .on("start", (event, d) => {
            if (!event.active) sim.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on("drag", (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on("end", (event, d) => {
            if (!event.active) sim.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          }) as any
      );

    node
      .append("circle")
      .attr("r", 18)
      .attr("fill", "#1B3A5C")
      .attr("stroke", "#fff")
      .attr("stroke-width", 1.5);

    node
      .append("text")
      .text((d) => d.id)
      .attr("text-anchor", "middle")
      .attr("dy", 32)
      .attr("font-size", 11)
      .attr("fill", "currentColor");

    sim.on("tick", () => {
      link
        .attr("x1", (d: any) => d.source.x)
        .attr("y1", (d: any) => d.source.y)
        .attr("x2", (d: any) => d.target.x)
        .attr("y2", (d: any) => d.target.y);
      node.attr("transform", (d: any) => `translate(${d.x},${d.y})`);
    });

    return () => {
      sim.stop();
    };
  }, [nodes, links]);

  return (
    <div>
      <svg ref={ref} width="100%" height={320} />
      <div className="min-h-[3em] text-xs mt-2">
        {hover ? (
          <div>
            <div className="font-medium">{hover.domains.join(" ↔ ")}</div>
            <div className="muted">{hover.nature} · {hover.strength}</div>
            <div className="mt-1 line-clamp-3">{hover.description}</div>
          </div>
        ) : (
          <div className="muted">Наведи на ребро, чтобы увидеть связь</div>
        )}
      </div>
    </div>
  );
}

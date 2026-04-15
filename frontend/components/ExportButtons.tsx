"use client";

import { exportUrl } from "@/lib/api";
import { FileDown } from "lucide-react";

export function ExportButtons({ id }: { id: string }) {
  return (
    <div className="flex gap-2 flex-wrap">
      <a className="btn" href={exportUrl(id, "md")} target="_blank" rel="noreferrer">
        <FileDown size={14} /> Markdown
      </a>
      <a className="btn" href={exportUrl(id, "docx")} target="_blank" rel="noreferrer">
        <FileDown size={14} /> Word
      </a>
      <a className="btn" href={exportUrl(id, "pptx")} target="_blank" rel="noreferrer">
        <FileDown size={14} /> PowerPoint
      </a>
      <a className="btn" href={exportUrl(id, "json")} target="_blank" rel="noreferrer">
        <FileDown size={14} /> JSON
      </a>
    </div>
  );
}

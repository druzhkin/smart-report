"use client";

// Not used by the primary flow (we go straight from /new to /report/[id]),
// but exposed as a reusable component per the spec structure.

import type { Matrix } from "@/lib/api";
import { useState } from "react";

export function MatrixEditor({
  matrix,
  onChange,
}: {
  matrix: Matrix;
  onChange: (m: Matrix) => void;
}) {
  const [local, setLocal] = useState(matrix);

  function update(next: Matrix) {
    setLocal(next);
    onChange(next);
  }

  return (
    <div className="space-y-3">
      {local.domains.map((d, di) => (
        <div key={di} className="card p-3">
          <input
            value={d.name}
            onChange={(e) => {
              const doms = [...local.domains];
              doms[di] = { ...d, name: e.target.value };
              update({ ...local, domains: doms });
            }}
          />
          <div className="mt-2 space-y-1">
            {d.layers.map((l, li) => (
              <div key={li} className="flex gap-2">
                <input
                  value={l.name}
                  onChange={(e) => {
                    const doms = [...local.domains];
                    const ls = [...doms[di].layers];
                    ls[li] = { ...l, name: e.target.value };
                    doms[di] = { ...d, layers: ls };
                    update({ ...local, domains: doms });
                  }}
                />
                <button
                  className="btn"
                  onClick={() => {
                    const doms = [...local.domains];
                    doms[di] = { ...d, layers: d.layers.filter((_, i) => i !== li) };
                    update({ ...local, domains: doms });
                  }}
                >
                  Удалить
                </button>
              </div>
            ))}
            <button
              className="btn"
              onClick={() => {
                const doms = [...local.domains];
                doms[di] = {
                  ...d,
                  layers: [...d.layers, { name: "Новый слой", description: "" }],
                };
                update({ ...local, domains: doms });
              }}
            >
              + слой
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

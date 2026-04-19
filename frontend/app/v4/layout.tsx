import type { ReactNode } from "react";
import { V4Shell } from "./V4Shell";

export default function V4Layout({ children }: { children: ReactNode }) {
  return (
    <div className="v4" data-theme="v4">
      <V4Shell>
        <main>{children}</main>
      </V4Shell>
    </div>
  );
}

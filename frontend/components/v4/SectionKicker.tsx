// SectionKicker — §NN mono number + uppercase mono label

export function SectionKicker({
  number,
  children,
  align = "left",
}: {
  number?: number | string;
  children?: React.ReactNode;
  align?: "left" | "center";
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "baseline",
        gap: 12,
        justifyContent: align === "center" ? "center" : "flex-start",
      }}
    >
      {number != null && (
        <span
          style={{
            fontFamily: "var(--v4-f-mono)",
            fontVariantNumeric: "tabular-nums",
            fontSize: 11,
            color: "var(--v4-ink-4)",
          }}
        >
          § {number}
        </span>
      )}
      {children && (
        <span
          style={{
            fontFamily: "var(--v4-f-mono)",
            fontSize: 11,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: "var(--v4-ink-3)",
          }}
        >
          {children}
        </span>
      )}
    </div>
  );
}

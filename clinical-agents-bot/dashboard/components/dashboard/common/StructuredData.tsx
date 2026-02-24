"use client";

import type React from "react";

export function formatLabel(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
}

export function StructuredData({ title, data }: { title: string; data: unknown }) {
  if (!data || typeof data !== "object") return null;
  const entries = Object.entries(data as Record<string, unknown>);

  const renderValue = (value: unknown): React.ReactNode => {
    if (value === null || value === undefined || value === "") return "-";
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
    if (Array.isArray(value)) {
      if (!value.length) return "-";
      return (
        <ul style={{ margin: 0, paddingLeft: 16 }}>
          {value.map((item, idx) => (
            <li key={`item-${idx}`}>{typeof item === "object" ? "View details available" : String(item)}</li>
          ))}
        </ul>
      );
    }
    if (typeof value === "object") {
      const nestedEntries = Object.entries(value as Record<string, unknown>);
      if (!nestedEntries.length) return "-";
      return (
        <div className="kv-nested">
          {nestedEntries.map(([nestedKey, nestedValue]) => (
            <div key={nestedKey}>
              <strong>{formatLabel(nestedKey)}:</strong> {renderValue(nestedValue)}
            </div>
          ))}
        </div>
      );
    }
    return String(value);
  };

  return (
    <div style={{ marginTop: 10 }}>
      <h3>{title}</h3>
      <div className="kv-grid">
        {entries.map(([key, value]) => (
          <div className="kv-item" key={key}>
            <div className="kv-label">{formatLabel(key)}</div>
            <div className="kv-value">{renderValue(value)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

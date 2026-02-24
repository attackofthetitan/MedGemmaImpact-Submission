import React from "react";

function inferName(
  explicitName: string | undefined,
  id: string | undefined,
  ariaLabel: string | undefined,
  placeholder: string | undefined,
): string | undefined {
  if (explicitName) return explicitName;
  const source = id ?? ariaLabel ?? placeholder;
  if (!source) return undefined;
  return source.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}

function inferAriaLabel(
  explicitAriaLabel: string | undefined,
  name: string | undefined,
  id: string | undefined,
  placeholder: string | undefined,
): string | undefined {
  if (explicitAriaLabel) return explicitAriaLabel;
  if (name) return name.replace(/_/g, " ");
  if (id) return id.replace(/[-_]/g, " ");
  return placeholder;
}

export function Card({ title, children }: { title?: string; children: React.ReactNode }) {
  return (
    <section className="card">
      {title ? <h3 className="card-title">{title}</h3> : null}
      {children}
    </section>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  const name = inferName(props.name, props.id, props["aria-label"], props.placeholder);
  const ariaLabel = inferAriaLabel(props["aria-label"], name, props.id, props.placeholder);
  return <input {...props} name={name} aria-label={ariaLabel} className={`input ${props.className ?? ""}`.trim()} />;
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  const name = inferName(props.name, props.id, props["aria-label"], undefined);
  const ariaLabel = inferAriaLabel(props["aria-label"], name, props.id, undefined);
  return <select {...props} name={name} aria-label={ariaLabel} className={`input ${props.className ?? ""}`.trim()} />;
}

export function TextArea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const name = inferName(props.name, props.id, props["aria-label"], props.placeholder);
  const ariaLabel = inferAriaLabel(props["aria-label"], name, props.id, props.placeholder);
  return <textarea {...props} name={name} aria-label={ariaLabel} className={`input ${props.className ?? ""}`.trim()} />;
}

export function Button({ variant = "default", ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "default" | "secondary" | "danger" }) {
  const type = props.type ?? "button";
  return <button {...props} type={type} className={`btn btn-${variant} ${props.className ?? ""}`.trim()} />;
}

"use client";

export function ReqLabel({ text, htmlFor }: { text: string; htmlFor?: string }) {
  return <label className="small" htmlFor={htmlFor}>{text} *</label>;
}

export function OptLabel({ text, htmlFor }: { text: string; htmlFor?: string }) {
  return <label className="small" htmlFor={htmlFor}>{text}</label>;
}

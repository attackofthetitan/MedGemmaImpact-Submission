export function splitLines(value: string): string[] {
  return value
    .split("\n")
    .map((v) => v.trim())
    .filter(Boolean);
}

export function splitComma(value: string): string[] {
  return value
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);
}

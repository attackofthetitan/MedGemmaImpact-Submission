"use client";

export function BindingStepper({ step }: { step: 1 | 2 | 3 }) {
  const items = [
    "Generate code",
    "Verify in LINE",
    "Complete",
  ];
  return (
    <div className="binding-stepper" aria-label="Binding progress">
      {items.map((label, idx) => {
        const current = idx + 1;
        const isDone = current < step;
        const isActive = current === step;
        return (
          <div key={label} className={`binding-step ${isDone ? "binding-step-done" : ""} ${isActive ? "binding-step-active" : ""}`}>
            <span className="binding-step-index">{current}</span>
            <span>{label}</span>
          </div>
        );
      })}
    </div>
  );
}

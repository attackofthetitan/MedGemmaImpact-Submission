"use client";

import type React from "react";
import { Button, Card } from "@/components/ui/primitives";
import type { ShowToast } from "@/components/dashboard/shell/useToast";

export function CreateCard({ title, onSubmit, show, children }: { title: string; onSubmit: () => Promise<unknown>; show: ShowToast; children: React.ReactNode }) {
  return (
    <Card title={title}>
      <div className="col">
        {children}
        <Button onClick={() => onSubmit().then(() => show("success", `${title} success`)).catch((e) => show("error", String(e)))}>Submit</Button>
      </div>
    </Card>
  );
}


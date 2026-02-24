"use client";

import { Button } from "@/components/ui/primitives";

export function BindingCodeCard({
  code,
  bindingId,
  expiresAt,
  message,
  onCopyCodeLine,
}: {
  code: string;
  bindingId: string;
  expiresAt: string;
  message: string;
  onCopyCodeLine: () => void;
}) {
  return (
    <div className="otp-card">
      <div className="otp-code">{code}</div>
      <div className="otp-meta">Binding ID: {bindingId} · Expires: {expiresAt}</div>
      <div className="otp-actions">
        <Button variant="secondary" className="copy-btn" onClick={onCopyCodeLine}>Copy Verification Code</Button>
      </div>
      <div className="small" style={{ textAlign: "center", marginTop: 4 }}>
        Clipboard content is only: 驗證碼：{code}
      </div>
      <div className="binding-help">{message}</div>
    </div>
  );
}

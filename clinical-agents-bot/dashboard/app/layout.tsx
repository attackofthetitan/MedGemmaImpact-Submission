import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Clinical Agents Dashboard",
  description: "Role-aware dashboard for clinical-agents",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a href="#main-content" className="small" style={{ position: "absolute", left: -9999, top: 0 }}>
          Skip to main content
        </a>
        {children}
      </body>
    </html>
  );
}

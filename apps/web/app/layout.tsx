import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI AgentOps: replay demo",
  description: "Recorded synthetic runs of AI AgentOps. No model, key or backend is used.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="site">
          <a href="/" className="brand">AI AgentOps</a>
          <p className="banner" role="note">
            Replay mode: recorded synthetic runs. No model, API key or backend is called.
          </p>
        </header>
        <main>{children}</main>
        <footer className="site">
          Synthetic data only. Model replies in these runs are scripted (mock mode); the
          platform's policy, tool and citation checks ran for real.
        </footer>
      </body>
    </html>
  );
}

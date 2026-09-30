import "./globals.css";
import { Background } from "@/components/Background";
import { TabBar } from "@/components/TabBar";
import { AgentGate } from "@/components/AgentGate";
import { Brand } from "@/components/Brand";

export const metadata = {
  title: { default: "Nyaya: Evidence-Grounded Multimodal Claim Resolution Agent", template: "%s | Nyaya" },
  description: "Nyaya resolves support claims with grounded evidence and deterministic policy.",
  icons: { icon: "/nyaya-mark.svg" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Background>
          <header className="brandbar"><Brand /></header>
          {children}
          <TabBar />
          <AgentGate />
        </Background>
      </body>
    </html>
  );
}

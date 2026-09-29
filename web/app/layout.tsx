import "./globals.css";
import { Background } from "@/components/Background";
import { TabBar } from "@/components/TabBar";
import { AgentGate } from "@/components/AgentGate";

export const metadata = { title: "Support Resolution Agent" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Background>
          {children}
          <TabBar />
          <AgentGate />
        </Background>
      </body>
    </html>
  );
}

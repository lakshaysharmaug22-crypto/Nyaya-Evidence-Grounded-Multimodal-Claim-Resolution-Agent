import "./globals.css";
import { Background } from "@/components/Background";
import { TabBar } from "@/components/TabBar";

export const metadata = { title: "Support Resolution Agent" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Background>
          {children}
          <TabBar />
        </Background>
      </body>
    </html>
  );
}

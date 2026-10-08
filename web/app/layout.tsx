import type { Metadata, Viewport } from "next";
import { Bricolage_Grotesque, Hanken_Grotesk, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import AppFrame from "@/components/AppFrame";
import WebVitals from "@/components/WebVitals";

const disp = Bricolage_Grotesque({ subsets: ["latin"], weight: ["500", "600", "700"], variable: "--font-disp" });
const body = Hanken_Grotesk({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-body" });
const mono = JetBrains_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: "Brasper · Panel",
  description: "Panel de operación del bot Brasper (remesas Perú ↔ Brasil)",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#0a3d91" },
    { media: "(prefers-color-scheme: dark)", color: "#0f1420" },
  ],
};

// Aplica el tema guardado antes del primer pintado para evitar el parpadeo claro→oscuro.
const THEME_BOOT = `(function(){try{var t=localStorage.getItem('brasper_theme');if(t!=='light'&&t!=='dark'){t=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'}document.documentElement.dataset.theme=t}catch(e){}})()`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className={`${disp.variable} ${body.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT }} />
      </head>
      <body>
        <WebVitals />
        <AppFrame>{children}</AppFrame>
      </body>
    </html>
  );
}

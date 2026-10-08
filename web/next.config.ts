import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // El indicador de desarrollo tapaba los botones del pie del menú lateral.
  devIndicators: { position: "bottom-right" },
};

export default nextConfig;

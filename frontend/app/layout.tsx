import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "MallMate 演示客服",
  description: "电商客服与售后 Agent 开发骨架",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}


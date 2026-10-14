import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "MallMate 电商售后助手",
  description: "支持身份认证、客服咨询与售后申请的电商 Agent",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}


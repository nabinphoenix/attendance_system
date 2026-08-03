import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "AntimBench", description: "College attendance and CRM" };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en"><body>{children}</body></html>; }

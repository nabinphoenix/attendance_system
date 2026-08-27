import type { Metadata } from "next";
import AgentationDev from "@/components/AgentationDev";
import "./globals.css";
export const metadata: Metadata = { title: "AntimBench", description: "College attendance and CRM" };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en"><body>{children}<AgentationDev /></body></html>; }

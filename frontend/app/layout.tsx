import type { Metadata } from "next";
import AgentationDev from "@/components/AgentationDev";
import { ThemeProvider, ThemeScript } from "@/components/ThemeProvider";
import "./globals.css";
export const metadata: Metadata = { title: "AntimBench | Attendance made clear", description: "College attendance and student support" };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en" suppressHydrationWarning><head><ThemeScript /></head><body><ThemeProvider>{children}</ThemeProvider><AgentationDev /></body></html>; }

import RoleShell from "@/components/RoleShell";
export default function Layout({ children }: { children: React.ReactNode }) { return <RoleShell role="admin">{children}</RoleShell>; }

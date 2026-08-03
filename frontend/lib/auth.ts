import { jwtDecode } from "jwt-decode";
export type Role = "student" | "teacher" | "admin" | "coordinator" | "parent";
export function storeToken(token: string) { localStorage.setItem("access_token", token); }
export function clearToken() { localStorage.removeItem("access_token"); }
export function getRole(): Role | null { const token = localStorage.getItem("access_token"); if (!token) return null; return jwtDecode<{ role?: Role }>(token).role ?? null; }

import type { AttendanceRecord } from "@/types";
export default function AttendanceTable({ records = [] }: { records?: AttendanceRecord[] }) { return <table className="w-full"><thead><tr><th className="text-left">Student</th><th>Status</th></tr></thead><tbody>{records.map((r) => <tr key={r.id}><td>{r.studentName}</td><td>{r.status}</td></tr>)}</tbody></table>; }

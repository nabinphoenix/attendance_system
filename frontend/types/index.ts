export interface User { id: number; email: string; role: "student" | "teacher" | "admin" | "coordinator" | "parent"; }
export interface AttendanceRecord { id: number; studentName: string; status: "present" | "absent" | "late" | "excused"; }
export interface StudentCase { id: number; studentId: number; status: "open" | "closed"; }


import AcademicSetupPage from "@/components/AcademicSetupPage";
import TeacherTimetablePanel from "@/components/TeacherTimetablePanel";

export default function Page() {
  return <><AcademicSetupPage config={{ title: "Teachers", singular: "Teacher", endpoint: "/api/v1/academic/teachers", fields: [{ name: "name", label: "Full name" }, { name: "email", label: "Email", type: "email" }, { name: "password", label: "Temporary password", type: "password" }, { name: "employee_code", label: "Employee code" }], columns: [{ label: "ID", field: "id" }, { label: "Name", field: "name" }, { label: "Email", field: "email" }, { label: "Employee code", field: "employee_code" }] }} /><TeacherTimetablePanel /></>;
}

import AcademicSetupPage from "@/components/AcademicSetupPage";

export default function Page() {
  return <AcademicSetupPage config={{ title: "Programs", singular: "Program", endpoint: "/api/v1/academic/programs", fields: [{ name: "name", label: "Program name" }], columns: [{ label: "ID", field: "id" }, { label: "Program", field: "name" }] }} />;
}

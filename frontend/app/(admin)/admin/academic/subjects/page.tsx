import AcademicSetupPage from "@/components/AcademicSetupPage";

export default function Page() {
  return <AcademicSetupPage config={{ title: "Subjects", singular: "Subject", endpoint: "/api/v1/academic/subjects", fields: [{ name: "name", label: "Subject name" }, { name: "code", label: "Subject code" }, { name: "section_id", label: "Section", optionsEndpoint: "/api/v1/academic/sections" }], columns: [{ label: "ID", field: "id" }, { label: "Subject", field: "name" }, { label: "Code", field: "code" }, { label: "Section", field: "section_id", optionsEndpoint: "/api/v1/academic/sections" }] }} />;
}

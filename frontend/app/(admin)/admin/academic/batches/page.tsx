import AcademicSetupPage from "@/components/AcademicSetupPage";

export default function Page() {
  return <AcademicSetupPage config={{ title: "Batches", singular: "Batch", endpoint: "/api/v1/academic/batches", fields: [{ name: "name", label: "Batch name" }, { name: "program_id", label: "Program", optionsEndpoint: "/api/v1/academic/programs" }], columns: [{ label: "ID", field: "id" }, { label: "Batch", field: "name" }, { label: "Program", field: "program_id", optionsEndpoint: "/api/v1/academic/programs" }] }} />;
}

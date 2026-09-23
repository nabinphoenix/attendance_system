import AcademicSetupPage from "@/components/AcademicSetupPage";

export default function Page() {
  return <AcademicSetupPage config={{
    title: "Sections",
    singular: "Section",
    endpoint: "/api/v1/academic/sections",
    fields: [
      { name: "name", label: "Section name" },
      { name: "batch_id", label: "Permanent Batch", optionsEndpoint: "/api/v1/academic/batches" },
      { name: "combined_with", label: "Combined label (optional)", required: false },
    ],
    columns: [
      { label: "ID", field: "id" },
      { label: "Section", field: "name" },
      { label: "Permanent Batch", field: "batch_id", optionsEndpoint: "/api/v1/academic/batches" },
      { label: "Combined label", field: "combined_with" },
    ],
  }} />;
}

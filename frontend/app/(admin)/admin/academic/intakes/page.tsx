import RoutineMasterPage from "@/components/RoutineMasterPage";

export default function Page() {
  return <RoutineMasterPage
    title="Intakes"
    endpoint="intakes"
    fields={[
      { key: "code", label: "Intake Code" },
      { key: "name", label: "Intake Name (optional)", required: false },
      { key: "start_date", label: "Start date (optional)", type: "date", required: false },
      { key: "program_id", label: "Program", optionsEndpoint: "/api/v1/academic/programs" },
    ]}
  />;
}

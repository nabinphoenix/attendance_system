import RoutineMasterPage from "@/components/RoutineMasterPage";

const roomTypes = [
  { value: "lecture", label: "Lecture" },
  { value: "tutorial", label: "Tutorial" },
  { value: "lab", label: "Lab" },
  { value: "all", label: "All" },
];

export default function Page() {
  return <RoutineMasterPage
    title="Rooms"
    endpoint="rooms"
    fields={[
      { key: "block_id", label: "Campus block", optionsEndpoint: "/api/v1/academic/blocks" },
      { key: "name", label: "Room name" },
      { key: "room_type", label: "Room type", options: roomTypes },
      { key: "capacity", label: "Capacity", type: "number" },
    ]}
  />;
}

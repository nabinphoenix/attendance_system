import RoomAvailabilityPanel from "@/components/RoomAvailabilityPanel";
import { PageHeader } from "@/components/ui/PageHeader";

export default function Page() {
  return <div>
    <PageHeader title="Room availability" description="Find a classroom by date, room type, time slot, and live occupancy." />
    <RoomAvailabilityPanel />
  </div>;
}

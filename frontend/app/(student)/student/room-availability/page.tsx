import RoomAvailabilityPanel from "@/components/RoomAvailabilityPanel";
import { PageHeader } from "@/components/ui/PageHeader";

export default function Page() {
  return <div>
    <PageHeader title="Room availability" description="Find an available classroom by date, room type, or time slot." />
    <RoomAvailabilityPanel />
  </div>;
}

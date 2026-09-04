import RoomAvailabilityPanel from "@/components/RoomAvailabilityPanel";
import { PageHeader } from "@/components/ui/PageHeader";

export default function Page() {
  return <div>
    <PageHeader title="Room availability" description="Check an available classroom before you arrive on campus." />
    <RoomAvailabilityPanel />
  </div>;
}

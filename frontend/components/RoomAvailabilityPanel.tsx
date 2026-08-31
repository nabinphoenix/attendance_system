"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { apiMessage } from "@/components/ScheduleFeedback";

const days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

type AvailabilitySlot = {
  time_slot_id: number;
  start_time: string;
  end_time: string;
  status: "available" | "occupied";
  routine_id?: number | null;
  class_label?: string | null;
  section_names: string[];
};

type AvailabilityRoom = {
  id: number;
  name: string;
  room_type: string;
  capacity: number;
  slots: AvailabilitySlot[];
};

type AvailabilityBlock = { id: number; name: string; rooms: AvailabilityRoom[] };
type AvailabilityResponse = { day_of_week: number; blocks: AvailabilityBlock[] };
type BlockOption = { id: number; name: string };

function timeLabel(value: string) {
  return value.slice(0, 5);
}

export default function RoomAvailabilityPanel({ blocks }: { blocks: BlockOption[] }) {
  const [day, setDay] = useState("0");
  const [blockId, setBlockId] = useState("");
  const [availability, setAvailability] = useState<AvailabilityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({ day_of_week: day });
    if (blockId) params.set("block_id", blockId);
    setLoading(true);
    api.get<AvailabilityResponse>(`/api/v1/academic/room-availability?${params}`, { signal: controller.signal })
      .then((response) => {
        setAvailability(response.data);
        setError("");
      })
      .catch((requestError) => {
        if (!controller.signal.aborted) setError(apiMessage(requestError, "Unable to load room availability."));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [blockId, day]);

  const timeSlots = availability?.blocks.flatMap((block) => block.rooms)[0]?.slots || [];

  return <section className="panel p-5 sm:p-6">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h2 className="text-xl font-semibold">Room availability</h2>
        <p className="mt-1 text-sm text-slate-400">Review every room in Block A, Block B, Block C, and any other configured block against the published routine time slots.</p>
      </div>
    </div>
    <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:max-w-2xl">
      <label><span className="field-label">Routine day</span><select className="w-full" value={day} onChange={(event) => setDay(event.target.value)}>{days.map((name, index) => <option key={name} value={index}>{name}</option>)}</select></label>
      <label><span className="field-label">Block</span><select className="w-full" value={blockId} onChange={(event) => setBlockId(event.target.value)}><option value="">All blocks</option>{blocks.map((block) => <option key={block.id} value={block.id}>{block.name}</option>)}</select></label>
    </div>
    {error && <div className="mt-5"><ErrorState title="Room availability needs attention" description={error} /></div>}
    {loading ? <div className="p-6"><LoadingState label="Loading room availability..." /></div> : !availability?.blocks.length ? <div className="mt-5"><EmptyState title="No blocks found" description="Add blocks and rooms in Academic setup to view their timetable availability." /></div> : <div className="mt-6 space-y-6">
      {availability.blocks.map((block) => <section key={block.id} className="overflow-hidden rounded-xl border border-slate-800">
        <div className="border-b border-slate-800 bg-slate-900/70 px-4 py-3"><h3 className="font-semibold text-slate-100">{block.name}</h3></div>
        {block.rooms.length === 0 ? <div className="p-4 text-sm text-slate-400">No rooms are configured in this block.</div> : <div className="table-wrap"><table><thead><tr><th>Room</th>{timeSlots.map((slot) => <th key={slot.time_slot_id} className="min-w-40 whitespace-nowrap">{timeLabel(slot.start_time)}-{timeLabel(slot.end_time)}</th>)}</tr></thead><tbody>{block.rooms.map((room) => <tr key={room.id}><td className="min-w-48"><p className="font-medium text-slate-100">{room.name}</p><p className="mt-1 text-xs text-slate-400">{room.room_type} / {room.capacity} seats</p></td>{room.slots.map((slot) => <td key={slot.time_slot_id} className="align-top">{slot.status === "available" ? <span className="inline-flex rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-xs font-medium text-emerald-200">Available</span> : <div><span className="inline-flex rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-xs font-medium text-amber-200">Occupied</span><p className="mt-2 text-xs leading-5 text-slate-300">{slot.class_label}</p><p className="mt-1 text-xs text-slate-500">{slot.section_names.join(" + ")}</p></div>}</td>)}</tr>)}</tbody></table></div>}
      </section>)}
    </div>}
  </section>;
}

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { apiMessage } from "@/components/ScheduleFeedback";

const localDate = (value = new Date()) =>
  `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;

type AvailabilitySlot = {
  time_slot_id: number;
  start_time: string;
  end_time: string;
  status: "available" | "occupied";
  routine_id?: number | null;
  override_id?: number | null;
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
type AvailabilityBlock = {
  id: number;
  name: string;
  rooms: AvailabilityRoom[];
};
type AvailabilityResponse = {
  date: string;
  day_of_week: number;
  blocks: AvailabilityBlock[];
};
type AvailabilityFilter =
  "all" | "available-now" | "occupied-now" | "scheduled";

function timeLabel(value: string) {
  return value.slice(0, 5);
}

function minutes(value: string) {
  const [hours, minutes] = value.split(":").map(Number);
  return hours * 60 + minutes;
}

function currentSlot(room: AvailabilityRoom, selectedDate: string, now: Date) {
  if (selectedDate !== localDate(now)) return null;
  const nowMinutes = now.getHours() * 60 + now.getMinutes();
  return (
    room.slots.find(
      (slot) =>
        minutes(slot.start_time) <= nowMinutes &&
        nowMinutes < minutes(slot.end_time),
    ) ?? null
  );
}

export default function RoomAvailabilityPanel() {
  const [selectedDate, setSelectedDate] = useState(localDate());
  const [blockId, setBlockId] = useState("");
  const [roomQuery, setRoomQuery] = useState("");
  const [roomType, setRoomType] = useState("");
  const [slotId, setSlotId] = useState("");
  const [availabilityFilter, setAvailabilityFilter] =
    useState<AvailabilityFilter>("all");
  const [availability, setAvailability] = useState<AvailabilityResponse | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [now, setNow] = useState(new Date());

  const load = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      try {
        const response = await api.get<AvailabilityResponse>(
          `/api/v1/academic/room-availability?date=${selectedDate}`,
          { signal },
        );
        setAvailability(response.data);
        setError("");
      } catch (requestError) {
        if (!signal?.aborted)
          setError(
            apiMessage(requestError, "Unable to load room availability."),
          );
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [selectedDate],
  );

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  useEffect(() => {
    const clock = window.setInterval(() => setNow(new Date()), 30_000);
    const refresh = window.setInterval(() => {
      if (selectedDate === localDate()) void load();
    }, 60_000);
    return () => {
      window.clearInterval(clock);
      window.clearInterval(refresh);
    };
  }, [load, selectedDate]);

  const allRooms = useMemo(
    () => availability?.blocks.flatMap((block) => block.rooms) ?? [],
    [availability],
  );
  const slots = useMemo(
    () => allRooms.find((room) => room.slots.length)?.slots ?? [],
    [allRooms],
  );
  const roomTypes = useMemo(
    () =>
      [
        ...new Set(allRooms.map((room) => room.room_type).filter(Boolean)),
      ].sort(),
    [allRooms],
  );
  const isToday = selectedDate === localDate(now);

  const visibleBlocks = useMemo(
    () =>
      (availability?.blocks ?? [])
        .filter((block) => !blockId || String(block.id) === blockId)
        .map((block) => ({
          ...block,
          rooms: block.rooms.filter((room) => {
            const active = currentSlot(room, selectedDate, now);
            const hasScheduledClass = room.slots.some(
              (slot) => slot.status === "occupied",
            );
            const matchesQuery =
              !roomQuery ||
              `${block.name} ${room.name}`
                .toLowerCase()
                .includes(roomQuery.toLowerCase());
            const matchesType = !roomType || room.room_type === roomType;
            const matchesSlot =
              !slotId ||
              room.slots.some((slot) => String(slot.time_slot_id) === slotId);
            const matchesAvailability =
              availabilityFilter === "all" ||
              (availabilityFilter === "available-now" &&
                isToday &&
                active?.status !== "occupied") ||
              (availabilityFilter === "occupied-now" &&
                isToday &&
                active?.status === "occupied") ||
              (availabilityFilter === "scheduled" && hasScheduledClass);
            return (
              matchesQuery && matchesType && matchesSlot && matchesAvailability
            );
          }),
        }))
        .filter((block) => block.rooms.length),
    [
      availability,
      availabilityFilter,
      blockId,
      isToday,
      now,
      roomQuery,
      roomType,
      selectedDate,
      slotId,
    ],
  );

  const displayedRooms = visibleBlocks.flatMap((block) => block.rooms);
  const occupiedNow = isToday
    ? displayedRooms.filter(
        (room) => currentSlot(room, selectedDate, now)?.status === "occupied",
      ).length
    : 0;
  const activeMinutes = now.getHours() * 60 + now.getMinutes();
  const clearFilters = () => {
    setBlockId("");
    setRoomQuery("");
    setRoomType("");
    setSlotId("");
    setAvailabilityFilter("all");
  };

  return (
    <section className="panel p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold">Room availability</h2>
          <p className="mt-1 max-w-3xl text-sm text-slate-400">
            Live inventory view for the selected date. Approved cancellations,
            room moves, and makeup classes are reflected before a room is shown
            as available.
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          loading={loading}
          onClick={() => void load()}
        >
          {loading ? "Refreshing..." : "Refresh"}
        </Button>
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <label>
          <span className="field-label">Date</span>
          <input
            className="w-full"
            type="date"
            value={selectedDate}
            onChange={(event) => {
              const nextDate = event.target.value || localDate();
              setSelectedDate(nextDate);
              if (nextDate !== localDate())
                setAvailabilityFilter((value) =>
                  value === "available-now" || value === "occupied-now"
                    ? "all"
                    : value,
                );
            }}
          />
        </label>
        <label>
          <span className="field-label">Block</span>
          <select
            className="w-full"
            value={blockId}
            onChange={(event) => setBlockId(event.target.value)}
          >
            <option value="">All blocks</option>
            {(availability?.blocks ?? []).map((block) => (
              <option key={block.id} value={block.id}>
                {block.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="field-label">Room search</span>
          <input
            className="w-full"
            placeholder="Block or room"
            value={roomQuery}
            onChange={(event) => setRoomQuery(event.target.value)}
          />
        </label>
        <label>
          <span className="field-label">Room type</span>
          <select
            className="w-full"
            value={roomType}
            onChange={(event) => setRoomType(event.target.value)}
          >
            <option value="">All room types</option>
            {roomTypes.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="field-label">Time slot</span>
          <select
            className="w-full"
            value={slotId}
            onChange={(event) => setSlotId(event.target.value)}
          >
            <option value="">All time slots</option>
            {slots.map((slot) => (
              <option key={slot.time_slot_id} value={slot.time_slot_id}>
                {timeLabel(slot.start_time)} to {timeLabel(slot.end_time)}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="field-label">Availability</span>
          <select
            className="w-full"
            value={availabilityFilter}
            onChange={(event) =>
              setAvailabilityFilter(event.target.value as AvailabilityFilter)
            }
          >
            <option value="all">All rooms</option>
            <option value="available-now" disabled={!isToday}>
              Available now
            </option>
            <option value="occupied-now" disabled={!isToday}>
              Occupied now
            </option>
            <option value="scheduled">Has a scheduled class</option>
          </select>
        </label>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm">
        <div className="flex flex-wrap gap-3">
          <span className="rounded-full border border-slate-700 px-3 py-1 text-slate-300">
            {displayedRooms.length} rooms shown
          </span>
          {isToday ? (
            <>
              <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-emerald-200">
                {displayedRooms.length - occupiedNow} available now
              </span>
              <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-amber-200">
                {occupiedNow} occupied now
              </span>
            </>
          ) : (
            <span className="rounded-full border border-sky-500/30 bg-sky-500/10 px-3 py-1 text-sky-200">
              Schedule preview for {availability?.date ?? selectedDate}
            </span>
          )}
        </div>
        <Button type="button" variant="ghost" size="sm" onClick={clearFilters}>
          Clear filters
        </Button>
      </div>
      {isToday && (
        <p className="mt-3 text-xs text-slate-500">
          Live status uses your local time (
          {now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}).
          The table remains a full schedule view for the day.
        </p>
      )}

      {error && (
        <div className="mt-5">
          <ErrorState
            title="Room availability needs attention"
            description={error}
            onRetry={() => void load()}
          />
        </div>
      )}
      {loading && !availability ? (
        <div className="p-6">
          <LoadingState label="Loading room availability..." />
        </div>
      ) : !availability?.blocks.length ? (
        <div className="mt-5">
          <EmptyState
            title="No rooms found"
            description="Add blocks and rooms in Academic setup to view their availability."
          />
        </div>
      ) : !visibleBlocks.length ? (
        <div className="mt-5">
          <EmptyState
            title="No rooms match these filters"
            description="Clear a filter or choose another date, block, room type, or time slot."
          />
        </div>
      ) : (
        <div className="mt-6 space-y-6">
          {visibleBlocks.map((block) => (
            <section
              key={block.id}
              className="overflow-hidden rounded-xl border border-slate-800"
            >
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 bg-slate-900/70 px-4 py-3">
                <h3 className="font-semibold text-slate-100">{block.name}</h3>
                <span className="text-sm text-slate-400">
                  {block.rooms.length} room{block.rooms.length === 1 ? "" : "s"}
                </span>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Room</th>
                      {slots
                        .filter(
                          (slot) =>
                            !slotId || String(slot.time_slot_id) === slotId,
                        )
                        .map((slot) => (
                          <th
                            key={slot.time_slot_id}
                            className="min-w-44 whitespace-nowrap"
                          >
                            {timeLabel(slot.start_time)} to{" "}
                            {timeLabel(slot.end_time)}
                            {isToday &&
                              minutes(slot.start_time) <= activeMinutes &&
                              activeMinutes < minutes(slot.end_time) && (
                                <span className="ml-2 rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] text-emerald-200">
                                  Now
                                </span>
                              )}
                          </th>
                        ))}
                    </tr>
                  </thead>
                  <tbody>
                    {block.rooms.map((room) => {
                      const active = currentSlot(room, selectedDate, now);
                      return (
                        <tr key={room.id}>
                          <td className="min-w-52">
                            <p className="font-medium text-slate-100">
                              {room.name}
                            </p>
                            <p className="mt-1 text-xs text-slate-400">
                              {room.room_type} / {room.capacity} seats
                            </p>
                            {isToday && (
                              <p
                                className={`mt-2 text-xs font-medium ${active?.status === "occupied" ? "text-amber-300" : "text-emerald-300"}`}
                              >
                                {active?.status === "occupied"
                                  ? "Occupied now"
                                  : "Available now"}
                              </p>
                            )}
                          </td>
                          {room.slots
                            .filter(
                              (slot) =>
                                !slotId || String(slot.time_slot_id) === slotId,
                            )
                            .map((slot) => (
                              <td key={slot.time_slot_id} className="align-top">
                                {slot.status === "available" ? (
                                  <span className="inline-flex rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-xs font-medium text-emerald-200">
                                    Available
                                  </span>
                                ) : (
                                  <div>
                                    <span className="inline-flex rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-xs font-medium text-amber-200">
                                      Occupied
                                    </span>
                                    {slot.override_id && (
                                      <span className="ml-1 inline-flex rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-1 text-xs font-medium text-sky-200">
                                        Adjusted
                                      </span>
                                    )}
                                    <p className="mt-2 text-xs leading-5 text-slate-200">
                                      {slot.class_label}
                                    </p>
                                    <p className="mt-1 text-xs text-slate-500">
                                      {slot.section_names.join(" + ")}
                                    </p>
                                  </div>
                                )}
                              </td>
                            ))}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          ))}
        </div>
      )}
    </section>
  );
}

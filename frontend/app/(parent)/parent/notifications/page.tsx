"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";

type LinkedStudent = {
  id: number;
  name: string | null;
  email: string | null;
  roll_number: string;
};

type Notification = {
  id: number;
  subject: string;
  body: string;
  status: string;
  created_at: string;
};

export default function Page() {
  const [students, setStudents] = useState<LinkedStudent[]>([]);
  const [notifications, setNotifications] = useState<Notification[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([
      api.get<LinkedStudent[]>("/api/v1/guardians/me/students"),
      api.get<Notification[]>("/api/v1/guardians/me/notifications"),
    ])
      .then(([studentResponse, notificationResponse]) => {
        if (!active) return;
        setStudents(studentResponse.data ?? []);
        setNotifications(notificationResponse.data ?? []);
      })
      .catch((requestError: any) => {
        if (active) setError(requestError.response?.data?.detail ?? "Unable to load your parent workspace");
      });
    return () => {
      active = false;
    };
  }, []);

  if (error) return <><h1 className="mb-6 text-3xl font-bold">Notifications</h1><ErrorState title="Unable to load your parent workspace" description={error} /></>;
  if (notifications === null) return <><h1 className="mb-6 text-3xl font-bold">Notifications</h1><LoadingState label="Loading parent workspace" /></>;

  return (
    <div className="max-w-4xl">
      <h1 className="text-3xl font-bold">Notifications</h1>
      <p className="mt-2 text-slate-400">Stay informed about linked student attendance and support updates.</p>

      <section className="mt-8" aria-labelledby="linked-students-heading">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <h2 id="linked-students-heading" className="text-xl font-semibold">Linked students</h2>
            <p className="mt-1 text-sm text-slate-400">Students connected to this parent account.</p>
          </div>
          <span className="text-sm text-slate-400">{students.length} linked</span>
        </div>
        {students.length ? (
          <div className="grid gap-3 sm:grid-cols-2">
            {students.map((student) => (
              <article key={student.id} className="panel p-4">
                <h3 className="text-lg font-semibold">{student.name || `Student #${student.id}`}</h3>
                {student.email && <p className="mt-1 text-sm text-slate-400">{student.email}</p>}
                <p className="mt-3 text-sm text-slate-300">Roll number: <span className="font-medium">{student.roll_number}</span></p>
              </article>
            ))}
          </div>
        ) : <div className="panel"><EmptyState title="No linked students yet" description="Ask your college administrator to link a student to this parent account." /></div>}
      </section>

      <section className="mt-10" aria-labelledby="notifications-heading">
        <div className="mb-3">
          <h2 id="notifications-heading" className="text-xl font-semibold">Recent notifications</h2>
          <p className="mt-1 text-sm text-slate-400">Attendance alerts and student-support updates will appear here.</p>
        </div>
        {notifications.length ? notifications.map((notification) => (
          <article key={notification.id} className="panel mb-3 p-4">
            <div className="flex items-start justify-between gap-3">
              <h3 className="font-semibold">{notification.subject}</h3>
              <span className="capitalize text-sm text-slate-400">{notification.status}</span>
            </div>
            <p className="my-2 whitespace-pre-wrap text-slate-300">{notification.body}</p>
            <small className="text-slate-500">{new Date(notification.created_at).toLocaleString()}</small>
          </article>
        )) : <div className="panel"><EmptyState title="No notifications yet" description="You will receive an alert when a linked student's attendance needs attention or a support update is available." /></div>}
      </section>
    </div>
  );
}

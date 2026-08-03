import QRDisplay from "@/components/QRDisplay";
export default async function Page({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <><h1 className="mb-6 text-3xl font-bold">Session {id}</h1><QRDisplay value={id} /></>; }


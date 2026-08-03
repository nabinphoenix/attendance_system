"use client";
import { QRCodeSVG } from "qrcode.react";
export default function QRDisplay({ value }: { value: string }) { return <div className="inline-block rounded-xl bg-white p-5"><QRCodeSVG value={value} size={280} level="M" /></div>; }

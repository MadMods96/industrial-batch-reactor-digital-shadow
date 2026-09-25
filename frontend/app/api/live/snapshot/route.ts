import { NextResponse } from "next/server";
import { liveSnapshot } from "@/lib/demo/plant";

export const dynamic = "force-dynamic";

export function GET() {
  return NextResponse.json(liveSnapshot());
}

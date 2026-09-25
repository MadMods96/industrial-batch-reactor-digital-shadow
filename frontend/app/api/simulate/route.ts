import { NextResponse } from "next/server";
import { demoSimulate } from "@/lib/demo/plant";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const body = await req.json();
  return NextResponse.json(demoSimulate(body));
}

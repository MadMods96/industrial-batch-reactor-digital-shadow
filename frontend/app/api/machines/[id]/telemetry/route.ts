import { NextResponse } from "next/server";
import { demoTelemetry } from "@/lib/demo/plant";

export const dynamic = "force-dynamic";

export function GET(_req: Request, ctx: { params: { id: string } }) {
  return NextResponse.json(demoTelemetry(Number(ctx.params.id)));
}

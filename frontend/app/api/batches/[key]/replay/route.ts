import { NextResponse } from "next/server";
import { demoReplay } from "@/lib/demo/plant";

export const dynamic = "force-dynamic";

export function GET(_req: Request, ctx: { params: { key: string } }) {
  return NextResponse.json(demoReplay(ctx.params.key));
}

export type VisualParams = {
  door: number;
  flame: number;
  gasFlow: number;
  n2Flow: number;
  condenser: number;
  chute: number;
  solenoid: number;
  cooling: number;
  shellRamp: boolean;
  unknown: boolean;
};

/** Stack-light band: red / amber / green / blue (top → bottom). */
export type StackTone = "red" | "amber" | "green" | "blue";

const BASE: VisualParams = {
  door: 0, flame: 0, gasFlow: 0, n2Flow: 0, condenser: 0, chute: 0,
  solenoid: 0, cooling: 0, shellRamp: true, unknown: false,
};

export const STATE_VISUAL: Record<string, VisualParams> = {
  idle: { ...BASE, shellRamp: true },
  heating: { ...BASE, flame: 1 },
  gas: { ...BASE, flame: 0.7, gasFlow: 1, condenser: 1 },
  solenoid_on: { ...BASE, flame: 0.7, gasFlow: 1, condenser: 1, solenoid: 1 },
  cooling: { ...BASE, cooling: 1, gasFlow: 0.15 },
  n2_purging: { ...BASE, n2Flow: 1 },
  carbon_discharge: { ...BASE, chute: 1 },
  main_door_open: { ...BASE, door: 1 },
  unknown: { ...BASE, shellRamp: false, unknown: true },
};

export function visualFor(state: string): VisualParams {
  return STATE_VISUAL[state] ?? STATE_VISUAL.unknown;
}

/** Plant tower light meaning for operators. */
export function stackToneFor(process: string, fault: string, stale: boolean): StackTone {
  if (stale || (fault && fault !== "none")) return "red";
  if (process === "heating" || process === "gas" || process === "solenoid_on") return "green";
  if (
    process === "cooling" ||
    process === "n2_purging" ||
    process === "carbon_discharge" ||
    process === "main_door_open"
  ) {
    return "amber";
  }
  return "blue"; // idle / unknown → standby
}

export const REQUIRED_NODES = [
  "Reactor", "Vessel", "Vessel_Shell", "Vessel_Interior", "Vessel_Insulation", "Vessel_Supports",
  "Door_Hinge", "Door", "Door_Plate", "Door_Flange", "Door_Bolts", "Door_Handle",
  "Burner", "Burner_Body", "Burner_Nozzle", "Burner_Flame_Anchor",
  "Separator", "Separator_Shell", "Separator_Supports",
  "Condenser", "Condenser_Body", "Condenser_Coils", "Condenser_Outlet",
  "Piping", "Pipe_Gas_Passage", "Pipe_Separator_Condenser", "Pipe_N2_Line", "Pipe_Gas_Outlet", "Valve_Solenoid",
  "Discharge", "Discharge_Chute", "Discharge_Chute_Hinge", "Discharge_Particle_Anchor", "Carbon_Bin", "Carbon_Bin_Fill",
  "Instruments", "Gauge_Pressure_Reactor", "Gauge_Needle_Pr", "Gauge_Pressure_Separator", "Gauge_Needle_Ps",
  "Sensor_Badge_Pressure", "Beacon_Light", "Stack_Light",
  "Frame", "Frame_Structure", "Frame_Ladder", "Frame_Platform", "HUD_Anchor",
];

const required = [
  "Reactor", "Vessel_Shell", "Door_Hinge", "Burner_Flame_Anchor", "Separator_Shell",
  "Condenser_Outlet", "Pipe_Gas_Passage", "Pipe_N2_Line", "Pipe_Gas_Outlet", "Valve_Solenoid",
  "Discharge_Chute_Hinge", "Carbon_Bin_Fill", "Gauge_Needle_Pr", "Sensor_Badge_Pressure",
  "Beacon_Light", "HUD_Anchor",
];
const fs = require("fs");
const src = fs.readFileSync(new URL("../components/scene/ReactorPlaceholder.tsx", import.meta.url), "utf8");
const missing = required.filter((name) => !src.includes(`name="${name}"`) && !src.includes(`name='${name}'`));
if (missing.length) {
  console.error("placeholder node contract failed", missing);
  process.exit(1);
}
console.log("placeholder node contract ok");

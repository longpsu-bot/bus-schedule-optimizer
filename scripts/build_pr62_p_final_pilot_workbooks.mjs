import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const args = Object.fromEntries(
  process.argv.slice(2).map((value, index, all) =>
    value.startsWith("--") ? [value.slice(2), all[index + 1]] : ["", ""],
  ),
);
if (!args.data || !args["output-dir"]) throw new Error("--data and --output-dir are required");
const data = JSON.parse(await fs.readFile(args.data, "utf8"));
const outputDir = args["output-dir"];

const COLORS = {
  navy: "#17365D", blue: "#2F75B5", paleBlue: "#DDEBF7", paleGold: "#FFF2CC",
  paleGreen: "#E2F0D9", paleGray: "#F2F2F2", white: "#FFFFFF", text: "#1F2937",
  line: "#D9E2F3",
};
const toTime = (seconds) => seconds / 86400;
const titleFormat = {
  fill: COLORS.navy, font: { bold: true, color: COLORS.white, size: 16 },
  verticalAlignment: "center",
};
const headerFormat = {
  fill: COLORS.blue, font: { bold: true, color: COLORS.white },
  verticalAlignment: "center", wrapText: true,
  borders: { preset: "outside", style: "thin", color: COLORS.line },
};

function styleHeader(sheet, range) { sheet.getRange(range).format = headerFormat; }
function addTable(sheet, range, name) {
  const table = sheet.tables.add(range, true, name);
  table.style = "TableStyleMedium2";
  table.showFilterButton = true;
  return table;
}
function setColumns(sheet, widths) {
  for (const [column, width] of Object.entries(widths)) {
    sheet.getRange(`${column}:${column}`).format.columnWidth = width;
  }
}
function rhythm(route, metric) {
  return ["outbound", "inbound"].reduce(
    (total, direction) => total + route.directions[direction].metrics.rhythm_simplicity[metric], 0,
  );
}
function finalGaps(route) {
  return ["outbound", "inbound"].flatMap((direction) => {
    const departures = route.directions[direction].exact_departures;
    return departures.slice(1).map((value, index) => (value - departures[index]) / 60);
  });
}

function buildSummary(workbook, route) {
  const sheet = workbook.worksheets.add("Summary");
  sheet.showGridLines = false;
  sheet.mergeCells("A1:B1");
  sheet.getRange("A1").values = [[`Route ${route.route_id} — Final V2 Recertified Pilot Timetable`]];
  sheet.getRange("A1:B1").format = titleFormat;
  sheet.getRange("A1:B1").format.rowHeight = 30;
  const out = route.directions.outbound.exact_departures;
  const inbound = route.directions.inbound.exact_departures;
  const rows = [
    ["Route", route.route_id],
    ["Certification status", route.certification_status],
    ["Selection policy", route.selection_policy],
    ["Selected pair fingerprint", route.selected_pair_fingerprint],
    ["Common anchor fingerprint", route.common_anchor_fingerprint],
    ["TE materiality band (trip-equivalent)", data.policy.te_materiality_band_trips],
    ["Selected pair TE", route.te.pair],
    ["Selected pair SSE", route.metrics.observed_demand_mismatch],
    ["Trips/day", null],
    ["Trips outbound", out.length],
    ["Trips inbound", inbound.length],
    ["First departure outbound", toTime(out[0])],
    ["Last departure outbound", toTime(out.at(-1))],
    ["First departure inbound", toTime(inbound[0])],
    ["Last departure inbound", toTime(inbound.at(-1))],
    ["Runtime (minutes each direction)", route.runtime_minutes],
    ["Official minimum layover (minutes)", route.official_minimum_layover_minutes],
    ["Fleet ceiling", route.fleet_ceiling],
    ["Fleet required", route.fleet_plan.fleet_required],
    ["Fleet spare", null],
    ["Average expected passenger wait (minutes)", route.metrics.demand_weighted_expected_passenger_wait_minutes],
    ["Outbound maximum bucket wait (minutes)", route.access.outbound.selected_maximum_bucket_wait_minutes],
    ["Inbound maximum bucket wait (minutes)", route.access.inbound.selected_maximum_bucket_wait_minutes],
    ["Maximum directional P90 (minutes)", route.metrics.maximum_directional_p90_bucket_wait_minutes],
    ["Actual ServiceRegime count", route.metrics.actual_service_regime_count],
    ["Sustained headway level count", route.metrics.total_directional_sustained_headway_level_count],
    ["Effective palette count", route.metrics.total_directional_effective_palette_count],
    ["Selection classification", route.selection_classification],
    ["Settlement used", route.settlement_used ? "Yes" : "No"],
    ["Certification classification", route.certification_classification],
  ];
  sheet.getRange(`A3:B${rows.length + 2}`).values = rows;
  sheet.getRange("B11").formulas = [["=B12+B13"]];
  sheet.getRange("B22").formulas = [["=B20-B21"]];
  sheet.getRange(`A3:A${rows.length + 2}`).format = { fill: COLORS.paleBlue, font: { bold: true, color: COLORS.text } };
  sheet.getRange(`A3:B${rows.length + 2}`).format.borders = {
    insideHorizontal: { style: "thin", color: COLORS.line },
    top: { style: "thin", color: COLORS.line }, bottom: { style: "thin", color: COLORS.line },
    left: { style: "thin", color: COLORS.line }, right: { style: "thin", color: COLORS.line },
  };
  sheet.getRange("B14:B17").format.numberFormat = "hh:mm";
  sheet.getRange("B8:B10").format.numberFormat = "0.000000000";
  sheet.getRange("B23:B26").format.numberFormat = "0.000000";
  sheet.getRange("B5:B7").format.wrapText = true;
  sheet.getRange("B30:B32").format.wrapText = true;
  setColumns(sheet, { A: 43, B: 92 });
  sheet.freezePanes.freezeRows(2);
}

function timetableRows(direction) {
  const regimeByDeparture = new Map();
  for (const regime of direction.service_regimes) {
    for (const departure of regime.departures) regimeByDeparture.set(departure, regime.service_regime_id);
  }
  return direction.exact_departures.map((departure, index, values) => [
    index + 1, toTime(departure), regimeByDeparture.get(departure),
    index === 0 ? null : (departure - values[index - 1]) / 60,
  ]);
}
function buildTimetable(workbook, route) {
  const sheet = workbook.worksheets.add("Timetable");
  sheet.showGridLines = false;
  const headers = [["Sequence", "Departure", "ServiceRegime", "Headway from previous (min)"]];
  const outRows = timetableRows(route.directions.outbound);
  const inRows = timetableRows(route.directions.inbound);
  sheet.getRange(`A1:D${outRows.length + 1}`).values = [...headers, ...outRows];
  sheet.getRange(`F1:I${inRows.length + 1}`).values = [...headers, ...inRows];
  addTable(sheet, `A1:D${outRows.length + 1}`, `Route${route.route_id}POutboundTimetable`);
  addTable(sheet, `F1:I${inRows.length + 1}`, `Route${route.route_id}PInboundTimetable`);
  styleHeader(sheet, "A1:D1"); styleHeader(sheet, "F1:I1");
  sheet.getRange(`B2:B${outRows.length + 1}`).format.numberFormat = "hh:mm";
  sheet.getRange(`G2:G${inRows.length + 1}`).format.numberFormat = "hh:mm";
  const fills = [COLORS.paleBlue, COLORS.paleGold, COLORS.paleGreen, COLORS.paleGray];
  for (const [startCol, rows] of [["A", outRows], ["F", inRows]]) {
    const endCol = startCol === "A" ? "D" : "I";
    let start = 2; let current = rows[0][2]; let colorIndex = 0;
    for (let index = 1; index <= rows.length; index += 1) {
      if (index === rows.length || rows[index][2] !== current) {
        sheet.getRange(`${startCol}${start}:${endCol}${index + 1}`).format.fill = fills[colorIndex % fills.length];
        start = index + 2; current = index < rows.length ? rows[index][2] : current; colorIndex += 1;
      }
    }
  }
  setColumns(sheet, { A: 11, B: 13, C: 27, D: 27, E: 3, F: 11, G: 13, H: 27, I: 27 });
  sheet.freezePanes.freezeRows(1);
}

function buildServiceRegimes(workbook, route) {
  const sheet = workbook.worksheets.add("ServiceRegimes");
  sheet.showGridLines = false;
  const rows = [["Direction", "ServiceRegime ID", "First departure", "Last departure", "Uniform headway (min)", "Trip count", "Source DemandRegime evidence IDs"]];
  for (const direction of ["outbound", "inbound"]) {
    for (const regime of route.directions[direction].service_regimes) {
      rows.push([direction, regime.service_regime_id, toTime(regime.first_departure), toTime(regime.last_departure), regime.uniform_headway_minutes, regime.trip_count, regime.demand_regime_ids.join(", ")]);
    }
  }
  sheet.getRange(`A1:G${rows.length}`).values = rows;
  addTable(sheet, `A1:G${rows.length}`, `Route${route.route_id}PServiceRegimes`);
  styleHeader(sheet, "A1:G1");
  sheet.getRange(`C2:D${rows.length}`).format.numberFormat = "hh:mm";
  sheet.getRange(`G2:G${rows.length}`).format.wrapText = true;
  setColumns(sheet, { A: 14, B: 27, C: 16, D: 16, E: 23, F: 13, G: 42 });
  sheet.freezePanes.freezeRows(1);
}

function buildDemandComparison(workbook, route) {
  const sheet = workbook.worksheets.add("Demand_Comparison");
  sheet.showGridLines = false;
  const rows = [["Direction", "Start", "End", "Observed demand", "Scenario B/current service count", "Final V2 service count", "Demand share", "Scenario B service share", "Final V2 service share"]];
  for (const item of route.demand_rows) rows.push([
    item.direction, toTime(item.start), toTime(item.end), item.observed_demand,
    item.scenario_b_service_count, item.final_service_count, item.demand_share,
    item.scenario_b_service_share, item.final_service_share,
  ]);
  sheet.getRange(`A1:I${rows.length}`).values = rows;
  addTable(sheet, `A1:I${rows.length}`, `Route${route.route_id}PDemandComparison`);
  styleHeader(sheet, "A1:I1");
  sheet.getRange(`B2:C${rows.length}`).format.numberFormat = "hh:mm";
  sheet.getRange(`D2:D${rows.length}`).format.numberFormat = "0.00";
  sheet.getRange(`G2:I${rows.length}`).format.numberFormat = "0.00%";
  const helperStart = 25;
  const helperEnd = helperStart + rows.length - 1;
  sheet.getRange(`K${helperStart}:N${helperStart}`).values = [["Bucket", "Observed demand profile", "Scenario B/current service", "Final V2 service"]];
  sheet.getRange(`K${helperStart + 1}:N${helperEnd}`).formulas = route.demand_rows.map((_, index) => {
    const row = index + 2;
    return [`=A${row}&" "&TEXT(B${row},"hh:mm")`, `=G${row}`, `=H${row}`, `=I${row}`];
  });
  styleHeader(sheet, `K${helperStart}:N${helperStart}`);
  sheet.getRange(`L${helperStart + 1}:N${helperEnd}`).format.numberFormat = "0.00%";
  const chart = sheet.charts.add("line", sheet.getRange(`K${helperStart}:N${helperEnd}`));
  chart.title = "Observed demand vs current and Final V2 service shares";
  chart.hasLegend = true;
  chart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 8 } };
  chart.yAxis = { numberFormatCode: "0%", min: 0 };
  chart.setPosition("K2", "T22");
  const noteStart = helperEnd + 2;
  sheet.getRange(`K${noteStart}:T${noteStart + 1}`).merge();
  sheet.getRange(`K${noteStart}`).values = [["Service is not expected to follow demand 1:1; all three profiles use the same authoritative bucket scale."]];
  sheet.getRange(`K${noteStart}:T${noteStart + 1}`).format = { fill: COLORS.paleGold, wrapText: true, font: { italic: true, color: COLORS.text } };
  setColumns(sheet, { A: 14, B: 11, C: 11, D: 18, E: 29, F: 23, G: 15, H: 25, I: 22, J: 3, K: 23, L: 23, M: 26, N: 22 });
  sheet.freezePanes.freezeRows(1);
}

function buildComparison(workbook, route) {
  const sheet = workbook.worksheets.add("Comparison");
  sheet.showGridLines = false;
  const scenario = route.scenario_b;
  const out = route.directions.outbound.exact_departures;
  const inbound = route.directions.inbound.exact_departures;
  const gaps = finalGaps(route);
  const rows = [
    ["Metric", "Scenario B/current", "Final V2 selected", "Unit / interpretation"],
    ["Total trips", scenario.total_trips, out.length + inbound.length, "trips/day"],
    ["First departure outbound", toTime(scenario.directions.outbound.first), toTime(out[0]), "HH:MM"],
    ["Last departure outbound", toTime(scenario.directions.outbound.last), toTime(out.at(-1)), "HH:MM"],
    ["First departure inbound", toTime(scenario.directions.inbound.first), toTime(inbound[0]), "HH:MM"],
    ["Last departure inbound", toTime(scenario.directions.inbound.last), toTime(inbound.at(-1)), "HH:MM"],
    ["Fleet requirement", scenario.fleet_required, route.fleet_plan.fleet_required, "vehicles at official authority"],
    ["Expected passenger wait", scenario.expected_wait, route.metrics.demand_weighted_expected_passenger_wait_minutes, "minutes"],
    ["Observed-demand SSE mismatch", scenario.mismatch, route.metrics.observed_demand_mismatch, "sum of directional squared share errors"],
    ["Pair trip-equivalent error", scenario.pair_te, route.te.pair, "same authoritative bucket authority"],
    ["Maximum bucket wait", scenario.maximum_bucket_wait, Math.max(route.access.outbound.selected_maximum_bucket_wait_minutes, route.access.inbound.selected_maximum_bucket_wait_minutes), "minutes"],
    ["P90 bucket wait", scenario.p90_bucket_wait, route.metrics.maximum_directional_p90_bucket_wait_minutes, "maximum directional P90, minutes"],
    ["Actual ServiceRegime count", scenario.service_regime_count, route.metrics.actual_service_regime_count, "uniform exact-headway runs"],
    ["Sustained headway level count", scenario.sustained_headway_level_count, route.metrics.total_directional_sustained_headway_level_count, "sum across directions"],
    ["Effective palette count", scenario.effective_palette_count, route.metrics.total_directional_effective_palette_count, "sum across directions"],
    ["Minimum actual headway", scenario.minimum_headway, Math.min(...gaps), "minutes"],
    ["Maximum actual headway", scenario.maximum_headway, Math.max(...gaps), "minutes"],
  ];
  sheet.getRange(`A1:D${rows.length}`).values = rows;
  addTable(sheet, `A1:D${rows.length}`, `Route${route.route_id}PComparison`);
  styleHeader(sheet, "A1:D1");
  sheet.getRange("B3:C6").format.numberFormat = "hh:mm";
  sheet.getRange("B8:C12").format.numberFormat = "0.000000";
  sheet.getRange(`D2:D${rows.length}`).format.wrapText = true;
  setColumns(sheet, { A: 34, B: 23, C: 23, D: 49 });
  sheet.freezePanes.freezeRows(1);
}

function buildFleetPlan(workbook, route) {
  const sheet = workbook.worksheets.add("Fleet_Plan");
  sheet.showGridLines = false;
  const rows = [["Vehicle", "Trip", "Direction", "Departure", "Arrival", "Next trip", "Connection layover (min)"]];
  for (const item of route.fleet_plan.assignments) rows.push([
    item.vehicle_id, item.trip_id, item.direction, toTime(item.departure), toTime(item.arrival),
    item.next_trip_id, item.connection_layover_minutes,
  ]);
  sheet.getRange(`A1:G${rows.length}`).values = rows;
  addTable(sheet, `A1:G${rows.length}`, `Route${route.route_id}PFleetPlan`);
  styleHeader(sheet, "A1:G1");
  sheet.getRange(`D2:E${rows.length}`).format.numberFormat = "hh:mm";
  setColumns(sheet, { A: 12, B: 18, C: 14, D: 13, E: 13, F: 18, G: 26 });
  sheet.freezePanes.freezeRows(1);
}

function buildRobustness(workbook, route) {
  const sheet = workbook.worksheets.add("Layover_Robustness");
  sheet.showGridLines = false;
  const official = route.layover_robustness.official;
  const sensitivity = route.layover_robustness.sensitivity;
  const rows = [
    ["Case", "Runtime min", "Minimum layover min", "Fleet ceiling", "Fleet required", "Fleet margin", "Timetable changed", "Trips shifted", "Min connection layover", "Median connection layover", "Max connection layover", "All connections pass", "Classification", "Authority", "Interpretation"],
    ["Official production authority", route.runtime_minutes, route.official_minimum_layover_minutes, route.fleet_ceiling, official.fleet_required, official.fleet_margin, "No", 0, official.minimum_connection_layover, official.median_connection_layover, official.maximum_connection_layover, official.all_connections_pass ? "Yes" : "No", "OFFICIAL_MINIMUM_LAYOVER_CERTIFIED", "Current V2 selected timetable", `Fresh exact fleet recertification: ${official.fleet_required}/${route.fleet_ceiling} vehicles.`],
    ["Static 10-minute sensitivity", route.runtime_minutes, sensitivity.minimum_layover_minutes, route.fleet_ceiling, sensitivity.fleet_required, sensitivity.fleet_margin, "No", sensitivity.departure_shifts, sensitivity.minimum_connection_layover, sensitivity.median_connection_layover, sensitivity.maximum_connection_layover, sensitivity.all_connections_pass ? "Yes" : "No", sensitivity.classification, "Same exact V2 timetable; diagnostic only", `Recomputed at 10 minutes with no departure shifts: ${sensitivity.fleet_required}/${route.fleet_ceiling} vehicles.`],
  ];
  sheet.getRange("A1:O3").values = rows;
  addTable(sheet, "A1:O3", "Route6PLayoverRobustness");
  styleHeader(sheet, "A1:O1");
  sheet.getRange("J2:J3").format.numberFormat = "0.0";
  sheet.getRange("M2:O3").format.wrapText = true;
  setColumns(sheet, { A: 28, B: 12, C: 20, D: 15, E: 15, F: 14, G: 19, H: 14, I: 22, J: 25, K: 22, L: 21, M: 37, N: 38, O: 54 });
  sheet.freezePanes.freezeRows(1);
}

async function buildRoute(route) {
  const workbook = Workbook.create();
  buildSummary(workbook, route); buildTimetable(workbook, route);
  buildServiceRegimes(workbook, route); buildDemandComparison(workbook, route);
  buildComparison(workbook, route); buildFleetPlan(workbook, route);
  if (route.route_id === "6") buildRobustness(workbook, route);
  const errors = await workbook.inspect({
    kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 300 }, summary: `Route ${route.route_id} formula error scan`,
  });
  if (/#[A-Z0-9/?]+!/.test(errors.ndjson)) throw new Error(`formula errors in Route ${route.route_id}`);
  const file = await SpreadsheetFile.exportXlsx(workbook);
  await file.save(path.join(outputDir, route.workbook_name));
}

async function verifyRoute(route, previewDir) {
  const input = await FileBlob.load(path.join(outputDir, route.workbook_name));
  const workbook = await SpreadsheetFile.importXlsx(input);
  const outRows = route.directions.outbound.exact_departures.length + 1;
  const inRows = route.directions.inbound.exact_departures.length + 1;
  const inspections = [
    { kind: "table", range: "Summary!A1:B35", include: "values,formulas", tableMaxRows: 35, tableMaxCols: 2 },
    { kind: "table", range: `Timetable!A1:D${outRows}`, include: "values,formulas", tableMaxRows: outRows, tableMaxCols: 4 },
    { kind: "table", range: `Timetable!F1:I${inRows}`, include: "values,formulas", tableMaxRows: inRows, tableMaxCols: 4 },
    { kind: "table", range: "Comparison!A1:D20", include: "values,formulas", tableMaxRows: 20, tableMaxCols: 4 },
    { kind: "table", range: `Fleet_Plan!A1:G${route.fleet_plan.assignments.length + 1}`, include: "values,formulas", tableMaxRows: route.fleet_plan.assignments.length + 1, tableMaxCols: 7 },
  ];
  if (route.route_id === "6") inspections.push({ kind: "table", range: "Layover_Robustness!A1:O3", include: "values,formulas", tableMaxRows: 3, tableMaxCols: 15 });
  for (const request of inspections) {
    const result = await workbook.inspect({ ...request, maxChars: 10000 });
    console.log(result.ndjson);
  }
  const errors = await workbook.inspect({
    kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 300 }, summary: `Route ${route.route_id} final formula error scan`,
  });
  console.log(errors.ndjson);
  if (/#[A-Z0-9/?]+!/.test(errors.ndjson)) throw new Error(`formula errors in Route ${route.route_id}`);
  await fs.mkdir(previewDir, { recursive: true });
  for (const sheetName of workbook.worksheets.items.map((sheet) => sheet.name)) {
    const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
    await fs.writeFile(
      path.join(previewDir, `route-${route.route_id}-${sheetName.replaceAll("_", "-")}.png`),
      new Uint8Array(await preview.arrayBuffer()),
    );
  }
}

if (args["verify-only"] === "true") {
  if (!args["preview-dir"]) throw new Error("--preview-dir is required for verification");
  for (const routeId of ["6", "10"]) await verifyRoute(data.routes[routeId], args["preview-dir"]);
} else {
  await fs.mkdir(outputDir, { recursive: true });
  for (const routeId of ["6", "10"]) await buildRoute(data.routes[routeId]);
}

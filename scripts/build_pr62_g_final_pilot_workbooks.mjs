import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const args = Object.fromEntries(
  process.argv.slice(2).map((value, index, all) =>
    value.startsWith("--") ? [value.slice(2), all[index + 1]] : ["", ""],
  ),
);
const dataPath = args.data;
const outputDir = args["output-dir"];
if (!dataPath || !outputDir) throw new Error("--data and --output-dir are required");
const data = JSON.parse(await fs.readFile(dataPath, "utf8"));
if (args["verify-only"] === "true") {
  const previewDir = args["preview-dir"];
  if (!previewDir) throw new Error("--preview-dir is required for verification");
  await fs.mkdir(previewDir, { recursive: true });
  for (const routeId of ["6", "10"]) {
    const route = data.routes[routeId];
    const input = await FileBlob.load(path.join(outputDir, route.workbook_name));
    const workbook = await SpreadsheetFile.importXlsx(input);
    const summary = await workbook.inspect({
      kind: "table",
      range: "Summary!A1:B24",
      include: "values,formulas",
      tableMaxRows: 24,
      tableMaxCols: 2,
    });
    console.log(summary.ndjson);
    const errors = await workbook.inspect({
      kind: "match",
      searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
      options: { useRegex: true, maxResults: 100 },
      summary: `Route ${routeId} final formula error scan`,
    });
    console.log(errors.ndjson);
    for (const sheetName of workbook.worksheets.items.map((sheet) => sheet.name)) {
      const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
      const safeName = sheetName.replaceAll("_", "-");
      await fs.writeFile(
        path.join(previewDir, `route-${routeId}-${safeName}.png`),
        new Uint8Array(await preview.arrayBuffer()),
      );
    }
  }
  process.exit(0);
}
await fs.mkdir(outputDir, { recursive: true });

const COLORS = {
  navy: "#17365D",
  blue: "#2F75B5",
  paleBlue: "#DDEBF7",
  paleGold: "#FFF2CC",
  paleGreen: "#E2F0D9",
  paleGray: "#F2F2F2",
  white: "#FFFFFF",
  text: "#1F2937",
  line: "#D9E2F3",
};

const toTime = (seconds) => seconds / 86400;
const titleFormat = {
  fill: COLORS.navy,
  font: { bold: true, color: COLORS.white, size: 16 },
  verticalAlignment: "center",
};
const headerFormat = {
  fill: COLORS.blue,
  font: { bold: true, color: COLORS.white },
  verticalAlignment: "center",
  wrapText: true,
  borders: { preset: "outside", style: "thin", color: COLORS.line },
};

function styleHeader(sheet, range) {
  sheet.getRange(range).format = headerFormat;
}

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

function buildSummary(workbook, route) {
  const sheet = workbook.worksheets.add("Summary");
  sheet.showGridLines = false;
  sheet.mergeCells("A1:B1");
  sheet.getRange("A1").values = [[`Route ${route.route_id} — Final Pilot Timetable`]];
  sheet.getRange("A1:B1").format = titleFormat;
  sheet.getRange("A1:B1").format.rowHeight = 30;
  const out = route.directions.outbound.exact_departures;
  const inbound = route.directions.inbound.exact_departures;
  const rows = [
    ["Route", route.route_id],
    ["Certification status", route.certification_status],
    ["Selected pair fingerprint", route.pair_fingerprint],
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
    ["Fleet required", route.metrics.fleet_required],
    ["Fleet spare", null],
    ["Expected passenger wait (minutes)", route.metrics.demand_weighted_expected_passenger_wait_minutes],
    ["Observed demand mismatch", route.metrics.observed_demand_mismatch],
    ["Actual ServiceRegime count", route.metrics.actual_service_regime_count],
    ["Maximum frequency jump", route.metrics.max_frequency_jump],
    ["Total frequency variation", route.metrics.total_frequency_variation],
    ["Selection source", route.selection_source],
    ["Settlement used", route.settlement_used],
  ];
  sheet.getRange(`A3:B${rows.length + 2}`).values = rows;
  sheet.getRange("B6").formulas = [["=B7+B8"]];
  sheet.getRange("B17").formulas = [["=B15-B16"]];
  sheet.getRange("A3:A24").format = { fill: COLORS.paleBlue, font: { bold: true, color: COLORS.text } };
  sheet.getRange("A3:B24").format.borders = {
    insideHorizontal: { style: "thin", color: COLORS.line },
    outside: { style: "thin", color: COLORS.line },
  };
  sheet.getRange("B9:B12").format.numberFormat = "hh:mm";
  sheet.getRange("B18:B19").format.numberFormat = "0.000000";
  sheet.getRange("B20").format.numberFormat = "0";
  sheet.getRange("B21:B22").format.numberFormat = "0.000000";
  sheet.getRange("B23").format.wrapText = true;
  setColumns(sheet, { A: 39, B: 92 });
  sheet.freezePanes.freezeRows(2);
  return sheet;
}

function timetableRows(direction) {
  const regimeByDeparture = new Map();
  for (const regime of direction.service_regimes) {
    for (const departure of regime.departures) regimeByDeparture.set(departure, regime.service_regime_id);
  }
  return direction.exact_departures.map((departure, index, values) => [
    index + 1,
    toTime(departure),
    regimeByDeparture.get(departure),
    index === 0 ? null : (departure - values[index - 1]) / 60,
  ]);
}

function buildTimetable(workbook, route) {
  const sheet = workbook.worksheets.add("Timetable");
  sheet.showGridLines = false;
  const headers = [["Sequence", "Departure", "ServiceRegime", "Headway" ]];
  const outRows = timetableRows(route.directions.outbound);
  const inRows = timetableRows(route.directions.inbound);
  sheet.getRange(`A1:D${outRows.length + 1}`).values = [...headers, ...outRows];
  sheet.getRange(`F1:I${inRows.length + 1}`).values = [...headers, ...inRows];
  addTable(sheet, `A1:D${outRows.length + 1}`, `Route${route.route_id}OutboundTimetable`);
  addTable(sheet, `F1:I${inRows.length + 1}`, `Route${route.route_id}InboundTimetable`);
  styleHeader(sheet, "A1:D1");
  styleHeader(sheet, "F1:I1");
  sheet.getRange(`B2:B${outRows.length + 1}`).format.numberFormat = "hh:mm";
  sheet.getRange(`G2:G${inRows.length + 1}`).format.numberFormat = "hh:mm";
  const fills = [COLORS.paleBlue, COLORS.paleGold, COLORS.paleGreen, COLORS.paleGray];
  for (const [startCol, rows] of [["A", outRows], ["F", inRows]]) {
    const endCol = startCol === "A" ? "D" : "I";
    let start = 2;
    let current = rows[0][2];
    let colorIndex = 0;
    for (let index = 1; index <= rows.length; index += 1) {
      if (index === rows.length || rows[index][2] !== current) {
        sheet.getRange(`${startCol}${start}:${endCol}${index + 1}`).format.fill = fills[colorIndex % fills.length];
        start = index + 2;
        current = index < rows.length ? rows[index][2] : current;
        colorIndex += 1;
      }
    }
  }
  setColumns(sheet, { A: 11, B: 13, C: 27, D: 11, E: 3, F: 11, G: 13, H: 27, I: 11 });
  sheet.freezePanes.freezeRows(1);
  return sheet;
}

function buildServiceRegimes(workbook, route) {
  const sheet = workbook.worksheets.add("ServiceRegimes");
  sheet.showGridLines = false;
  const rows = [["Direction", "ServiceRegime", "Start", "End", "Headway_minutes", "Trip_count", "DemandRegime_evidence"]];
  for (const direction of ["outbound", "inbound"]) {
    for (const regime of route.directions[direction].service_regimes) {
      rows.push([
        direction,
        regime.service_regime_id,
        toTime(regime.first_departure),
        toTime(regime.last_departure),
        regime.uniform_headway_minutes,
        regime.trip_count,
        regime.demand_regime_ids.join(", "),
      ]);
    }
  }
  sheet.getRange(`A1:G${rows.length}`).values = rows;
  addTable(sheet, `A1:G${rows.length}`, `Route${route.route_id}ServiceRegimes`);
  styleHeader(sheet, "A1:G1");
  sheet.getRange(`C2:D${rows.length}`).format.numberFormat = "hh:mm";
  setColumns(sheet, { A: 14, B: 27, C: 12, D: 12, E: 18, F: 13, G: 34 });
  sheet.freezePanes.freezeRows(1);
  return sheet;
}

function buildDemandComparison(workbook, route) {
  const sheet = workbook.worksheets.add("Demand_Comparison");
  sheet.showGridLines = false;
  const rows = [["Direction", "Start", "End", "Observed_demand", "Scenario_B_service_count", "Final_service_count", "Demand_share", "Scenario_B_service_share", "Final_service_share"]];
  for (const item of route.demand_rows) {
    rows.push([
      item.direction,
      toTime(item.start),
      toTime(item.end),
      item.observed_demand,
      item.scenario_b_service_count,
      item.final_service_count,
      item.demand_share,
      item.scenario_b_service_share,
      item.final_service_share,
    ]);
  }
  sheet.getRange(`A1:I${rows.length}`).values = rows;
  addTable(sheet, `A1:I${rows.length}`, `Route${route.route_id}DemandComparison`);
  styleHeader(sheet, "A1:I1");
  sheet.getRange(`B2:C${rows.length}`).format.numberFormat = "hh:mm";
  sheet.getRange(`D2:D${rows.length}`).format.numberFormat = "0.00";
  sheet.getRange(`G2:I${rows.length}`).format.numberFormat = "0.00%";
  sheet.getRange("K1:N1").values = [["Bucket", "Observed demand profile", "Scenario B/current service", "Final selected service"]];
  const formulas = route.demand_rows.map((_, index) => {
    const row = index + 2;
    return [
      `=A${row}&" "&TEXT(B${row},"hh:mm")`,
      `=G${row}`,
      `=H${row}`,
      `=I${row}`,
    ];
  });
  sheet.getRange(`K2:N${rows.length}`).formulas = formulas;
  styleHeader(sheet, "K1:N1");
  sheet.getRange(`L2:N${rows.length}`).format.numberFormat = "0.00%";
  const chart = sheet.charts.add("line", sheet.getRange(`K1:N${rows.length}`));
  chart.title = "Demand and service shares by frozen 30-minute bucket";
  chart.hasLegend = true;
  chart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 8 } };
  chart.yAxis = { numberFormatCode: "0%", min: 0 };
  chart.setPosition("K2", "T22");
  const noteStart = rows.length + 2;
  const noteEnd = rows.length + 3;
  sheet.getRange(`K${noteStart}:T${noteEnd}`).merge();
  sheet.getRange(`K${noteStart}`).values = [["Service shares are compared on one normalized scale; service is not expected to follow observed demand 1:1."]];
  sheet.getRange(`K${noteStart}:T${noteEnd}`).format = { fill: COLORS.paleGold, wrapText: true, font: { italic: true, color: COLORS.text } };
  setColumns(sheet, { A: 14, B: 11, C: 11, D: 18, E: 24, F: 19, G: 15, H: 24, I: 19, J: 3, K: 23, L: 23, M: 26, N: 22 });
  sheet.freezePanes.freezeRows(1);
  return sheet;
}

function buildComparison(workbook, route) {
  const sheet = workbook.worksheets.add("Comparison");
  sheet.showGridLines = false;
  const scenario = route.scenario_b;
  const out = route.directions.outbound.exact_departures;
  const inbound = route.directions.inbound.exact_departures;
  const rows = [
    ["Metric", "Scenario B/current", "Final", "Unit / interpretation"],
    ["Total trips", scenario.total_trips, out.length + inbound.length, "trips/day"],
    ["First departure outbound", toTime(scenario.directions.outbound.first), toTime(out[0]), "HH:MM"],
    ["Last departure outbound", toTime(scenario.directions.outbound.last), toTime(out.at(-1)), "HH:MM"],
    ["First departure inbound", toTime(scenario.directions.inbound.first), toTime(inbound[0]), "HH:MM"],
    ["Last departure inbound", toTime(scenario.directions.inbound.last), toTime(inbound.at(-1)), "HH:MM"],
    ["Fleet requirement", scenario.fleet_required, route.metrics.fleet_required, "vehicles at official authority"],
    ["Expected passenger wait", scenario.expected_wait, route.metrics.demand_weighted_expected_passenger_wait_minutes, "minutes; same frozen demand integration"],
    ["Demand mismatch", scenario.mismatch, route.metrics.observed_demand_mismatch, "sum of directional squared share errors"],
    ["ServiceRegime count", scenario.service_regime_count, route.metrics.actual_service_regime_count, "uniform exact-headway runs"],
    ["Minimum headway", scenario.minimum_headway, route.comparison.final_minimum_headway, "minutes"],
    ["Maximum headway", scenario.maximum_headway, route.comparison.final_maximum_headway, "minutes"],
  ];
  sheet.getRange(`A1:D${rows.length}`).values = rows;
  addTable(sheet, `A1:D${rows.length}`, `Route${route.route_id}Comparison`);
  styleHeader(sheet, "A1:D1");
  sheet.getRange("B3:C6").format.numberFormat = "hh:mm";
  sheet.getRange("B8:C9").format.numberFormat = "0.000000";
  setColumns(sheet, { A: 31, B: 23, C: 23, D: 47 });
  sheet.freezePanes.freezeRows(1);
  return sheet;
}

function buildFleetPlan(workbook, route) {
  const sheet = workbook.worksheets.add("Fleet_Plan");
  sheet.showGridLines = false;
  const rows = [["Vehicle", "Trip", "Direction", "Departure", "Arrival", "Next_trip", "Connection_layover_minutes"]];
  for (const item of route.fleet_plan.assignments) {
    rows.push([
      item.vehicle_id,
      item.trip_id,
      item.direction,
      toTime(item.departure),
      toTime(item.arrival),
      item.next_trip_id,
      item.connection_layover_minutes,
    ]);
  }
  sheet.getRange(`A1:G${rows.length}`).values = rows;
  addTable(sheet, `A1:G${rows.length}`, `Route${route.route_id}FleetPlan`);
  styleHeader(sheet, "A1:G1");
  sheet.getRange(`D2:E${rows.length}`).format.numberFormat = "hh:mm";
  setColumns(sheet, { A: 12, B: 18, C: 14, D: 13, E: 13, F: 18, G: 29 });
  sheet.freezePanes.freezeRows(1);
  return sheet;
}

function buildRobustness(workbook, route) {
  const sheet = workbook.worksheets.add("Layover_Robustness");
  sheet.showGridLines = false;
  const official = route.layover_robustness.official;
  const sensitivity = route.layover_robustness.sensitivity;
  const wait = route.metrics.demand_weighted_expected_passenger_wait_minutes;
  const mismatch = route.metrics.observed_demand_mismatch;
  const rows = [
    ["Case", "Runtime_min", "Minimum_layover_min", "Fleet_ceiling", "Fleet_required", "Fleet_margin", "Timetable_changed", "Trips_shifted", "Expected_wait", "Mismatch", "Min_connection_layover", "Median_connection_layover", "Max_connection_layover", "All_connections_pass", "Interpretation"],
    ["Official baseline", 70, 5, 20, 19, 1, "No", 0, wait, mismatch, official.minimum_connection_layover, official.median_connection_layover, official.maximum_connection_layover, "Yes", "Official production authority: 5-minute minimum layover; 19 vehicles required."],
    ["Sensitivity", 70, 10, 20, 20, 0, "No", 0, wait, mismatch, sensitivity.minimum_connection_layover, sensitivity.median_connection_layover, sensitivity.maximum_connection_layover, "Yes", "The selected timetable remains exactly feasible at 10-minute minimum layover, but uses the full 20-vehicle ceiling."],
  ];
  sheet.getRange("A1:O3").values = rows;
  addTable(sheet, "A1:O3", "Route6LayoverRobustness");
  styleHeader(sheet, "A1:O1");
  sheet.getRange("I2:J3").format.numberFormat = "0.000000";
  sheet.getRange("O2:O3").format.wrapText = true;
  setColumns(sheet, { A: 20, B: 13, C: 22, D: 15, E: 15, F: 14, G: 20, H: 14, I: 17, J: 14, K: 24, L: 27, M: 24, N: 23, O: 78 });
  sheet.freezePanes.freezeRows(1);
  return sheet;
}

async function buildRoute(route) {
  const workbook = Workbook.create();
  buildSummary(workbook, route);
  buildTimetable(workbook, route);
  buildServiceRegimes(workbook, route);
  buildDemandComparison(workbook, route);
  buildComparison(workbook, route);
  buildFleetPlan(workbook, route);
  if (route.route_id === "6") buildRobustness(workbook, route);
  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 100 },
    summary: `Route ${route.route_id} formula error scan`,
  });
  if (errors.ndjson.includes("#REF!") || errors.ndjson.includes("#DIV/0!")) {
    throw new Error(`formula errors in Route ${route.route_id} workbook`);
  }
  const file = await SpreadsheetFile.exportXlsx(workbook);
  await file.save(path.join(outputDir, route.workbook_name));
}

for (const routeId of ["6", "10"]) await buildRoute(data.routes[routeId]);

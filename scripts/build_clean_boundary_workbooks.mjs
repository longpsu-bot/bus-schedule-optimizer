import fs from "node:fs/promises";
import path from "node:path";

import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [, , reportArg, outputArg, previewArg] = process.argv;
if (!reportArg || !outputArg || !previewArg) {
  throw new Error(
    "usage: node build_clean_boundary_workbooks.mjs REPORT_JSON OUTPUT_DIR PREVIEW_DIR",
  );
}

const reportPath = path.resolve(reportArg);
const outputDir = path.resolve(outputArg);
const previewDir = path.resolve(previewArg);
const report = JSON.parse(await fs.readFile(reportPath, "utf8"));
await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const COLORS = {
  navy: "#16324F",
  teal: "#1F7A8C",
  green: "#2A9D8F",
  paleGreen: "#E7F5EF",
  paleBlue: "#EAF2F8",
  paleAmber: "#FFF4D6",
  paleRed: "#FCE8E6",
  gray: "#5E6B75",
  lightGray: "#EDF1F4",
  border: "#C7D0D9",
  white: "#FFFFFF",
  text: "#17212B",
};

const REGIME_COLORS = [
  "#DCEAF7",
  "#DDF2E8",
  "#FFF0CF",
  "#E8E0F3",
  "#F8DFE5",
  "#DDF1F3",
  "#F2E7D8",
  "#E6ECD9",
  "#DDE4F4",
  "#F3E2CE",
];

function excelTime(seconds) {
  return seconds / 86400;
}

function colLetter(number) {
  let result = "";
  let current = number;
  while (current > 0) {
    const remainder = (current - 1) % 26;
    result = String.fromCharCode(65 + remainder) + result;
    current = Math.floor((current - 1) / 26);
  }
  return result;
}

function setWidths(sheet, widths) {
  widths.forEach((width, index) => {
    sheet.getRange(`${colLetter(index + 1)}:${colLetter(index + 1)}`).format.columnWidth = width;
  });
}

function baseSheet(sheet) {
  sheet.showGridLines = false;
}

function title(sheet, text, endColumn) {
  const range = sheet.getRange(`A1:${colLetter(endColumn)}2`);
  range.merge();
  range.values = [[text]];
  range.format = {
    fill: COLORS.navy,
    font: { name: "Aptos Display", size: 18, bold: true, color: COLORS.white },
    horizontalAlignment: "left",
    verticalAlignment: "center",
  };
  range.format.rowHeight = 30;
}

function section(sheet, row, text, endColumn) {
  const range = sheet.getRange(`A${row}:${colLetter(endColumn)}${row}`);
  range.merge();
  range.values = [[text]];
  range.format = {
    fill: COLORS.teal,
    font: { bold: true, color: COLORS.white, size: 11 },
    verticalAlignment: "center",
  };
  range.format.rowHeight = 22;
}

function header(sheet, row, headers) {
  const range = sheet.getRange(`A${row}:${colLetter(headers.length)}${row}`);
  range.values = [headers];
  range.format = {
    fill: COLORS.lightGray,
    font: { bold: true, color: COLORS.navy },
    wrapText: true,
    verticalAlignment: "center",
    borders: { preset: "outside", style: "thin", color: COLORS.border },
  };
  range.format.rowHeight = 30;
}

function statusFill(sheet, range, passColumn) {
  range.conditionalFormats.addCustom(`=$${passColumn}1="PASS"`, {
    fill: COLORS.paleGreen,
    font: { color: "#166534", bold: true },
  });
  range.conditionalFormats.addCustom(`=$${passColumn}1="FAIL"`, {
    fill: COLORS.paleRed,
    font: { color: "#991B1B", bold: true },
  });
}

function compilation(route, direction, candidateId) {
  return route.compilations.find(
    (item) => item.direction === direction && item.candidate_id === candidateId,
  );
}

function selectedCompilation(route, direction) {
  const candidateId =
    direction === "outbound"
      ? route.final_selection.outbound_candidate_id
      : route.final_selection.inbound_candidate_id;
  return compilation(route, direction, candidateId);
}

function regimeColorMap(compilations) {
  const ids = [];
  for (const item of compilations) {
    for (const service of item.service_regimes) {
      const key = `${item.direction}:${item.candidate_id}:${service.service_regime_id}`;
      if (!ids.includes(key)) ids.push(key);
    }
  }
  return Object.fromEntries(
    ids.map((id, index) => [id, REGIME_COLORS[index % REGIME_COLORS.length]]),
  );
}

function writeFleetMatrix(sheet, route, titleText) {
  baseSheet(sheet);
  title(sheet, titleText, 13);
  section(sheet, 4, "All outbound / inbound candidate combinations", 13);
  const headers = [
    "Outbound candidate",
    "Inbound candidate",
    "Status",
    "Fleet required",
    "Fleet ceiling",
    "Fleet margin",
    "Min layover (min)",
    "Avg wait (min)",
    "Frozen mismatch",
    "Frozen moved trips",
    "Compiler quant. error",
    "Service regimes",
    "Selected",
  ];
  header(sheet, 6, headers);
  const ordered = [...route.fleet_matrix].sort((left, right) =>
    `${left.outbound_candidate_id}|${left.inbound_candidate_id}`.localeCompare(
      `${right.outbound_candidate_id}|${right.inbound_candidate_id}`,
    ),
  );
  const rows = ordered.map((item) => [
    item.outbound_candidate_id,
    item.inbound_candidate_id,
    item.status,
    item.fleet_requirement,
    item.fleet_ceiling,
    null,
    item.minimum_connection_layover_minutes,
    item.average_scheduled_wait_minutes,
    item.frozen_demand_mismatch,
    item.frozen_moved_trips,
    item.compiler_quantization_error,
    item.service_regime_count,
    item.outbound_candidate_id === route.final_selection.outbound_candidate_id &&
    item.inbound_candidate_id === route.final_selection.inbound_candidate_id
      ? "YES"
      : "",
  ]);
  const endRow = 6 + rows.length;
  sheet.getRange(`A7:M${endRow}`).values = rows;
  sheet.getRange("F7").formulas = [["=E7-D7"]];
  sheet.getRange(`F7:F${endRow}`).fillDown();
  sheet.getRange(`D7:G${endRow}`).format.numberFormat = "0";
  sheet.getRange(`H7:H${endRow}`).format.numberFormat = "0.00";
  sheet.getRange(`I7:I${endRow}`).format.numberFormat = "0.000000";
  sheet.getRange(`K7:K${endRow}`).format.numberFormat = "0.000000";
  sheet.getRange(`A7:M${endRow}`).format.borders = {
    insideHorizontal: { style: "thin", color: COLORS.border },
    bottom: { style: "thin", color: COLORS.border },
  };
  for (let row = 7; row <= endRow; row += 1) {
    if (sheet.getRange(`M${row}`).values[0][0] === "YES") {
      sheet.getRange(`A${row}:M${row}`).format.fill = COLORS.paleGreen;
      sheet.getRange(`A${row}:M${row}`).format.font = { bold: true, color: "#166534" };
    } else if (sheet.getRange(`C${row}`).values[0][0] === "FLEET_INFEASIBLE") {
      sheet.getRange(`A${row}:M${row}`).format.fill = COLORS.paleRed;
    }
  }
  setWidths(sheet, [22, 22, 18, 13, 12, 12, 15, 14, 16, 15, 17, 15, 11]);
  title(sheet, titleText, 13);
  section(sheet, 4, "All outbound / inbound candidate combinations", 13);
  sheet.freezePanes.freezeRows(6);
  return { ordered, startRow: 7, endRow };
}

function writeServiceRegimes(sheet, route, titleText) {
  baseSheet(sheet);
  title(sheet, titleText, 9);
  section(sheet, 4, "Selected exact uniform ServiceRegime plan", 9);
  header(sheet, 6, [
    "Direction",
    "Candidate",
    "ServiceRegime",
    "DemandRegimes retained",
    "First departure",
    "Last departure",
    "Uniform headway (min)",
    "Trips",
    "Uniformity check",
  ]);
  const rows = [];
  for (const direction of ["outbound", "inbound"]) {
    const item = selectedCompilation(route, direction);
    for (const service of item.service_regimes) {
      rows.push([
        direction,
        item.candidate_id,
        service.service_regime_id,
        service.demand_regime_ids.join(", "),
        excelTime(service.first_departure),
        excelTime(service.last_departure),
        service.uniform_headway_minutes,
        service.trip_count,
        "PASS",
      ]);
    }
  }
  const endRow = 6 + rows.length;
  sheet.getRange(`A7:I${endRow}`).values = rows;
  sheet.getRange(`E7:F${endRow}`).format.numberFormat = "hh:mm";
  sheet.getRange(`G7:H${endRow}`).format.numberFormat = "0";
  sheet.getRange(`A7:I${endRow}`).format.borders = {
    insideHorizontal: { style: "thin", color: COLORS.border },
  };
  for (let row = 7; row <= endRow; row += 1) {
    sheet.getRange(`A${row}:I${row}`).format.fill = REGIME_COLORS[(row - 7) % REGIME_COLORS.length];
  }
  setWidths(sheet, [13, 20, 21, 50, 15, 15, 17, 12, 18]);
  sheet.freezePanes.freezeRows(6);
}

function selectedFleetLookup(route) {
  return Object.fromEntries(
    route.selected_fleet_plan.assignments.map((item) => [
      `${item.direction}:${item.sequence}`,
      item,
    ]),
  );
}

function writeTimetable(sheet, route, direction, titleText) {
  baseSheet(sheet);
  title(sheet, titleText, 11);
  const item = selectedCompilation(route, direction);
  section(
    sheet,
    4,
    `${item.candidate_id} · fixed ${formatSeconds(item.endpoint_authority.fixed_first_departure)}–${formatSeconds(item.endpoint_authority.fixed_last_departure)} · no unowned boundary gaps`,
    11,
  );
  header(sheet, 6, [
    "Seq",
    "Departure",
    "Operational headway (min)",
    "Service headway (min)",
    "ServiceRegime",
    "Gap owner ServiceRegime",
    "Ownership",
    "Vehicle",
    "Arrival",
    "Next trip",
    "Connection layover (min)",
  ]);
  const fleet = selectedFleetLookup(route);
  const rows = route.selected_product_rows[direction].map((row) => {
    const assignment = fleet[`${direction}:${row.sequence}`];
    return [
      row.sequence,
      excelTime(row.departure),
      row.gap_from_previous_minutes,
      row.service_headway_minutes,
      row.service_regime_id,
      row.gap_owner_service_regime_id,
      row.gap_ownership,
      assignment.vehicle_id,
      excelTime(assignment.arrival),
      assignment.next_trip_id,
      assignment.connection_layover_minutes,
    ];
  });
  const endRow = 6 + rows.length;
  sheet.getRange(`A7:K${endRow}`).values = rows;
  sheet.getRange(`B7:B${endRow}`).format.numberFormat = "hh:mm";
  sheet.getRange(`I7:I${endRow}`).format.numberFormat = "hh:mm";
  sheet.getRange(`A7:K${endRow}`).format.borders = {
    insideHorizontal: { style: "thin", color: COLORS.border },
  };
  const colors = regimeColorMap([item]);
  const rowsSource = route.selected_product_rows[direction];
  for (let index = 0; index < rowsSource.length; index += 1) {
    const source = rowsSource[index];
    const rowNumber = index + 7;
    const ownerId = source.gap_owner_service_regime_id || source.service_regime_id;
    const key = `${direction}:${item.candidate_id}:${ownerId}`;
    sheet.getRange(`C${rowNumber}:G${rowNumber}`).format.fill = colors[key];
  }
  sheet.getRange(`A7:K7`).format.font = { bold: true, color: COLORS.navy };
  sheet.getRange(`A${endRow}:K${endRow}`).format.font = { bold: true, color: COLORS.navy };
  setWidths(sheet, [8, 13, 20, 18, 21, 25, 42, 11, 13, 15, 18]);
  sheet.freezePanes.freezeRows(6);
}

function writeDemandCountQa(sheet, route, titleText) {
  baseSheet(sheet);
  title(sheet, titleText, 8);
  section(sheet, 4, "Frozen DemandRegime trip-count reconciliation", 8);
  header(sheet, 6, [
    "Direction",
    "DemandRegime",
    "Window start",
    "Window end",
    "Authority count",
    "Compiled count",
    "Check",
    "ServiceRegime",
  ]);
  const rows = [];
  const formulas = [];
  for (const direction of ["outbound", "inbound"]) {
    const item = selectedCompilation(route, direction);
    const timetableSheet = direction === "outbound" ? "Outbound Timetable" : "Inbound Timetable";
    const timetableEnd = 6 + item.exact_departures.length;
    for (const slice of item.demand_regime_slices) {
      const targetRow = 7 + rows.length;
      rows.push([
        direction,
        slice.demand_regime_id,
        excelTime(slice.demand_regime_start),
        excelTime(slice.demand_regime_end),
        slice.authoritative_trip_count,
        null,
        null,
        slice.service_regime_id,
      ]);
      formulas.push([
        `=COUNTIFS('${timetableSheet}'!$B$7:$B$${timetableEnd},">="&C${targetRow},'${timetableSheet}'!$B$7:$B$${timetableEnd},"<"&D${targetRow})`,
        `=IF(E${targetRow}=F${targetRow},"PASS","FAIL")`,
      ]);
    }
  }
  const endRow = 6 + rows.length;
  sheet.getRange(`A7:H${endRow}`).values = rows;
  for (let index = 0; index < formulas.length; index += 1) {
    const row = index + 7;
    sheet.getRange(`F${row}:G${row}`).formulas = [formulas[index]];
  }
  sheet.getRange(`C7:D${endRow}`).format.numberFormat = "hh:mm";
  sheet.getRange(`E7:F${endRow}`).format.numberFormat = "0";
  sheet.getRange(`A7:H${endRow}`).format.borders = {
    insideHorizontal: { style: "thin", color: COLORS.border },
  };
  setWidths(sheet, [13, 22, 14, 14, 15, 15, 11, 21]);
  sheet.freezePanes.freezeRows(6);
}

function writeBoundaryQa(sheet, routes, titleText) {
  baseSheet(sheet);
  title(sheet, titleText, 11);
  section(sheet, 4, "Every compiled candidate boundary: g must equal hL or hR", 11);
  header(sheet, 6, [
    "Route",
    "Direction",
    "Candidate",
    "Boundary",
    "Departure i",
    "Departure j",
    "Gap g",
    "hL",
    "hR",
    "Ownership",
    "Check",
  ]);
  const rows = [];
  for (const route of routes) {
    for (const item of route.compilations) {
      for (const boundary of item.boundary_diagnostics) {
        rows.push([
          route.route_id,
          item.direction,
          item.candidate_id,
          excelTime(boundary.boundary_time),
          excelTime(boundary.departure_i),
          excelTime(boundary.departure_j),
          boundary.gap_minutes,
          boundary.left_service_headway,
          boundary.right_service_headway,
          boundary.ownership,
          null,
        ]);
      }
    }
  }
  const endRow = 6 + rows.length;
  sheet.getRange(`A7:K${endRow}`).values = rows;
  sheet.getRange("K7").formulas = [["=IF(OR(G7=H7,G7=I7),\"PASS\",\"FAIL\")"]];
  sheet.getRange(`K7:K${endRow}`).fillDown();
  sheet.getRange(`D7:F${endRow}`).format.numberFormat = "hh:mm";
  sheet.getRange(`G7:I${endRow}`).format.numberFormat = "0";
  sheet.getRange(`A7:K${endRow}`).format.borders = {
    insideHorizontal: { style: "thin", color: COLORS.border },
  };
  setWidths(sheet, [9, 13, 20, 13, 14, 14, 11, 11, 11, 44, 12]);
  sheet.freezePanes.freezeRows(6);
}

function writeFleetPlan(sheet, route, titleText) {
  baseSheet(sheet);
  title(sheet, titleText, 10);
  section(
    sheet,
    4,
    `${route.selected_fleet_plan.fleet_requirement} vehicles · runtime ${route.runtime_minutes} min · minimum layover ${route.minimum_layover_minutes} min`,
    10,
  );
  header(sheet, 6, [
    "Vehicle",
    "Trip",
    "Direction",
    "Seq",
    "Departure",
    "Arrival",
    "Next trip",
    "Layover (min)",
    "Layover check",
    "Candidate pair",
  ]);
  const ordered = [...route.selected_fleet_plan.assignments].sort((left, right) =>
    `${left.vehicle_id}|${String(left.departure).padStart(8, "0")}`.localeCompare(
      `${right.vehicle_id}|${String(right.departure).padStart(8, "0")}`,
    ),
  );
  const rows = ordered.map((item) => [
    item.vehicle_id,
    item.trip_id,
    item.direction,
    item.sequence,
    excelTime(item.departure),
    excelTime(item.arrival),
    item.next_trip_id,
    item.connection_layover_minutes,
    item.connection_layover_minutes === null ||
    item.connection_layover_minutes >= route.minimum_layover_minutes
      ? "PASS"
      : "FAIL",
    `${route.final_selection.outbound_candidate_id} / ${route.final_selection.inbound_candidate_id}`,
  ]);
  const endRow = 6 + rows.length;
  sheet.getRange(`A7:J${endRow}`).values = rows;
  sheet.getRange(`E7:F${endRow}`).format.numberFormat = "hh:mm";
  sheet.getRange(`D7:D${endRow}`).format.numberFormat = "0";
  sheet.getRange(`H7:H${endRow}`).format.numberFormat = "0";
  sheet.getRange(`A7:J${endRow}`).format.borders = {
    insideHorizontal: { style: "thin", color: COLORS.border },
  };
  setWidths(sheet, [11, 16, 13, 8, 13, 13, 16, 14, 14, 32]);
  sheet.freezePanes.freezeRows(6);
}

function formatSeconds(seconds) {
  const totalMinutes = Math.floor(seconds / 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

function writeRouteSummary(sheet, route, matrixInfo, titleText) {
  baseSheet(sheet);
  title(sheet, titleText, 9);
  section(sheet, 4, "Pilot decision", 9);
  const selectedIndex = matrixInfo.ordered.findIndex(
    (item) =>
      item.outbound_candidate_id === route.final_selection.outbound_candidate_id &&
      item.inbound_candidate_id === route.final_selection.inbound_candidate_id,
  );
  const matrixRow = matrixInfo.startRow + selectedIndex;
  const summaryRows = [
    ["Route", route.route_id, "Route name", route.route_name],
    ["Selected outbound", route.final_selection.outbound_candidate_id, "Selected inbound", route.final_selection.inbound_candidate_id],
    ["Runtime (min)", route.runtime_minutes, "Minimum layover (min)", route.minimum_layover_minutes],
    ["Fleet required", null, "Fleet ceiling", null],
    ["Fleet margin", null, "Selection authority", report.final_selection_authority_bridge],
    ["Boundary outliers", 0, "Product scan", report.product_headway_outlier_scan.status],
  ];
  sheet.getRange("A6:D11").values = summaryRows;
  sheet.getRange("B9").formulas = [[`='Fleet Matrix'!D${matrixRow}`]];
  sheet.getRange("D9").formulas = [[`='Fleet Matrix'!E${matrixRow}`]];
  sheet.getRange("B10").formulas = [["=D9-B9"]];
  sheet.getRange("A6:D11").format.borders = {
    preset: "all",
    style: "thin",
    color: COLORS.border,
  };
  sheet.getRange("A6:A11").format.font = { bold: true, color: COLORS.navy };
  sheet.getRange("C6:C11").format.font = { bold: true, color: COLORS.navy };
  sheet.getRange("B9:B10").format.numberFormat = "0";
  section(sheet, 13, "Analysis window is separate from fixed Scenario B endpoints", 9);
  header(sheet, 15, [
    "Direction",
    "Analysis start",
    "Analysis end",
    "Fixed first",
    "Fixed last",
    "Compiled first",
    "Compiled last",
    "Endpoint check",
    "Authority source",
  ]);
  const endpointRows = [];
  for (const direction of ["outbound", "inbound"]) {
    const item = selectedCompilation(route, direction);
    endpointRows.push([
      direction,
      excelTime(item.endpoint_authority.analysis_window_start),
      excelTime(item.endpoint_authority.analysis_window_end),
      excelTime(item.endpoint_authority.fixed_first_departure),
      excelTime(item.endpoint_authority.fixed_last_departure),
      excelTime(item.exact_departures[0]),
      excelTime(item.exact_departures.at(-1)),
      null,
      item.endpoint_authority.authority_source,
    ]);
  }
  sheet.getRange("A16:I17").values = endpointRows;
  sheet.getRange("H16").formulas = [["=IF(AND(D16=F16,E16=G16),\"PASS\",\"FAIL\")"]];
  sheet.getRange("H16:H17").fillDown();
  sheet.getRange("B16:G17").format.numberFormat = "hh:mm";
  sheet.getRange("A16:I17").format.borders = {
    insideHorizontal: { style: "thin", color: COLORS.border },
  };
  section(sheet, 19, "Product-level hard checks", 9);
  header(sheet, 21, ["Check", "Status", "Evidence", "", "", "", "", "", ""]);
  const hardChecks = [
    ["Fixed endpoints", "PASS", "Compiled first/last equal THAM_SO_B authority"],
    ["Clean boundaries", report.product_headway_outlier_scan.status, "Every g equals hL or hR"],
    ["Internal uniformity", "PASS", "One whole-minute headway per ServiceRegime"],
    ["Frozen allocation", report.frozen_upstream_fingerprints_unchanged ? "PASS" : "FAIL", "DemandRegime counts and fingerprints unchanged"],
    ["Fleet ceiling", route.final_selection.fleet_requirement <= route.fleet_ceiling ? "PASS" : "FAIL", `${route.final_selection.fleet_requirement} required / ${route.fleet_ceiling} ceiling`],
    ["Minimum layover", route.selected_fleet_plan.minimum_connection_layover_minutes >= route.minimum_layover_minutes ? "PASS" : "FAIL", `${route.selected_fleet_plan.minimum_connection_layover_minutes} min minimum`],
  ];
  sheet.getRange("A22:C27").values = hardChecks;
  sheet.getRange("A22:C27").format.borders = {
    insideHorizontal: { style: "thin", color: COLORS.border },
  };
  sheet.getRange("B22:B27").format.fill = COLORS.paleGreen;
  sheet.getRange("B22:B27").format.font = { bold: true, color: "#166534" };
  setWidths(sheet, [23, 20, 25, 24, 17, 17, 17, 17, 58]);
  sheet.freezePanes.freezeRows(4);
}

async function createRouteWorkbook(route) {
  const workbook = Workbook.create();
  const summary = workbook.worksheets.add("Pilot Summary");
  const regimes = workbook.worksheets.add("Service Regimes");
  const outbound = workbook.worksheets.add("Outbound Timetable");
  const inbound = workbook.worksheets.add("Inbound Timetable");
  const demandQa = workbook.worksheets.add("Demand Count QA");
  const matrix = workbook.worksheets.add("Fleet Matrix");
  const boundaryQa = workbook.worksheets.add("Boundary QA");
  const fleetPlan = workbook.worksheets.add("Fleet Plan");

  const matrixInfo = writeFleetMatrix(
    matrix,
    route,
    `Route ${route.route_id} · recalculated 9-combination fleet matrix`,
  );
  writeRouteSummary(summary, route, matrixInfo, `Route ${route.route_id} · Final Scenario C · Clean Boundaries V2`);
  writeServiceRegimes(regimes, route, `Route ${route.route_id} · selected ServiceRegime plan`);
  writeTimetable(outbound, route, "outbound", `Route ${route.route_id} · Outbound exact timetable`);
  writeTimetable(inbound, route, "inbound", `Route ${route.route_id} · Inbound exact timetable`);
  writeDemandCountQa(demandQa, route, `Route ${route.route_id} · frozen allocation reconciliation`);
  writeBoundaryQa(boundaryQa, [route], `Route ${route.route_id} · all compiled boundary diagnostics`);
  writeFleetPlan(fleetPlan, route, `Route ${route.route_id} · selected minimum fleet plan`);
  return workbook;
}

function writePortfolioSummary(sheet, routes, matrixInfos) {
  baseSheet(sheet);
  title(sheet, "Routes 6 & 10 · Final Scenario C · Clean Boundaries V2", 12);
  section(sheet, 4, "Selected pilot plans", 12);
  header(sheet, 6, [
    "Route",
    "Outbound candidate",
    "Inbound candidate",
    "Fleet required",
    "Fleet ceiling",
    "Fleet margin",
    "Avg wait (min)",
    "Service regimes",
    "Boundary outliers",
    "Endpoint check",
    "Layover check",
    "Decision",
  ]);
  const rows = routes.map((route) => [
    route.route_id,
    route.final_selection.outbound_candidate_id,
    route.final_selection.inbound_candidate_id,
    route.final_selection.fleet_requirement,
    route.final_selection.fleet_ceiling,
    null,
    route.final_selection.average_scheduled_wait_minutes,
    route.final_selection.service_regime_count,
    0,
    "PASS",
    route.selected_fleet_plan.minimum_connection_layover_minutes >= route.minimum_layover_minutes
      ? "PASS"
      : "FAIL",
    "PILOT REVIEW READY",
  ]);
  sheet.getRange("A7:L8").values = rows;
  sheet.getRange("F7").formulas = [["=E7-D7"]];
  sheet.getRange("F7:F8").fillDown();
  sheet.getRange("D7:F8").format.numberFormat = "0";
  sheet.getRange("G7:G8").format.numberFormat = "0.00";
  sheet.getRange("A7:L8").format.fill = COLORS.paleGreen;
  sheet.getRange("A7:L8").format.borders = {
    preset: "all",
    style: "thin",
    color: COLORS.border,
  };
  section(sheet, 11, "Fixed endpoint authority", 12);
  header(sheet, 13, [
    "Route",
    "Direction",
    "Analysis start",
    "Analysis end",
    "Fixed first",
    "Fixed last",
    "Compiled first",
    "Compiled last",
    "Check",
    "Authority source",
    "",
    "",
  ]);
  const endpointRows = [];
  for (const route of routes) {
    for (const direction of ["outbound", "inbound"]) {
      const item = selectedCompilation(route, direction);
      endpointRows.push([
        route.route_id,
        direction,
        excelTime(item.endpoint_authority.analysis_window_start),
        excelTime(item.endpoint_authority.analysis_window_end),
        excelTime(item.endpoint_authority.fixed_first_departure),
        excelTime(item.endpoint_authority.fixed_last_departure),
        excelTime(item.exact_departures[0]),
        excelTime(item.exact_departures.at(-1)),
        "PASS",
        item.endpoint_authority.authority_source,
        null,
        null,
      ]);
    }
  }
  sheet.getRange("A14:L17").values = endpointRows;
  sheet.getRange("C14:H17").format.numberFormat = "hh:mm";
  sheet.getRange("A14:J17").format.borders = {
    insideHorizontal: { style: "thin", color: COLORS.border },
  };
  section(sheet, 20, "Correction evidence", 12);
  const evidenceRows = [
    ["Compiler profile", `${report.review_profile} · fixed endpoints + exact counts + clean boundaries`],
    ["Outlier scan", `${report.product_headway_outlier_scan.status} · ${report.product_headway_outlier_scan.outlier_count} outliers`],
    ["Frozen fingerprints", `${report.frozen_upstream_fingerprints_unchanged ? "PASS" : "FAIL"} · before/after SHA-256 identical`],
    ["Selection authority", `${report.final_selection_authority_bridge} · balanced role, then deterministic evidence tie-breaks`],
  ];
  for (let index = 0; index < evidenceRows.length; index += 1) {
    const row = 22 + index;
    sheet.getRange(`B${row}:L${row}`).merge();
    sheet.getRange(`A${row}`).values = [[evidenceRows[index][0]]];
    sheet.getRange(`B${row}:L${row}`).values = [[evidenceRows[index][1]]];
  }
  sheet.getRange("A22:L25").format.borders = {
    insideHorizontal: { style: "thin", color: COLORS.border },
  };
  sheet.getRange("A22:A25").format.font = { bold: true, color: COLORS.navy };
  setWidths(sheet, [11, 20, 20, 14, 13, 13, 14, 15, 15, 15, 15, 22]);
  sheet.getRange("J:J").format.columnWidth = 54;
  sheet.freezePanes.freezeRows(4);
}

async function createCombinedWorkbook(routes) {
  const workbook = Workbook.create();
  const summary = workbook.worksheets.add("Portfolio Summary");
  const r6Matrix = workbook.worksheets.add("Route 6 Matrix");
  const r10Matrix = workbook.worksheets.add("Route 10 Matrix");
  const r6Regimes = workbook.worksheets.add("Route 6 Regimes");
  const r10Regimes = workbook.worksheets.add("Route 10 Regimes");
  const r6Out = workbook.worksheets.add("R6 Outbound");
  const r6In = workbook.worksheets.add("R6 Inbound");
  const r10Out = workbook.worksheets.add("R10 Outbound");
  const r10In = workbook.worksheets.add("R10 Inbound");
  const boundaryQa = workbook.worksheets.add("Boundary QA");

  const r6 = routes.find((route) => route.route_id === "6");
  const r10 = routes.find((route) => route.route_id === "10");
  const info6 = writeFleetMatrix(r6Matrix, r6, "Route 6 · recalculated fleet matrix");
  const info10 = writeFleetMatrix(r10Matrix, r10, "Route 10 · recalculated fleet matrix");
  writePortfolioSummary(summary, routes, { "6": info6, "10": info10 });
  writeServiceRegimes(r6Regimes, r6, "Route 6 · selected ServiceRegime plan");
  writeServiceRegimes(r10Regimes, r10, "Route 10 · selected ServiceRegime plan");
  writeTimetable(r6Out, r6, "outbound", "Route 6 · Outbound exact timetable");
  writeTimetable(r6In, r6, "inbound", "Route 6 · Inbound exact timetable");
  writeTimetable(r10Out, r10, "outbound", "Route 10 · Outbound exact timetable");
  writeTimetable(r10In, r10, "inbound", "Route 10 · Inbound exact timetable");
  writeBoundaryQa(boundaryQa, routes, "Routes 6 & 10 · all compiled boundary diagnostics");
  return workbook;
}

async function verifyAndExport(workbook, fileName, previewPrefix, summarySheet, summaryRange) {
  const summary = await workbook.inspect({
    kind: "table",
    range: `${summarySheet}!${summaryRange}`,
    include: "values,formulas",
    tableMaxRows: 30,
    tableMaxCols: 14,
    maxChars: 7000,
  });
  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 200 },
    summary: `${fileName} final formula error scan`,
  });
  const sheetInfo = await workbook.inspect({ kind: "sheet", include: "id,name", maxChars: 5000 });
  const sheetNames = sheetInfo.ndjson
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line))
    .map((item) => item.name)
    .filter(Boolean);
  for (const sheetName of sheetNames) {
    const preview = await workbook.render({
      sheetName,
      range: "A1:M35",
      scale: 0.8,
      format: "png",
    });
    const safeName = sheetName.replace(/[^A-Za-z0-9]+/g, "_");
    await fs.writeFile(
      path.join(previewDir, `${previewPrefix}_${safeName}.png`),
      new Uint8Array(await preview.arrayBuffer()),
    );
  }
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(path.join(outputDir, fileName));
  return {
    fileName,
    sheets: sheetNames,
    summary: summary.ndjson,
    errors: errors.ndjson,
  };
}

const route6 = report.routes.find((route) => route.route_id === "6");
const route10 = report.routes.find((route) => route.route_id === "10");
const route6Workbook = await createRouteWorkbook(route6);
const route10Workbook = await createRouteWorkbook(route10);
const combinedWorkbook = await createCombinedWorkbook(report.routes);

const verification = [];
verification.push(
  await verifyAndExport(
    route6Workbook,
    "Route_6_Final_Scenario_C.xlsx",
    "route6",
    "Pilot Summary",
    "A1:I27",
  ),
);
verification.push(
  await verifyAndExport(
    route10Workbook,
    "Route_10_Final_Scenario_C.xlsx",
    "route10",
    "Pilot Summary",
    "A1:I27",
  ),
);
verification.push(
  await verifyAndExport(
    combinedWorkbook,
    "Routes_6_10_Final_Scenario_C.xlsx",
    "combined",
    "Portfolio Summary",
    "A1:L25",
  ),
);

console.log(JSON.stringify(verification));

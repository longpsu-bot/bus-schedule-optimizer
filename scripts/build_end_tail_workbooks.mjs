import fs from "node:fs/promises";
import path from "node:path";

import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [, , reportArg, priorReportArg, outputArg, previewArg] = process.argv;
if (!reportArg || !priorReportArg || !outputArg || !previewArg) {
  throw new Error(
    "usage: node build_end_tail_workbooks.mjs REPORT_JSON PRIOR_REPORT_JSON OUTPUT_DIR PREVIEW_DIR",
  );
}

const report = JSON.parse(await fs.readFile(path.resolve(reportArg), "utf8"));
const priorReport = JSON.parse(await fs.readFile(path.resolve(priorReportArg), "utf8"));
const outputDir = path.resolve(outputArg);
const previewDir = path.resolve(previewArg);
await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const COLORS = {
  navy: "#16324F",
  teal: "#1F7A8C",
  green: "#2A9D8F",
  amber: "#D99000",
  red: "#B42318",
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
  range.format.rowHeight = 34;
}

function selectedDirectionCandidate(route, direction, candidateId) {
  const directionData = route.directions.find((item) => item.direction === direction);
  return directionData.selected_candidates.find((item) => item.candidate_id === candidateId);
}

function priorRoute(routeId) {
  return priorReport.routes.find((item) => item.route_id === routeId);
}

function priorCompilation(routeId, direction, candidateId) {
  return priorRoute(routeId).compilations.find(
    (item) => item.direction === direction && item.candidate_id === candidateId,
  );
}

function directionData(route, direction) {
  return route.directions.find((item) => item.direction === direction);
}

function beforeAfter(route, direction, candidateId) {
  return directionData(route, direction).before_after.find(
    (item) => item.candidate_id === candidateId,
  );
}

function serviceForDeparture(compilation, departure) {
  return compilation.service_regimes.find((service) => service.departures.includes(departure));
}

function compactOwnership(value) {
  if (value === "MERGED_EQUAL_HEADWAY_SERVICE_REGIME") return "MERGED";
  if (value === "LEFT_SERVICE_REGIME") return "LEFT";
  if (value === "RIGHT_SERVICE_REGIME") return "RIGHT";
  return value;
}

function writeSummary(sheet, route, prior) {
  baseSheet(sheet);
  title(sheet, `Route ${route.route_id} · Tail-Aware End Settlement V3 · Human Review`, 10);
  section(sheet, 4, "Pilot status — not final authority", 10);
  const priorSelection = prior.final_selection;
  const currentSelection = route.final_selection;
  sheet.getRange("A6:D13").values = [
    ["Route", route.route_id, "Route name", route.route_name],
    ["Authority", report.authority_status, "Architecture", report.review_profile],
    ["V2 selected pair", `${priorSelection.outbound_candidate_id} / ${priorSelection.inbound_candidate_id}`, "V3 selected pair", `${currentSelection.outbound_candidate_id} / ${currentSelection.inbound_candidate_id}`],
    ["V2 fleet required", priorSelection.fleet_requirement, "V3 fleet required", currentSelection.fleet_requirement],
    ["Fleet delta", null, "Fleet ceiling", route.fleet_ceiling],
    ["Compiled candidates", 6, "Fleet combinations", route.candidate_pair_count],
    ["Headway outliers", report.pilot_totals.serialized_headway_outliers, "Frozen artifacts", report.frozen_prior_artifacts_unchanged ? "PASS" : "FAIL"],
    ["Review decision", "HUMAN REVIEW REQUIRED", "Promotion", "NOT FINAL"],
  ];
  sheet.getRange("B10").formulas = [["=D9-B9"]];
  sheet.getRange("A6:D13").format.borders = { preset: "all", style: "thin", color: COLORS.border };
  sheet.getRange("A6:A13").format.font = { bold: true, color: COLORS.navy };
  sheet.getRange("C6:C13").format.font = { bold: true, color: COLORS.navy };
  sheet.getRange("B12:D12").format.fill = COLORS.paleGreen;
  sheet.getRange("B13:D13").format.fill = COLORS.paleAmber;

  section(sheet, 15, "End-tail anomaly audit across all six direction candidates", 10);
  header(sheet, 17, [
    "Direction",
    "Candidate",
    "V2 previous h",
    "V2 tail h",
    "V2 inversion",
    "V3 previous h",
    "V3 tail h",
    "V3 inversion",
    "Inversion removed",
    "Tail count / capacity",
  ]);
  const rows = [];
  for (const direction of ["outbound", "inbound"]) {
    for (const candidateId of ["C1_DEMAND_FIT", "C2_CONSERVATIVE", "C3_BALANCED"]) {
      const comparison = beforeAfter(route, direction, candidateId);
      const tail = selectedDirectionCandidate(route, direction, candidateId).tail_settlement_evidence;
      rows.push([
        direction,
        candidateId,
        comparison.before_clean_boundary_v2.previous_core_headway,
        comparison.before_clean_boundary_v2.tail_headway,
        comparison.before_clean_boundary_v2.service_intensity_inversion ? "YES" : "NO",
        comparison.after_end_tail_v3.previous_core_headway,
        comparison.after_end_tail_v3.tail_headway,
        null,
        null,
        `${tail.tail_trip_count} / ${tail.min_feasible_tail_trip_count}–${tail.max_feasible_tail_trip_count}`,
      ]);
    }
  }
  sheet.getRange("A18:J23").values = rows;
  sheet.getRange("H18").formulas = [["=IF(G18<F18,\"YES\",\"NO\")"]];
  sheet.getRange("H18:H23").fillDown();
  sheet.getRange("I18").formulas = [["=IF(AND(E18=\"YES\",H18=\"NO\"),\"YES\",\"NO\")"]];
  sheet.getRange("I18:I23").fillDown();
  sheet.getRange("A18:J23").format.borders = {
    insideHorizontal: { style: "thin", color: COLORS.border },
  };
  sheet.getRange("H18:I23").conditionalFormats.add("containsText", {
    text: "YES",
    format: { fill: COLORS.paleGreen, font: { color: "#166534", bold: true } },
  });

  section(sheet, 25, "What changed in this side-by-side path", 10);
  const notes = [
    ["Demand evidence", "DemandRegime boundaries and observed-demand shares are unchanged."],
    ["Effective spans", "Service-floor, nominal-headway, compile-quality, and edge feasibility use fixed endpoint clipping."],
    ["Allocation", "Core regimes are allocated first; the final tail count is the exact residual."],
    ["Tail compiler", "Tail departures are built backward from fixed last with h_prev ≤ h_tail ≤ service floor."],
    ["Fleet", "The existing fixed-timetable fleet validator is reused after exact compilation."],
  ];
  sheet.getRange("A27:B31").values = notes;
  sheet.getRange("A27:A31").format.font = { bold: true, color: COLORS.navy };
  sheet.getRange("A27:B31").format.borders = {
    insideHorizontal: { style: "thin", color: COLORS.border },
  };
  sheet.getRange("B27:B31").format.wrapText = true;
  setWidths(sheet, [20, 48, 20, 48, 15, 15, 15, 15, 18, 22]);
  sheet.freezePanes.freezeRows(4);
}

function writeTailEvidence(sheet, route) {
  baseSheet(sheet);
  title(sheet, `Route ${route.route_id} · Tail settlement evidence`, 18);
  section(sheet, 4, "Eligibility, residual debt capacity, backward anchoring, and clean-boundary ownership", 18);
  header(sheet, 6, [
    "Direction",
    "Candidate",
    "Final density",
    "Eligibility",
    "Tail zone start",
    "Tail zone end",
    "Fixed last",
    "Previous h",
    "Tail count",
    "Tail ideal",
    "Tail debt",
    "Tail h",
    "Tail start",
    "Tail last",
    "Feasible counts",
    "Min",
    "Max",
    "Boundary ownership",
  ]);
  const rows = [];
  for (const direction of ["outbound", "inbound"]) {
    for (const candidateId of ["C1_DEMAND_FIT", "C2_CONSERVATIVE", "C3_BALANCED"]) {
      const tail = selectedDirectionCandidate(route, direction, candidateId).tail_settlement_evidence;
      rows.push([
        direction,
        candidateId,
        tail.final_demand_density_index,
        tail.tail_eligibility,
        excelTime(tail.tail_zone_start),
        excelTime(tail.tail_zone_end),
        excelTime(tail.fixed_last_departure),
        tail.previous_core_headway,
        tail.tail_trip_count,
        tail.tail_ideal_trip_count,
        null,
        tail.tail_headway,
        excelTime(tail.tail_start),
        excelTime(tail.tail_last_departure),
        tail.feasible_tail_trip_counts.join(", "),
        tail.min_feasible_tail_trip_count,
        tail.max_feasible_tail_trip_count,
        compactOwnership(tail.clean_boundary_ownership),
      ]);
    }
  }
  sheet.getRange("A7:R12").values = rows;
  sheet.getRange("K7").formulas = [["=I7-J7"]];
  sheet.getRange("K7:K12").fillDown();
  sheet.getRange("C7:C12").format.numberFormat = "0.000";
  sheet.getRange("E7:G12").format.numberFormat = "hh:mm";
  sheet.getRange("J7:K12").format.numberFormat = "0.00";
  sheet.getRange("M7:N12").format.numberFormat = "hh:mm";
  sheet.getRange("A7:R12").format.borders = {
    insideHorizontal: { style: "thin", color: COLORS.border },
  };
  sheet.getRange("D7:D12").format.fill = COLORS.paleGreen;
  sheet.getRange("K7:K12").conditionalFormats.add("colorScale", {
    colors: [COLORS.paleGreen, COLORS.paleAmber, COLORS.paleRed],
  });
  setWidths(sheet, [13, 20, 13, 27, 14, 14, 14, 12, 11, 12, 12, 10, 13, 13, 17, 9, 9, 18]);
  sheet.freezePanes.freezeRows(6);
}

function writeAllocation(sheet, route) {
  baseSheet(sheet);
  title(sheet, `Route ${route.route_id} · Demand evidence and trip allocation`, 17);
  section(sheet, 4, "Observed demand stays unchanged; operational calculations use effective spans", 17);
  header(sheet, 6, [
    "Direction",
    "Candidate",
    "DemandRegime",
    "Demand start",
    "Demand end",
    "Effective start",
    "Effective end",
    "Demand share",
    "Ideal trips",
    "V2 trips",
    "V3 trips",
    "Trip delta",
    "V3 service share",
    "Mismatch component",
    "Nominal op. h",
    "Service floor",
    "Tail/core",
  ]);
  const rows = [];
  for (const direction of ["outbound", "inbound"]) {
    const data = directionData(route, direction);
    const finalSpan = data.effective_service_spans.at(-1);
    for (const candidateId of ["C1_DEMAND_FIT", "C2_CONSERVATIVE", "C3_BALANCED"]) {
      const candidate = selectedDirectionCandidate(route, direction, candidateId);
      const comparison = beforeAfter(route, direction, candidateId);
      const core = candidate.allocation.core_regime_evidence;
      const totalTrips = candidate.compilation.exact_departures.length;
      core.forEach((item, index) => {
        rows.push([
          direction,
          candidateId,
          item.regime_id,
          excelTime(item.demand_start),
          excelTime(item.demand_end),
          excelTime(item.effective_start),
          excelTime(item.effective_end),
          item.demand_share,
          item.ideal_trip_count,
          comparison.before_clean_boundary_v2.allocation_vector[index],
          item.allocated_trip_count,
          null,
          null,
          null,
          item.nominal_operational_headway,
          data.service_floor_headway_minutes,
          "CORE",
        ]);
      });
      const tailIndex = comparison.before_clean_boundary_v2.allocation_vector.length - 1;
      const tailCount = candidate.tail_settlement_evidence.tail_trip_count;
      rows.push([
        direction,
        candidateId,
        data.tail_eligibility.final_regime_id,
        excelTime(finalSpan.demand_start),
        excelTime(finalSpan.demand_end),
        excelTime(finalSpan.effective_start),
        excelTime(finalSpan.effective_end),
        data.tail_eligibility.final_demand_share,
        data.tail_ideal_trip_count,
        comparison.before_clean_boundary_v2.allocation_vector[tailIndex],
        tailCount,
        null,
        null,
        null,
        finalSpan.effective_duration_minutes / tailCount,
        data.service_floor_headway_minutes,
        "TAIL RESIDUAL",
      ]);
      void totalTrips;
    }
  }
  const endRow = 6 + rows.length;
  sheet.getRange(`A7:Q${endRow}`).values = rows;
  sheet.getRange("L7").formulas = [["=K7-J7"]];
  sheet.getRange(`L7:L${endRow}`).fillDown();
  sheet.getRange("M7").formulas = [["=K7/SUMIFS($K$7:$K$200,$A$7:$A$200,A7,$B$7:$B$200,B7)"]];
  sheet.getRange(`M7:M${endRow}`).fillDown();
  sheet.getRange("N7").formulas = [["=(M7-H7)^2"]];
  sheet.getRange(`N7:N${endRow}`).fillDown();
  sheet.getRange(`D7:G${endRow}`).format.numberFormat = "hh:mm";
  sheet.getRange(`H7:H${endRow}`).format.numberFormat = "0.00%";
  sheet.getRange(`I7:I${endRow}`).format.numberFormat = "0.00";
  sheet.getRange(`M7:M${endRow}`).format.numberFormat = "0.00%";
  sheet.getRange(`N7:P${endRow}`).format.numberFormat = "0.0000";
  sheet.getRange(`A7:Q${endRow}`).format.borders = {
    insideHorizontal: { style: "thin", color: COLORS.border },
  };
  sheet.getRange(`Q7:Q${endRow}`).conditionalFormats.add("containsText", {
    text: "TAIL",
    format: { fill: COLORS.paleAmber, font: { bold: true, color: COLORS.amber } },
  });
  setWidths(sheet, [13, 20, 23, 13, 13, 14, 14, 13, 12, 10, 10, 10, 14, 16, 14, 13, 16]);
  sheet.freezePanes.freezeRows(6);
}

function writeTimetable(sheet, route) {
  baseSheet(sheet);
  title(sheet, `Route ${route.route_id} · V2 / V3 exact timetable comparison`, 12);
  section(sheet, 4, "All six direction candidates; fixed endpoints and exact totals retained", 12);
  header(sheet, 6, [
    "Direction",
    "Candidate",
    "Seq",
    "V2 departure",
    "V2 gap",
    "V2 ServiceRegime",
    "V3 departure",
    "V3 gap",
    "Delta (min)",
    "V3 ServiceRegime",
    "V3 service h",
    "Tail row",
  ]);
  const rows = [];
  for (const direction of ["outbound", "inbound"]) {
    for (const candidateId of ["C1_DEMAND_FIT", "C2_CONSERVATIVE", "C3_BALANCED"]) {
      const before = priorCompilation(route.route_id, direction, candidateId);
      const afterCandidate = selectedDirectionCandidate(route, direction, candidateId);
      const after = afterCandidate.compilation;
      const tailStart = afterCandidate.tail_settlement_evidence.tail_start;
      for (let index = 0; index < before.exact_departures.length; index += 1) {
        const beforeDeparture = before.exact_departures[index];
        const afterDeparture = after.exact_departures[index];
        const beforeService = serviceForDeparture(before, beforeDeparture);
        const afterService = serviceForDeparture(after, afterDeparture);
        rows.push([
          direction,
          candidateId,
          index + 1,
          excelTime(beforeDeparture),
          index === 0 ? null : (beforeDeparture - before.exact_departures[index - 1]) / 60,
          beforeService.service_regime_id,
          excelTime(afterDeparture),
          index === 0 ? null : (afterDeparture - after.exact_departures[index - 1]) / 60,
          null,
          afterService.service_regime_id,
          afterService.uniform_headway_minutes,
          afterDeparture >= tailStart ? "TAIL" : "",
        ]);
      }
    }
  }
  const endRow = 6 + rows.length;
  sheet.getRange(`A7:L${endRow}`).values = rows;
  sheet.getRange("I7").formulas = [["=(G7-D7)*1440"]];
  sheet.getRange(`I7:I${endRow}`).fillDown();
  sheet.getRange(`D7:D${endRow}`).format.numberFormat = "hh:mm";
  sheet.getRange(`G7:G${endRow}`).format.numberFormat = "hh:mm";
  sheet.getRange(`E7:E${endRow}`).format.numberFormat = "0";
  sheet.getRange(`H7:I${endRow}`).format.numberFormat = "0";
  sheet.getRange(`A7:L${endRow}`).format.borders = {
    insideHorizontal: { style: "thin", color: COLORS.border },
  };
  sheet.getRange(`L7:L${endRow}`).conditionalFormats.add("containsText", {
    text: "TAIL",
    format: { fill: COLORS.paleAmber, font: { bold: true, color: COLORS.amber } },
  });
  setWidths(sheet, [13, 20, 8, 14, 10, 24, 14, 10, 12, 25, 13, 11]);
  sheet.freezePanes.freezeRows(6);
}

function writeFleet(sheet, route, prior) {
  baseSheet(sheet);
  title(sheet, `Route ${route.route_id} · Recalculated 9-combination fleet matrix`, 16);
  section(sheet, 4, "Same fixed-timetable validator, rerun on V3 exact departures", 16);
  header(sheet, 6, [
    "Outbound",
    "Inbound",
    "V2 status",
    "V2 fleet",
    "V3 status",
    "V3 fleet",
    "Fleet delta",
    "Ceiling",
    "V3 min layover",
    "V3 avg wait",
    "V3 mismatch",
    "V3 moved",
    "V3 quant. error",
    "V3 regimes",
    "V2 selected",
    "V3 selected",
  ]);
  const rows = [];
  for (const current of route.fleet_matrix) {
    const before = prior.fleet_matrix.find(
      (item) =>
        item.outbound_candidate_id === current.outbound_candidate_id &&
        item.inbound_candidate_id === current.inbound_candidate_id,
    );
    rows.push([
      current.outbound_candidate_id,
      current.inbound_candidate_id,
      before.status,
      before.fleet_requirement,
      current.status,
      current.fleet_requirement,
      null,
      current.fleet_ceiling,
      current.minimum_connection_layover_minutes,
      current.average_scheduled_wait_minutes,
      current.frozen_demand_mismatch,
      current.frozen_moved_trips,
      current.compiler_quantization_error,
      current.service_regime_count,
      before.outbound_candidate_id === prior.final_selection.outbound_candidate_id &&
      before.inbound_candidate_id === prior.final_selection.inbound_candidate_id
        ? "YES"
        : "",
      current.outbound_candidate_id === route.final_selection.outbound_candidate_id &&
      current.inbound_candidate_id === route.final_selection.inbound_candidate_id
        ? "YES"
        : "",
    ]);
  }
  sheet.getRange("A7:P15").values = rows;
  sheet.getRange("G7").formulas = [["=F7-D7"]];
  sheet.getRange("G7:G15").fillDown();
  sheet.getRange("J7:J15").format.numberFormat = "0.00";
  sheet.getRange("K7:K15").format.numberFormat = "0.000000";
  sheet.getRange("M7:M15").format.numberFormat = "0.000000";
  sheet.getRange("A7:P15").format.borders = {
    insideHorizontal: { style: "thin", color: COLORS.border },
  };
  for (let row = 7; row <= 15; row += 1) {
    if (sheet.getRange(`P${row}`).values[0][0] === "YES") {
      sheet.getRange(`A${row}:P${row}`).format.fill = COLORS.paleGreen;
      sheet.getRange(`A${row}:P${row}`).format.font = { bold: true, color: "#166534" };
    } else if (sheet.getRange(`E${row}`).values[0][0] === "FLEET_INFEASIBLE") {
      sheet.getRange(`A${row}:P${row}`).format.fill = COLORS.paleRed;
    }
  }
  setWidths(sheet, [20, 20, 18, 10, 18, 10, 11, 10, 15, 13, 15, 12, 16, 13, 12, 12]);
  sheet.freezePanes.freezeRows(6);
}

async function createRouteWorkbook(route) {
  const workbook = Workbook.create();
  const summary = workbook.worksheets.add("Review Summary");
  const tail = workbook.worksheets.add("Tail Evidence");
  const allocation = workbook.worksheets.add("Allocation Compare");
  const timetable = workbook.worksheets.add("Timetable Compare");
  const fleet = workbook.worksheets.add("Fleet Matrix");
  const prior = priorRoute(route.route_id);
  writeSummary(summary, route, prior);
  writeTailEvidence(tail, route);
  writeAllocation(allocation, route);
  writeTimetable(timetable, route);
  writeFleet(fleet, route, prior);
  return workbook;
}

async function verifyAndExport(workbook, fileName, previewPrefix) {
  const summary = await workbook.inspect({
    kind: "table",
    range: "Review Summary!A1:J31",
    include: "values,formulas",
    tableMaxRows: 35,
    tableMaxCols: 12,
    maxChars: 8000,
  });
  const tail = await workbook.inspect({
    kind: "table",
    range: "Tail Evidence!A1:R12",
    include: "values,formulas",
    tableMaxRows: 15,
    tableMaxCols: 20,
    maxChars: 8000,
  });
  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 300 },
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
      range: sheetName === "Timetable Compare" ? "A1:L40" : "A1:R35",
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
    tail: tail.ndjson,
    errors: errors.ndjson,
  };
}

const route6 = report.routes.find((item) => item.route_id === "6");
const route10 = report.routes.find((item) => item.route_id === "10");
const route6Workbook = await createRouteWorkbook(route6);
const route10Workbook = await createRouteWorkbook(route10);
const verification = [];
verification.push(
  await verifyAndExport(route6Workbook, "Route_6_EndTail_V3.xlsx", "route6"),
);
verification.push(
  await verifyAndExport(route10Workbook, "Route_10_EndTail_V3.xlsx", "route10"),
);
console.log(JSON.stringify(verification));

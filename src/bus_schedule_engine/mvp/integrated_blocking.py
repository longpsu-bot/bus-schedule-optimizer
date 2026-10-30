"""Complete fixed-timetable trip-DAG CP-SAT; no change to production scoring."""

from __future__ import annotations

import json
import math
import os
import platform
from collections import defaultdict
from contextlib import suppress
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from threading import Event, Thread
from time import perf_counter

import ortools
from ortools.graph.python import max_flow
from ortools.sat.python import cp_model

from .circulation import _matching
from .input import runtime_at
from .integrated_blocking_validation import digest, validate_assignment, validate_request


def _memory_mb():
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (k, ctypes.c_size_t)
                for k in (
                    "PeakWorkingSetSize",
                    "WorkingSetSize",
                    "QuotaPeakPagedPoolUsage",
                    "QuotaPagedPoolUsage",
                    "QuotaPeakNonPagedPoolUsage",
                    "QuotaNonPagedPoolUsage",
                    "PagefileUsage",
                    "PeakPagefileUsage",
                )
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.c_void_p(handle), ctypes.byref(counters), counters.cb
        )
        return counters.WorkingSetSize / 1048576
    # /proc is current resident memory; resource is a conservative peak fallback.
    try:
        return (
            int(Path("/proc/self/statm").read_text().split()[1])
            * os.sysconf("SC_PAGE_SIZE")
            / 1048576
        )
    except (OSError, IndexError):
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (
            1048576 if platform.system() == "Darwin" else 1024
        )


def _relaxation(trips, edges, r):
    n = len(trips)
    adjacency = [[] for _ in trips]
    for i, j in edges:
        adjacency[i].append(j)
    successor, _ = _matching(adjacency)
    matching = [(i, j) for i, j in enumerate(successor) if j >= 0]
    flow = max_flow.SimpleMaxFlow()
    source, sink = 2 * n, 2 * n + 1
    for i in range(n):
        flow.add_arc_with_capacity(source, i, 1)
        flow.add_arc_with_capacity(n + i, sink, 1)
    for i, j in edges:
        flow.add_arc_with_capacity(i, n + j, 1)
    if flow.solve(source, sink) != flow.OPTIMAL:
        raise ValueError("relaxation maximum flow failed")
    cut = set(flow.get_source_side_min_cut())
    capacity = sum(
        flow.capacity(a)
        for a in range(flow.num_arcs())
        if flow.tail(a) in cut and flow.head(a) not in cut
    )
    if len(matching) != flow.optimal_flow() or capacity != len(matching):
        raise ValueError("matching/flow/min-cut disagree")
    q, h, p = (r["terminal_policy"][k] for k in ("technical", "post", "pre"))
    workload = sum(t["runtime"] for t in trips)
    duty_bound = (
        math.ceil((workload + n * (q + h + p)) / (r["crew_policy"]["duty"]["limit"] + q))
        if r["crew_policy"]["duty"]["mode"] == "ENFORCED"
        else 1
    )
    return dict(
        task_path_bound=n - len(matching),
        workload_duty_bound=duty_bound,
        driving_workload=workload,
        matching_size=len(matching),
        cut_capacity=capacity,
        source_side_cut=sorted(cut),
        matching=[[trips[i]["trip_id"], trips[j]["trip_id"]] for i, j in matching],
        edge_count=len(edges),
        provenance="complete task/reserve DAG matching and independent unit-capacity max-flow/min-cut; corrected endpoint workload",
    )


def _witness(chains, trips, edges, meals, meal_choices=None):
    blocks = []
    for k, chain in enumerate(
        sorted(chains, key=lambda c: (trips[c[0]]["departure"], trips[c[0]]["trip_id"])), 1
    ):
        rests = []
        used = set()
        for i, j in zip(chain, chain[1:], strict=False):
            left, right = edges[i, j]
            base = dict(
                after_trip=trips[i]["trip_id"],
                before_trip=trips[j]["trip_id"],
                terminal="B" if trips[i]["direction"] == "outbound" else "A",
            )
            if right > left:
                rests.append(dict(base, start=left, end=right, kind="protected"))
            for m in meals:
                lo, u = max(left, m["start"]), min(right, m["end"])
                chosen = (
                    (i, j, m["name"]) in meal_choices
                    if meal_choices is not None
                    else m["name"] not in used
                    and m["mode"] == "ENFORCED"
                    and u - lo >= m["minutes"]
                )
                if chosen:
                    rests.append(dict(base, start=lo, end=lo + m["minutes"], kind=m["name"]))
                    used.add(m["name"])
        blocks.append(
            dict(
                block_id=f"B{k:03d}",
                vehicle_id=f"V{k:03d}",
                team_id=f"T{k:03d}",
                driver_id=f"D{k:03d}",
                attendant_id=f"A{k:03d}",
                trip_ids=[trips[i]["trip_id"] for i in chain],
                rests=rests,
            )
        )
    return blocks


def _greedy(r, trips, edges):
    """Conservative short blocks provide a seed, never a minimum certificate."""
    crew = r["crew_policy"]
    q, h, p = (r["terminal_policy"][k] for k in ("technical", "post", "pre"))
    chains = []
    for j, t in enumerate(trips):
        choices = []
        for k, chain in enumerate(chains):
            if (chain[-1], j) not in edges:
                continue
            span = t["arrival"] + h - (trips[chain[0]]["departure"] - p)
            # Sustained duties shorter than the thresholds owe no meal/general rest.
            if span >= min(crew["meals"]["duty_threshold"], crew["general_rest"]["duty_threshold"]):
                continue
            if crew["duty"]["mode"] == "ENFORCED" and span > crew["duty"]["limit"]:
                continue
            total = sum(trips[i]["runtime"] for i in chain) + t["runtime"]
            if crew["driving"]["mode"] == "ENFORCED" and total > crew["driving"]["limit"]:
                continue
            choices.append((trips[chain[0]]["departure"], k))
        if choices:
            chains[min(choices)[1]].append(j)
        else:
            chains.append([j])
    return _witness(chains, trips, edges, crew["meals"]["windows"])


def solve_integrated(request, *, incumbent=None, checkpoint=None, cancelled=None):
    """Return only independently verified upper bounds; preserve them at any cutoff."""
    began = perf_counter()
    result = dict(
        schema_version="integrated_blocking_result_v1",
        status="SEARCH_INCOMPLETE",
        native_status=None,
        model_complete=False,
        validator_pass=False,
        lower_bound=None,
        upper_bound=None,
        absolute_gap=None,
        relative_gap=None,
        blocks=None,
        validation=None,
        operational_authority="UNVERIFIED",
        proof_scope="declared experimental fixed timetable only",
    )
    try:
        r = validate_request(request)
    except ValueError as exc:
        return result | dict(
            status="BLOCKED_INPUT_AUTHORITY",
            termination_reason=str(exc),
            wall_seconds=perf_counter() - began,
        )
    result.update(
        request_sha256=digest(r),
        runtime_sha256=digest(r["runtime_scenario"]),
        policy_sha256=digest(
            {
                k: r[k]
                for k in (
                    "terminal_policy",
                    "recovery_policy",
                    "crew_policy",
                    "stock",
                    "resource_cap",
                )
            }
        ),
        versions=dict(python=platform.python_version(), ortools=ortools.__version__),
        limits=r["search"],
        deterministic_seconds=0,
    )
    best = None
    errors = []
    stop_reason = None

    def retain(blocks):
        nonlocal best
        checked = validate_assignment(r, blocks)
        rank = (
            len(blocks),
            sum(b["duty_span"] for b in checked["blocks"]),
            tuple(tuple(b["trip_ids"]) for b in blocks),
        )
        if best is None or rank < best[0]:
            best = (rank, deepcopy(blocks), checked)
            if checkpoint is not None:
                try:
                    target = Path(checkpoint)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temporary = target.with_suffix(target.suffix + ".tmp")
                    temporary.write_text(
                        json.dumps(
                            dict(request_sha256=result["request_sha256"], blocks=blocks),
                            sort_keys=True,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                    temporary.replace(target)
                except OSError as exc:
                    errors.append(
                        f"checkpoint write failed; validated witness retained in memory: {exc}"
                    )

    def finish(reason, *, native=None, proven_infeasible=False, internal=False):
        internal = internal or bool(errors)
        if best is not None:
            # Revalidate the retained immutable witness, independent of last native response.
            checked = validate_assignment(r, best[1])
            upper = len(best[1])
            result.update(
                blocks=best[1], validation=checked, validator_pass=True, upper_bound=upper
            )
            lower = result["lower_bound"]
            if lower is not None and lower > upper:
                internal = True
                errors.append("lower bound exceeds validated incumbent")
            if not internal:
                result["status"] = (
                    "OPTIMAL_PROVEN" if lower == upper else "FEASIBLE_NOT_PROVEN_OPTIMAL"
                )
            if lower is not None:
                result.update(absolute_gap=upper - lower, relative_gap=(upper - lower) / upper)
        elif proven_infeasible and not internal:
            result["status"] = "INFEASIBLE_PROVEN"
        result.update(
            termination_reason=reason,
            native_status=native,
            wall_seconds=perf_counter() - began,
            errors=errors,
            incumbent_order="vehicle count, total elapsed duty, canonical chain order",
        )
        return result

    if checkpoint is not None and Path(checkpoint).exists():
        try:
            saved = json.loads(Path(checkpoint).read_text(encoding="utf-8"))
            if not isinstance(saved, dict) or set(saved) != {"request_sha256", "blocks"}:
                raise ValueError("checkpoint must contain only request_sha256 and blocks")
            if saved["request_sha256"] != result["request_sha256"]:
                raise ValueError("checkpoint request digest mismatch")
            retain(saved["blocks"])
        except (ValueError, KeyError, OSError) as exc:
            return finish(f"invalid checkpoint: {exc}", internal=True)
    if incumbent is not None:
        try:
            retain(incumbent)
        except ValueError as exc:
            return finish(f"invalid supplied incumbent: {exc}", internal=True)
    crew, tasks = r["crew_policy"], r["terminal_policy"]
    q, h, p = (tasks[k] for k in ("technical", "post", "pre"))
    trips = []
    for t in r["timetable"]["trips"]:
        runtime = runtime_at(
            {"runtime_periods": r["runtime_scenario"]["directions"][t["direction"]]}, t["departure"]
        )
        trips.append(dict(t, runtime=runtime, arrival=t["departure"] + runtime))
    trips.sort(key=lambda t: (t["departure"], t["trip_id"]))
    edges = {}
    for i, t in enumerate(trips):
        left = t["arrival"] + q + h + r["recovery_policy"]["reserve_by_arriving_trip"][t["trip_id"]]
        for j, u in enumerate(trips):
            if (
                t["direction"] != u["direction"]
                and t["departure"] < u["departure"]
                and left <= u["departure"] - p
            ):
                edges[i, j] = (left, u["departure"] - p)
    relaxation = _relaxation(trips, edges, r)
    result.update(
        relaxation=relaxation,
        lower_bound=max(relaxation["task_path_bound"], relaxation["workload_duty_bound"]),
    )
    if len(edges) > r["search"]["max_edges"]:
        return finish("complete edge budget exceeded; model not searched")
    if cancelled is not None and cancelled():
        return finish("cancelled before model construction")
    # Strict-window rules/stock may invalidate this heuristic; validation gates the bound.
    with suppress(ValueError):
        retain(_greedy(r, trips, edges))
    if _memory_mb() > r["search"]["memory_mb"]:
        return finish("process memory ceiling before model construction")
    model = cp_model.CpModel()
    incoming, outgoing = defaultdict(list), defaultdict(list)
    x = {e: model.new_bool_var(f"x{e[0]}_{e[1]}") for e in edges}
    for (i, j), v in x.items():
        outgoing[i].append(v)
        incoming[j].append(v)
    n = len(trips)
    starts = [model.new_bool_var(f"s{i}") for i in range(n)]
    ends = [model.new_bool_var(f"t{i}") for i in range(n)]
    earliest = min(t["departure"] for t in trips) - p
    S = [model.new_int_var(earliest, t["departure"] - p, f"S{i}") for i, t in enumerate(trips)]
    V = (
        [
            model.new_int_var(t["runtime"], sum(u["runtime"] for u in trips), f"V{i}")
            for i, t in enumerate(trips)
        ]
        if crew["total_driving"]["mode"] == "ENFORCED"
        else None
    )
    C = (
        [model.new_int_var(0, crew["driving"]["limit"], f"C{i}") for i in range(n)]
        if crew["driving"]["mode"] == "ENFORCED"
        else None
    )
    G = (
        [model.new_bool_var(f"G{i}") for i in range(n)]
        if crew["general_rest"]["mode"] == "ENFORCED"
        else None
    )
    meals = [m for m in crew["meals"]["windows"] if m["mode"] == "ENFORCED"]
    M = {m["name"]: [model.new_bool_var(f"M{m['name']}{i}") for i in range(n)] for m in meals}
    meal_vars = {}
    for i, t in enumerate(trips):
        model.add(starts[i] + sum(incoming[i]) == 1)
        model.add(ends[i] + sum(outgoing[i]) == 1)
        model.add(S[i] == t["departure"] - p).only_enforce_if(starts[i])
        if crew["duty"]["mode"] == "ENFORCED":
            model.add(
                t["arrival"] + h - S[i] <= crew["duty"]["limit"]
            )  # Valid monotone prefix bound.
        if V is not None:
            model.add(V[i] == t["runtime"]).only_enforce_if(starts[i])
            model.add(V[i] <= crew["total_driving"]["limit"]).only_enforce_if(ends[i])
        if C is not None:
            model.add(C[i] == t["runtime"]).only_enforce_if(starts[i])
        if G is not None:
            model.add(G[i] == 0).only_enforce_if(starts[i])
            model.add(
                S[i] >= t["arrival"] + h - crew["general_rest"]["duty_threshold"] + 1
            ).only_enforce_if([ends[i], G[i].Not()])
        for m in meals:
            state = M[m["name"]][i]
            model.add(state == 0).only_enforce_if(starts[i])
            end = t["arrival"] + h
            if crew["meals"]["eligibility"] == "DUTY_INTERSECTS_WINDOW":
                if end > m["start"]:
                    model.add(S[i] >= m["end"]).only_enforce_if([ends[i], state.Not()])
            else:
                overlap = crew["meals"]["overlap_threshold"]
                threshold = end - crew["meals"]["duty_threshold"]
                if overlap == 0:
                    model.add(S[i] >= threshold + 1).only_enforce_if([ends[i], state.Not()])
                elif overlap <= m["end"] - m["start"] and end >= m["start"] + overlap:
                    threshold = min(threshold, end - overlap, m["end"] - overlap)
                    model.add(S[i] >= threshold + 1).only_enforce_if([ends[i], state.Not()])
    for (i, j), v in x.items():
        left, right = edges[i, j]
        model.add(S[j] == S[i]).only_enforce_if(v)
        if V is not None:
            model.add(V[j] == V[i] + trips[j]["runtime"]).only_enforce_if(v)
        if C is not None:
            reset = right - left >= crew["driving"]["reset_minutes"]
            model.add(
                C[j] == (trips[j]["runtime"] if reset else C[i] + trips[j]["runtime"])
            ).only_enforce_if(v)
        if G is not None:
            model.add(
                G[j] == (1 if right - left >= crew["general_rest"]["minutes"] else G[i])
            ).only_enforce_if(v)
        for m in meals:
            if min(right, m["end"]) - max(left, m["start"]) >= m["minutes"]:
                b = model.new_bool_var(f"b{i}_{j}_{m['name']}")
                model.add(b <= v)
                meal_vars[i, j, m["name"]] = b
            else:
                b = 0
            model.add(M[m["name"]][j] == M[m["name"]][i] + b).only_enforce_if(v)
    caps = r["stock"]["initial_vehicles"]
    if caps is not None:
        for d, terminal in (("outbound", "A"), ("inbound", "B")):
            model.add(
                sum(starts[i] for i, t in enumerate(trips) if t["direction"] == d) <= caps[terminal]
            )
    K = sum(starts)
    model.add(result["lower_bound"] <= K)
    if r["resource_cap"] is not None:
        model.add(r["resource_cap"]["limit"] >= K)
    model.minimize(K)
    if best:
        model.add(len(best[1]) >= K)
        by_id = {t["trip_id"]: i for i, t in enumerate(trips)}
        selected = {
            (by_id[a], by_id[b])
            for chain in best[1]
            for a, b in zip(chain["trip_ids"], chain["trip_ids"][1:], strict=False)
        }
        for e, v in x.items():
            model.add_hint(v, int(e in selected))
    result.update(
        model_complete=True,
        model_sha256=sha256(str(model.proto).encode()).hexdigest(),
        model_stats=model.model_stats(),
    )
    remaining = r["search"]["wall_seconds"] - (perf_counter() - began)
    if remaining <= 0:
        return finish("wall limit during model construction")
    engine = cp_model.CpSolver()
    engine.parameters.num_search_workers = 1
    engine.parameters.random_seed = r["search"]["seed"]
    engine.parameters.max_time_in_seconds = remaining
    engine.parameters.max_deterministic_time = r["search"]["deterministic_seconds"]
    engine.parameters.absolute_gap_limit = 0
    engine.parameters.relative_gap_limit = 0

    def extract(reader):
        following = {i: j for (i, j), v in x.items() if reader.value(v)}
        chains = []
        for i in range(n):
            if reader.value(starts[i]):
                chain = []
                cursor = i
                while True:
                    chain.append(cursor)
                    if cursor not in following:
                        break
                    cursor = following[cursor]
                chains.append(chain)
        choices = {key for key, v in meal_vars.items() if reader.value(v)}
        return _witness(chains, trips, edges, meals, choices)

    class Collector(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            try:
                retain(extract(self))
            except (ValueError, OSError) as exc:
                errors.append(f"incumbent validation/checkpoint failure: {exc}")
                self.stop_search()

    done = Event()

    def monitor():
        nonlocal stop_reason
        while not done.wait(0.05):
            if cancelled is not None and cancelled():
                stop_reason = "cancelled during search"
            elif _memory_mb() > r["search"]["memory_mb"]:
                stop_reason = "process memory ceiling"
            elif perf_counter() - began >= r["search"]["wall_seconds"]:
                stop_reason = "emergency wall limit"
            if stop_reason:
                engine.stop_search()
                break

    watcher = Thread(target=monitor, daemon=True)
    watcher.start()
    try:
        native = engine.solve(model, Collector())
    except (ValueError, RuntimeError) as exc:
        errors.append(str(exc))
        return finish("internal solver error", internal=True)
    finally:
        done.set()
        watcher.join()
    name = engine.status_name(native)
    result.update(
        deterministic_seconds=engine.response_proto.deterministic_time,
        response_sha256=sha256(str(engine.response_proto).encode()).hexdigest(),
        solver_statistics=engine.response_stats(),
    )
    if native in (cp_model.OPTIMAL, cp_model.FEASIBLE, cp_model.UNKNOWN) and not errors:
        bound = engine.best_objective_bound
        if math.isfinite(bound):
            result["lower_bound"] = max(result["lower_bound"], math.floor(bound))
    if native in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        try:
            retain(extract(engine))
        except (ValueError, OSError) as exc:
            errors.append(str(exc))
    if native == cp_model.OPTIMAL and best is not None and not errors:
        result["lower_bound"] = len(best[1])
    inconsistent = native == cp_model.INFEASIBLE and best is not None
    return finish(
        stop_reason
        or (
            "complete model optimum"
            if native == cp_model.OPTIMAL
            else "complete model infeasible"
            if native == cp_model.INFEASIBLE
            else "deterministic/wall search limit"
        ),
        native=name,
        proven_infeasible=native == cp_model.INFEASIBLE,
        internal=bool(errors) or inconsistent or native == cp_model.MODEL_INVALID,
    )

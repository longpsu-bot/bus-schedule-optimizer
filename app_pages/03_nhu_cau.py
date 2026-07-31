import streamlit as st

from bus_schedule_engine.models import TripRidershipMatchStatusV1
from bus_schedule_engine.protected_service_floor import (
    protected_service_floor_assessment_is_current_v1,
)
from bus_schedule_engine.protected_service_floor_codes import (
    PROTECTED_FLOOR_CANDIDATE_ACCEPTED,
    PROTECTED_FLOOR_CANDIDATE_REJECTED,
    PROTECTED_FLOOR_ENFORCEMENT_AUTHORITY_CURRENT,
    PROTECTED_FLOOR_ENFORCEMENT_NO_REGIMES,
)
from bus_schedule_engine.time_utils import format_hhmm
from bus_schedule_engine.trip_ridership import trip_ridership_analysis_is_current_v1
from bus_schedule_engine.ui_result_authority import (
    VisibleResultModeV1,
    resolve_visible_result_context_v1,
)
from bus_schedule_engine.unified_ui_frames import (
    demand_block_rows_v1,
    demand_gap_rows_v1,
    demand_summary_v1,
)

visible = resolve_visible_result_context_v1(
    runtime_status=st.session_state.get("unified_runtime_status"),
    input_readiness=st.session_state.get("workbook_input_readiness"),
    unified_result=st.session_state.get("unified_optimization_result"),
    presentation=st.session_state.get("unified_presentation"),
    unified_demand_supply_figure=st.session_state.get("unified_demand_supply_figure"),
    unified_departure_figure=st.session_state.get("unified_departure_figure"),
    unified_download_artifacts=st.session_state.get("unified_download_artifacts"),
    unified_runtime_failure=st.session_state.get("unified_runtime_failure"),
)

if visible.mode == VisibleResultModeV1.NO_RESULT:
    st.warning(visible.banner_message)
    st.stop()

if not visible.uses_unified:
    if visible.banner_level == "error":
        st.error(visible.banner_message, icon=":material/error:")
    else:
        st.warning(visible.banner_message, icon=":material/warning:")
    st.stop()

if visible.mode == VisibleResultModeV1.UNIFIED_ARTIFACT_FAILED:
    st.warning(visible.banner_message, icon=":material/warning:")
else:
    st.info(visible.banner_message, icon=":material/info:")

if visible.uses_unified:
    presentation = visible.presentation
    assert presentation is not None
    if presentation.requires_expert_review:
        review_codes = "\n".join(f"- {code}" for code in presentation.expert_review_required_codes)
        st.warning(
            "Contract V1 yêu cầu chuyên gia rà soát; đây không phải phê duyệt khai thác.\n\n"
            f"{review_codes}",
            icon=":material/rate_review:",
        )

    summary = demand_summary_v1(presentation)
    maximum_b = summary["maximum_b_load_factor"]
    maximum_c = summary["maximum_c_load_factor"]
    with st.container(horizontal=True):
        st.metric("Mức phù hợp nhu cầu", summary["demand_suitability_status"], border=True)
        st.metric("Độ tin cậy nhu cầu", summary["demand_confidence"], border=True)
        st.metric(
            "Khoảng trống nhu cầu (DISPLAY_DERIVED)",
            summary["demand_gap_count"],
            border=True,
        )
        st.metric(
            "Hệ số tải B cao nhất (DISPLAY_DERIVED)",
            "—" if maximum_b is None else f"{maximum_b:.1%}",
            border=True,
        )
        st.metric(
            "Hệ số tải C cao nhất (DISPLAY_DERIVED)",
            "—" if maximum_c is None else f"{maximum_c:.1%}",
            border=True,
        )

    gaps = demand_gap_rows_v1(presentation)
    if gaps:
        st.subheader("Khoảng trống nhu cầu được Contract V1 trả về")
        st.dataframe(gaps, hide_index=True)

    if not presentation.outcome.accepted_c_exists:
        st.warning(
            "Không tồn tại phương án C có thẩm quyền trong kết quả Contract V1. "
            "Bảng giữ các cột C trống và không dùng B thay thế C.",
            icon=":material/info:",
        )
        st.write(f"Hành động được chọn: `{presentation.outcome.selected_action}`")
        for explanation in presentation.outcome.explanations:
            st.write(f"- {explanation}")
        for limitation in presentation.outcome.limitations:
            st.warning(limitation, icon=":material/warning:")

    st.subheader("Nhu cầu và cung theo đúng grain block Contract V1")
    st.caption(
        "Các số đếm và cực đại được gắn nhãn DISPLAY_DERIVED; không có nội suy, "
        "gộp block hoặc phân bổ nhu cầu theo chiều."
    )
    st.dataframe(
        demand_block_rows_v1(presentation),
        hide_index=True,
        column_config={
            "Hệ số tải B": st.column_config.NumberColumn(format="percent"),
            "Hệ số tải C": st.column_config.NumberColumn(format="percent"),
        },
    )

    st.subheader("Sản lượng theo từng chuyến")
    st.warning(
        "Dữ liệu mô tả bổ sung; chưa được sử dụng để sinh phương án C.",
        icon=":material/info:",
    )
    imported_workbook = st.session_state.get("imported_workbook")
    trip_observations = (
        imported_workbook.trip_ridership_observations if imported_workbook is not None else ()
    )
    trip_analysis = st.session_state.get("trip_ridership_analysis")
    trip_failure = st.session_state.get("trip_ridership_failure")
    unified_result = visible.unified_result
    assert unified_result is not None
    b_fingerprint = unified_result.normalized_inputs.scenario_b_fingerprint

    if not trip_observations:
        st.info("Workbook không có bộ dữ liệu SAN_LUONG_CHUYEN.")
    elif trip_failure is not None:
        st.warning(
            f"{trip_failure.code}\n\nMã đối chiếu: {trip_failure.correlation_id}",
            icon=":material/warning:",
        )
    elif not trip_ridership_analysis_is_current_v1(
        trip_analysis,
        imported_workbook,
        b_fingerprint,
    ):
        st.warning(
            "Phân tích sản lượng theo chuyến không khớp workbook hoặc Scenario B hiện tại và "
            "không được hiển thị.",
            icon=":material/warning:",
        )
    else:
        summary = trip_analysis.dataset_summary
        st.write(
            f"Bộ dữ liệu: `{trip_analysis.dataset_id}` · "
            f"Nguồn: `{trip_analysis.source_type}` · "
            f"Độ tin cậy: `{trip_analysis.confidence}` · "
            f"Ngày vận hành: `{trip_analysis.operating_day_type}`"
        )
        with st.container(horizontal=True):
            st.metric("Số ngày quan sát", summary.distinct_service_dates, border=True)
            st.metric(
                "Tỷ lệ ghép dùng được",
                ("—" if summary.usable_match_rate is None else f"{summary.usable_match_rate:.1%}"),
                border=True,
            )
            st.metric(
                "Tỷ lệ ghép chính xác",
                ("—" if summary.exact_match_rate is None else f"{summary.exact_match_rate:.1%}"),
                border=True,
            )
            st.metric(
                "Bao phủ chuyến B",
                (
                    "—"
                    if summary.scheduled_trip_coverage_rate is None
                    else f"{summary.scheduled_trip_coverage_rate:.1%}"
                ),
                border=True,
            )
            st.metric(
                "Bao phủ chuyến-ngày",
                (
                    "—"
                    if summary.matched_trip_date_coverage_rate is None
                    else f"{summary.matched_trip_date_coverage_rate:.1%}"
                ),
                border=True,
            )

        st.caption(
            "Chỉ MATCHED_EXACT và MATCHED_WITHIN_TOLERANCE được dùng cho thống kê. "
            "Quan sát thiếu không được xem là 0 và không có nội suy chuyến-ngày."
        )
        st.markdown("**Chất lượng ghép dữ liệu**")
        st.dataframe(
            [
                {"Trạng thái": "MATCHED_EXACT", "Số bản ghi": summary.exact_matches},
                {
                    "Trạng thái": "MATCHED_WITHIN_TOLERANCE",
                    "Số bản ghi": summary.tolerance_matches,
                },
                {"Trạng thái": "UNMATCHED", "Số bản ghi": summary.unmatched_records},
                {"Trạng thái": "AMBIGUOUS", "Số bản ghi": summary.ambiguous_records},
                {"Trạng thái": "COLLISION", "Số bản ghi": summary.collided_records},
                {"Trạng thái": "INVALID", "Số bản ghi": summary.invalid_records},
            ],
            hide_index=True,
        )

        st.markdown("**Tổng hợp theo chiều**")
        st.dataframe(
            [
                {
                    "Chiều": item.direction.value,
                    "Chuyến B": item.total_b_trips,
                    "Chuyến B có quan sát dùng được": (item.b_trips_with_usable_observation),
                    "Bao phủ chuyến": item.scheduled_trip_coverage_rate,
                    "Bản ghi dùng được": item.usable_matched_records,
                    "Khách ghép quan sát": item.observed_matched_passengers,
                    "Khách ghép/ngày quan sát": (item.observed_matched_passengers_per_service_date),
                    "Bao phủ chuyến-ngày": item.matched_trip_date_coverage_rate,
                }
                for item in trip_analysis.directional_summaries
            ],
            hide_index=True,
        )

        st.markdown("**Tổng hợp toàn tuyến**")
        st.dataframe(
            [
                {
                    "Chuyến B": summary.total_b_trips,
                    "Chuyến B có quan sát dùng được": (summary.b_trips_with_usable_observation),
                    "Bản ghi dùng được": summary.usable_matched_records,
                    "Khách ghép quan sát": summary.observed_matched_passengers,
                    "Khách ghép trung bình/chuyến quan sát": (
                        summary.average_matched_passenger_count_per_observed_trip
                    ),
                    "Khách ghép/ngày quan sát": (
                        summary.observed_matched_passengers_per_service_date
                    ),
                    "Bao phủ chuyến-ngày": summary.matched_trip_date_coverage_rate,
                    "Diễn giải bao phủ": summary.coverage_adjusted_interpretation,
                }
            ],
            hide_index=True,
        )

        st.markdown("**Thống kê mô tả theo chuyến B**")
        st.dataframe(
            [
                {
                    "Mã chuyến": item.trip_id,
                    "Chiều": item.direction.value,
                    "Bến đi": item.departure_terminal,
                    "Giờ kế hoạch": format_hhmm(item.scheduled_departure_seconds),
                    "Sức chứa": item.nominal_trip_capacity,
                    "Số quan sát": item.observation_count,
                    "Số ngày": item.distinct_observation_day_count,
                    "Nhỏ nhất": item.passenger_minimum,
                    "Lớn nhất": item.passenger_maximum,
                    "Trung bình": item.passenger_mean,
                    "Trung vị": item.passenger_median,
                    "P85": item.passenger_p85,
                    "P90": item.passenger_p90,
                    "Hệ số tải TB": item.mean_load_factor,
                    "Hệ số tải P85": item.p85_load_factor,
                    "Hệ số tải P90": item.p90_load_factor,
                    "Ngày đạt/vượt target": (item.days_at_or_above_target_load_factor),
                    "Ngày vượt maximum": item.days_above_maximum_load_factor,
                    "Ghép chính xác": item.exact_match_count,
                    "Ghép trong dung sai": item.tolerance_match_count,
                    "Lệch ghép TB (phút)": (item.mean_absolute_matching_offset_minutes),
                    "Lệch ghép lớn nhất (phút)": (item.maximum_absolute_matching_offset_minutes),
                }
                for item in trip_analysis.trip_summaries
            ],
            hide_index=True,
        )

        diagnostics = [
            item
            for item in trip_analysis.match_rows
            if item.match_status
            in {
                TripRidershipMatchStatusV1.UNMATCHED,
                TripRidershipMatchStatusV1.AMBIGUOUS,
                TripRidershipMatchStatusV1.COLLISION,
                TripRidershipMatchStatusV1.INVALID,
            }
        ]
        if diagnostics:
            st.markdown("**Bản ghi chẩn đoán bị loại**")
            st.dataframe(
                [
                    {
                        "observation_id": item.observation_id,
                        "service_date": item.service_date.isoformat(),
                        "direction": item.direction.value,
                        "source_trip_id": item.source_trip_id,
                        "scheduled_trip_id": item.supplied_scheduled_trip_id,
                        "scheduled_departure_time": format_hhmm(item.scheduled_departure_seconds),
                        "actual_departure_time": format_hhmm(item.actual_departure_seconds),
                        "match_method": item.match_method.value,
                        "match_status": item.match_status.value,
                        "candidate_trip_ids": ", ".join(item.candidate_trip_ids),
                        "time_offset_minutes": (
                            None
                            if item.absolute_time_offset_seconds is None
                            else item.absolute_time_offset_seconds / 60
                        ),
                        "issue_codes": ", ".join(item.issue_codes),
                    }
                    for item in diagnostics
                ],
                hide_index=True,
            )

    st.subheader("Đánh giá regime cần bảo vệ")
    st.warning(
        "Kết quả 6A2A là bằng chứng và preview lịch sử. Trường "
        "NOT_ENFORCED_IN_6A2A không bị thay đổi; 6A2B hiển thị trạng thái thực thi riêng.",
        icon=":material/info:",
    )
    protected_assessment = st.session_state.get("protected_service_floor_assessment")
    protected_failure = st.session_state.get("protected_service_floor_failure")
    assessment_is_current = protected_service_floor_assessment_is_current_v1(
        protected_assessment,
        imported_workbook,
        unified_result.normalized_inputs.scenario_b,
        trip_analysis,
    )
    if protected_failure is not None:
        st.warning(
            f"{protected_failure.code}\n\nMã đối chiếu: {protected_failure.correlation_id}",
            icon=":material/warning:",
        )
    elif not assessment_is_current:
        st.info(
            "Chưa có đánh giá 6A2A hiện hành cho workbook, Scenario B và "
            "bộ dữ liệu sản lượng chuyến đang hoạt động."
        )
    else:
        policy = protected_assessment.policy
        st.markdown("**Ngưỡng chính sách 6A2A**")
        st.dataframe(
            [
                {
                    "Ngưỡng": "Headway B tối đa được bảo vệ (phút)",
                    "Giá trị": policy.maximum_protected_b_headway_minutes,
                },
                {
                    "Ngưỡng": "Dung sai làm tròn headway (phút)",
                    "Giá trị": policy.headway_rounding_tolerance_minutes,
                },
                {
                    "Ngưỡng": "Số chuyến tối thiểu/regime",
                    "Giá trị": policy.minimum_departures_per_regime,
                },
                {
                    "Ngưỡng": "Thời lượng tối thiểu (phút)",
                    "Giá trị": policy.minimum_regime_duration_minutes,
                },
                {
                    "Ngưỡng": "Số ngày quan sát tối thiểu/chuyến",
                    "Giá trị": policy.minimum_observed_days_per_trip,
                },
                {
                    "Ngưỡng": "Bao phủ chuyến tối thiểu",
                    "Giá trị": policy.minimum_regime_trip_coverage_rate,
                },
                {
                    "Ngưỡng": "Tỷ lệ chuyến tải cao tối thiểu",
                    "Giá trị": policy.minimum_high_load_trip_share,
                },
                {
                    "Ngưỡng": "Thống kê tải",
                    "Giá trị": policy.protected_load_statistic,
                },
                {
                    "Ngưỡng": "Độ tin cậy tối thiểu",
                    "Giá trị": policy.minimum_trip_ridership_confidence,
                },
                {
                    "Ngưỡng": "Dung sai biên tương lai (phút)",
                    "Giá trị": (policy.future_service_window_boundary_tolerance_minutes),
                },
            ],
            hide_index=True,
        )

        regimes_by_id = {regime.regime_id: regime for regime in protected_assessment.regimes}
        st.markdown("**Mọi regime B và quyết định bảo vệ**")
        st.dataframe(
            [
                {
                    "Mã regime": decision.regime_id,
                    "Chiều": regimes_by_id[decision.regime_id].direction.value,
                    "Chuyến đầu": regimes_by_id[decision.regime_id].first_b_trip_id,
                    "Chuyến cuối": regimes_by_id[decision.regime_id].last_b_trip_id,
                    "Cửa sổ B": (
                        f"{format_hhmm(regimes_by_id[decision.regime_id].first_departure)}–"
                        f"{format_hhmm(regimes_by_id[decision.regime_id].last_departure)}"
                    ),
                    "Số chuyến B": regimes_by_id[decision.regime_id].trip_count,
                    "Thời lượng (phút)": (regimes_by_id[decision.regime_id].duration_minutes),
                    "Phân loại đều đặn": (
                        regimes_by_id[decision.regime_id].regularity_classification
                    ),
                    "Headway B đại diện": (
                        regimes_by_id[decision.regime_id].representative_b_headway
                    ),
                    "Headway B nhỏ nhất": (regimes_by_id[decision.regime_id].minimum_b_headway),
                    "Headway B lớn nhất": (regimes_by_id[decision.regime_id].maximum_b_headway),
                    "Chuỗi headway nội bộ": ", ".join(
                        f"{value:g}"
                        for value in regimes_by_id[decision.regime_id].internal_headway_sequence
                    ),
                    "Headway chuyển tiếp trước": (
                        regimes_by_id[decision.regime_id].transition_headway_before
                    ),
                    "Headway chuyển tiếp sau": (
                        regimes_by_id[decision.regime_id].transition_headway_after
                    ),
                    "Chuyến có quan sát dùng được": (
                        decision.evidence.trips_with_any_usable_observation
                    ),
                    "Chuyến đủ bao phủ": decision.evidence.coverage_eligible_trips,
                    "Tỷ lệ bao phủ regime": (decision.evidence.regime_trip_coverage_rate),
                    "Chuyến tải cao": decision.evidence.high_load_eligible_trips,
                    "Tỷ lệ chuyến tải cao": decision.evidence.high_load_trip_share,
                    "P85 tải nhỏ nhất": (decision.evidence.minimum_p85_load_factor),
                    "P85 tải trung vị": (decision.evidence.median_p85_load_factor),
                    "P85 tải lớn nhất": (decision.evidence.maximum_p85_load_factor),
                    "Chuyến P85 vượt maximum": (
                        decision.evidence.trips_above_maximum_load_factor_at_p85
                    ),
                    "Ngày dịch vụ": decision.evidence.total_distinct_service_dates,
                    "Ghép chính xác": decision.evidence.exact_match_count,
                    "Ghép trong dung sai": decision.evidence.tolerance_match_count,
                    "Bản ghi loại quy được": (decision.evidence.excluded_record_count),
                    "Quyết định": decision.classification,
                    "Mọi gate không đạt": ", ".join(decision.failed_gate_codes),
                    "Giới hạn bằng chứng": ", ".join(decision.evidence.evidence_limitations),
                }
                for decision in protected_assessment.decisions
            ],
            hide_index=True,
        )

        st.markdown("**Preview sàn dịch vụ tương lai — chưa thực thi**")
        if protected_assessment.protected_previews:
            st.dataframe(
                [
                    {
                        "Mã regime": preview.regime_id,
                        "Headway C tối đa (phút)": (preview.maximum_future_c_headway_minutes),
                        "Số chuyến C tối thiểu": (preview.minimum_future_c_trip_count),
                        "Bắt đầu cửa sổ": format_hhmm(preview.protected_window_start),
                        "Kết thúc cửa sổ": format_hhmm(preview.protected_window_end),
                        "Dung sai biên (phút)": (preview.future_boundary_tolerance_minutes),
                        "Cấm lấy chuyến làm donor": (preview.donor_removal_prohibited),
                        "Trạng thái thực thi": preview.enforcement_status,
                    }
                    for preview in protected_assessment.protected_previews
                ],
                hide_index=True,
            )
        else:
            st.info("Không có regime nào đạt toàn bộ gate để tạo preview sàn dịch vụ.")

    st.subheader("Trạng thái thực thi sàn dịch vụ 6A2B")
    enforcement_authority = st.session_state.get("protected_service_floor_enforcement_authority")
    enforcement_failure = st.session_state.get("protected_service_floor_enforcement_failure")
    outcomes = tuple(
        outcome
        for outcome in (unified_result.heuristic_outcome, unified_result.ortools_outcome)
        if outcome is not None
    )
    protected_rejection = any(
        outcome.diagnostic_candidate is not None
        and outcome.diagnostic_candidate.protected_service_floor_enforcement_fingerprint is not None
        for outcome in outcomes
    )
    protected_acceptance = any(
        outcome.solution is not None
        and outcome.solution.protected_service_floor_enforcement_fingerprint is not None
        for outcome in outcomes
    )
    if enforcement_failure is not None:
        st.error(
            f"{enforcement_failure.code}\n\nMã đối chiếu: {enforcement_failure.correlation_id}",
            icon=":material/error:",
        )
    elif enforcement_authority is None or not enforcement_authority.has_enforceable_regimes:
        st.info(PROTECTED_FLOOR_ENFORCEMENT_NO_REGIMES)
    elif protected_acceptance:
        st.success(PROTECTED_FLOOR_CANDIDATE_ACCEPTED, icon=":material/check_circle:")
    elif protected_rejection:
        st.warning(PROTECTED_FLOOR_CANDIDATE_REJECTED, icon=":material/warning:")
    else:
        st.info(PROTECTED_FLOOR_ENFORCEMENT_AUTHORITY_CURRENT)

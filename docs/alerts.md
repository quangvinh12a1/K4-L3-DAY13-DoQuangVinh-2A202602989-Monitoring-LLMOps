# Alert và Runbook

Mỗi alert dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ. Định nghĩa máy đọc được nằm ở [`config/alert_rules.yaml`](../config/alert_rules.yaml); nguồn dữ liệu là `data/logs.jsonl` và dashboard [`config/dashboard.yaml`](../config/dashboard.yaml).

## Alert 1

- Tên: `chat_latency_p95_slo_breach`
- Severity: P2-high
- Duration: 5 phút
- Kênh thông báo: Slack `#day13-llmops-oncall`
- SLI/SLO liên quan: `fast_successful_requests` — 99.5% request có `response_sent` với `latency_ms <= 3000` trong 28 ngày (`config/slo.yaml`).
- Điều kiện và thời gian duy trì: P95 `latency_ms` của `response_sent` > 3000 ms liên tục 5 phút.
- Ảnh hưởng tới người dùng: câu trả lời chậm rõ rệt; request chậm tiêu error budget của SLO chính.
- Ba bước kiểm tra đầu tiên:
  1. Dashboard panel **Latency**: P95/P99 tăng từ lúc nào; TTFT P95 có tăng cùng không (TTFT không đổi → chậm nằm ngoài LLM).
  2. Lọc log `response_sent` có `latency_ms > 3000` trong khoảng đó, lấy vài `correlation_id`.
  3. Mở trace có cùng `correlation_id` trên Langfuse, so duration của span `retrieval` và `llm-generation` trong waterfall.
- Mitigation tạm thời: nếu `retrieval` chậm — giảm timeout/top-k, bật cache kết quả retrieval, chuyển sang vector store dự phòng; nếu `llm-generation` chậm — giảm `max_tokens` hoặc chuyển model nhanh hơn; rollback prompt/deploy gần nhất nếu trùng thời điểm.
- Owner: Đỗ Quang Vinh (LLM platform on-call)

## Alert 2

- Tên: `chat_error_rate_high`
- Severity: P1-critical
- Duration: 5 phút
- Kênh thông báo: Slack `#day13-llmops-oncall`
- SLI/SLO liên quan: guardrail `error_rate_pct_max: 2`; request lỗi cũng tiêu error budget của `fast_successful_requests`.
- Điều kiện và thời gian duy trì: `count(request_failed) / count(request_received) * 100 > 2%` liên tục 5 phút.
- Ảnh hưởng tới người dùng: người dùng nhận HTTP 500, không có câu trả lời.
- Ba bước kiểm tra đầu tiên:
  1. Dashboard panel **Errors**: error rate, breakdown theo `error_type`, retrieval success có giảm không.
  2. Lọc log `request_failed`: xem `error_type`, `tool_name`, `tool_success=false`, `payload.detail`; ghi `correlation_id`.
  3. Mở trace cùng `correlation_id`: observation nào có level ERROR (vd `retrieval` báo `Vector store timeout`).
- Mitigation tạm thời: nếu lỗi ở retrieval — retry có backoff, fallback trả lời không dùng RAG kèm thông báo, chuyển vector store dự phòng; nếu do deploy/prompt mới — rollback label `production` về version trước.
- Owner: Đỗ Quang Vinh (LLM platform on-call)

## Alert 3

- Tên: `llm_cost_burn_rate_high`
- Severity: P3-medium
- Duration: 15 phút
- Kênh thông báo: Slack `#day13-llmops-cost`
- SLI/SLO liên quan: guardrail `daily_cost_usd_max: 2.5` (`config/slo.yaml`).
- Điều kiện và thời gian duy trì: chi phí 1 giờ gần nhất × 24 > 2.5 USD (dự báo vượt ngân sách ngày), duy trì 15 phút.
- Ảnh hưởng tới người dùng: chưa ảnh hưởng trực tiếp, nhưng vượt ngân sách có thể buộc giới hạn dịch vụ; thường đi kèm câu trả lời dài bất thường.
- Ba bước kiểm tra đầu tiên:
  1. Dashboard panel **Cost** và **Tokens**: cost/phút tăng do traffic tăng hay do `tokens_out` mỗi request tăng.
  2. Lọc log `response_sent` có `tokens_out` cao bất thường, ghi `correlation_id`, `feature`, `model`.
  3. Mở trace cùng `correlation_id`: kiểm tra usage/cost của `llm-generation`, prompt version đang dùng.
- Mitigation tạm thời: đặt `max_tokens`, rollback prompt version gây trả lời dài, rate-limit feature/user gây tăng đột biến, chuyển model rẻ hơn cho feature ít quan trọng.
- Owner: Đỗ Quang Vinh (LLM platform on-call)

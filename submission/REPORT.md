# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.
>
> ⬜ = phần học viên tự điền sau khi chạy Langfuse / challenge. Xóa các dấu ⬜ trước khi nộp.

## 1. Thông tin học viên

- **Họ và tên:** Đỗ Quang Vinh
- **MSSV:** 2A202602989
- **Lớp:** K4-L3A
- **Repository URL:** https://github.com/quangvinh12a1/K4-L3-DAY13-DoQuangVinh-2A202602989-Monitoring-LLMOps
- **Commit SHA cuối:** ⬜ (lấy bằng `git log -1 --format=%H` sau commit cuối)
- **Challenge ID:** ⬜ (`day13-k4-l3a-monitoring-llmops-v1` — xác nhận trong `config/challenge.json`)
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-2A202602989`

## 2. Evidence index

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | [`evidence/01-pytest.txt`](evidence/01-pytest.txt) |
| Log validator | [`evidence/02-log-validator.txt`](evidence/02-log-validator.txt) |
| Dashboard validator | [`evidence/03-dashboard-validator.txt`](evidence/03-dashboard-validator.txt) |
| Structured log | ⬜ `evidence/04-structured-log.png` |
| PII redaction | ⬜ `evidence/05-pii-redaction.png` |
| Trace list | ⬜ `evidence/06-trace-list.png` |
| Trace waterfall | ⬜ `evidence/07-trace-waterfall.png` |
| Trace metadata | ⬜ `evidence/08-trace-metadata.png` |
| Prompt versions | ⬜ `evidence/09-prompt-versions.png` |
| Prompt rollback | ⬜ `evidence/10-prompt-rollback.png` |
| Dashboard runtime | ⬜ `evidence/11-dashboard-overview.png` |
| Incident metric | ⬜ `evidence/12-incident-metric.png` |
| Incident log | ⬜ `evidence/13-incident-log.png` |
| Incident trace | ⬜ `evidence/14-incident-trace.png` |

## 3. Kết quả kỹ thuật

Baseline = starter chưa sửa, chạy `load_test.py --concurrency 5` (10 request mẫu). Kết quả cuối = sau khi hoàn thành CP1–CP2 trên cùng workload.

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 | 100/100 | Baseline: 20/21 record thiếu `correlation_id` (giá trị `MISSING`) và thiếu context; 0 correlation ID hợp lệ |
| `validate_dashboard.py` | 6/6 | 6/6 | Contract YAML đã hợp lệ từ đầu; dashboard runtime dựng bằng `scripts/build_dashboard.py` |
| `pytest` | 22 passed | 30 passed | Thêm 8 test: PII (CCCD, thẻ, hộ chiếu, địa chỉ, không false positive) và correlation/enrichment/request lỗi |
| Số traces hợp lệ | 0 (chưa bật Langfuse) | ⬜ | Đếm trên project `day13-k4-l3a-2A202602989` |
| Số PII leak | 0 | 0 | Log validator và test `test_api_logs_are_enriched_scrubbed...` |
| Latency P95 / TTFT P95 | ~152 ms / ~50 ms (log `response_sent`) | ~152 ms / ~50 ms | Instrumentation không làm tăng latency của agent |
| Retrieval success rate | 100% | 100% (bình thường); 0% khi practice `tool_fail` | `tool_success` được log ở `response_sent` và `request_failed` |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** `app/middleware.py` gọi `clear_contextvars()` đầu mỗi request, nhận `x-request-id` nếu hợp lệ (`^[A-Za-z0-9._-]{1,64}$`, chống log injection) hoặc sinh `req-<8 hex>`, `bind_contextvars(correlation_id=...)`, lưu vào `request.state`, trả lại header `x-request-id` và `x-response-time-ms`. `LabAgent.run` nhận cùng ID và gắn vào metadata trace. Request lỗi (HTTP 500) cũng trả `correlation_id` trong body.
- **Các metadata được ghi vào structured log:** `ts`, `level`, `service`, `event`, `correlation_id`, `user_id_hash` (SHA-256, 12 ký tự — không log `user_id` gốc), `session_id`, `feature`, `model`, `env`; với `response_sent` thêm `latency_ms`, `ttft_ms`, `tokens_in/out`, `cost_usd`, `quality_score`, `tool_name`, `tool_success`; `request_failed` có `error_type`.
- **Cách bảo đảm PII được scrub trước khi ghi:** processor `scrub_event` được đặt trong chain structlog **sau** `format_exc_info` và **trước** `JsonlFileProcessor`/`JSONRenderer`, scrub đệ quy mọi giá trị string (không chỉ `payload`). `app/pii.py` có rule email, thẻ (chạy trước CCCD để chuỗi 16 số không bị cắt), CCCD 12 số, SĐT Việt Nam (0/+84, có dấu cách/chấm/gạch), hộ chiếu, địa chỉ có số nhà + đường/phố/ngõ/hẻm.
- **Cách kiểm chứng kết quả:** `scripts/validate_logs.py` (detector PII độc lập với code scrub) báo 0 leak; `tests/test_pii.py` và `tests/test_logging_correlation.py` gửi request thật qua ASGI với email + số thẻ và kiểm tra file log không còn giá trị gốc.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** ⬜ (ảnh `06` thấy tên project `day13-k4-l3a-2A202602989`; `correlation_id` trong trace trùng với log do máy mình sinh)
- **Cấu trúc root/retrieval/generation observations:** root `lab-agent-run` (agent, trace name `day13-agent-request`) → con `retrieval` (retriever: input là query đã scrub, output là `doc_count`) → con `llm-generation` (generation: model, prompt đã link, `usage_details` input/output tokens, `cost_details`, `completion_start_time` = start + TTFT). `capture_input/capture_output=False` nên không gửi message/prompt thô chứa PII.
- **Cách nối trace với log:** `correlation_id` nằm trong metadata trace (qua `propagate_attributes`) và trong mọi log line của request → tìm trace bằng metadata filter `correlation_id`.
- **Prompt name:** `day13-chat`
- **Version/label baseline:** v1 — `baseline`, `production`
- **Version/label candidate:** v2 — `candidate`
- **Trace ID của mỗi version:** ⬜ v1: `...` · v2: `...`
- **Cách promote và rollback `production`:** ⬜ (chuyển label `production` v1 → v2 trên Langfuse, restart API, trace mới ghi version 2; chuyển về v1, restart, trace ghi version 1 — dán trace ID hai lần)

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** `scripts/build_dashboard.py` đọc `data/logs.jsonl` + `config/dashboard.yaml`, xuất `data/dashboard.html` (time range 60 phút, auto-refresh 30 s, đường threshold đỏ, đơn vị trên mỗi panel): Latency P50/P95/P99 + TTFT P95 (ms), Traffic (req/phút), Error rate + breakdown + retrieval success (%), Cost (USD, theo phút và cộng dồn), Tokens in/out (cộng dồn), Quality mean. Chạy `python scripts/build_dashboard.py --watch` để tự cập nhật. Ảnh runtime: ⬜ `evidence/11-dashboard-overview.png`.
- **SLO và lý do chọn:** `fast_successful_requests`: 99.5% request có `response_sent` với `latency_ms <= 3000` trong 28 ngày. Giữ 3000 ms vì baseline P95 ~152 ms còn nhiều headroom cho LLM thật, nhưng vẫn phát hiện được sự cố retrieval chậm (practice `rag_slow` đo được ~2654 ms/request, sát ngưỡng và vượt khi có request xếp hàng).
- **Cách tính error budget:** budget = (1 − 0.995) × tổng request 28 ngày; ví dụ 10.000 request → tối đa 50 request chậm hoặc lỗi. Burn rate = tỉ lệ bad event / 0.5%; error rate 2% trong 5 phút = burn 4×, nếu kéo dài sẽ tiêu hết budget 28 ngày trong ~7 ngày.
- **Ba alert và runbook tương ứng:** [`config/alert_rules.yaml`](../config/alert_rules.yaml), [`docs/alerts.md`](../docs/alerts.md):
  1. `chat_latency_p95_slo_breach` — P95 > 3000 ms trong 5 phút, P2-high.
  2. `chat_error_rate_high` — error rate > 2% trong 5 phút, P1-critical.
  3. `llm_cost_burn_rate_high` — chi phí 1 giờ × 24 > 2.5 USD trong 15 phút, P3-medium.

## 7. Điều tra challenge

⬜ Toàn bộ mục này điền sau khi Lab Coach gửi `config/challenge.json` và chạy `inject_incident.py` + `load_test.py --challenge --concurrency 5`.

- **Challenge ID:** ⬜
- **Khoảng thời gian điều tra:** ⬜
- **Triệu chứng từ metrics:** ⬜ (panel nào, giá trị bao nhiêu so với threshold)
- **Log line và correlation ID liên quan:** ⬜
- **Trace ID và span gây ảnh hưởng:** ⬜
- **Root cause:** ⬜
- **Fix action:** ⬜
- **Preventive measure:** ⬜

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** Scrub PII ở tầng processor của structlog (trước file writer) và scrub **mọi** field thay vì chỉ `payload`/`event`. Phương án khác là scrub ở từng chỗ gọi `log.info(...)`, nhưng dễ sót khi thêm log mới (vd `payload.detail` của exception chứa nội dung user). Đặt ở một điểm chung đảm bảo không đường ghi log nào bỏ qua được; test tích hợp gửi PII thật qua API để kiểm chứng.
- **Một lỗi/blocker đã gặp:** Khi request lỗi (practice `tool_fail`), `load_test.py` in `correlation_id = None` vì handler trả `HTTPException` không có ID trong body, làm khó tra log/trace đúng lúc cần nhất.
- **Cách tìm nguyên nhân và xử lý:** Đối chiếu response 500 với log `request_failed` (log vẫn có ID nhờ contextvars, header vẫn có `x-request-id`) → lỗi nằm ở body. Sửa handler trả `JSONResponse(500, {"detail", "correlation_id"})` và thêm test `test_failed_request_returns_and_logs_correlation_id`.
- **Cách hiểu luồng Metrics → Logs → Traces:** ⬜ (tự viết bằng lời của mình)
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:** ⬜ (tự viết)
- **Điều quan trọng nhất đã học:** ⬜ (tự viết)
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:** Endpoint `/chat` là `async` nhưng gọi `agent.run` đồng bộ nên chặn event loop: với `--concurrency 5` các request xếp hàng, latency phía client (~470–790 ms) cao hơn `latency_ms` của agent (~152 ms). Có thể chuyển sang `run_in_threadpool`. ⬜ (bổ sung nếu có)

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối.
- [ ] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [ ] Incident evidence nối đúng metric → log → trace.
- [ ] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [ ] Repository chạy lại được theo README.
- [ ] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.

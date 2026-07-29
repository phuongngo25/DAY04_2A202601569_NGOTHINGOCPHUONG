# Day 04 Lab v2 Report - Research Agent

## Team

| STT | Họ và tên            | Mã học viên | 
|-----|----------------------|-------------|
| 1   | Trần Thị Hoa Mai     | 2A202601317 | 
| 2   | Lương Thị Linh       | 2A202601015 | 
| 3   | Phạm Mai Anh         | 2A202601681 | 
| 4   | Cao Quế Phương       | 2A202601111 | 
| 5   | Ngô Thị Ngọc Phượng  | 2A202601569 | 

- Provider/model: Groq `openai/gpt-oss-120b` (mặc định), có thể override bằng `--model`

---

# PHẦN A - Giới thiệu agent

## A1. Agent này làm được gì

Research Agent tìm kiếm và tổng hợp thông tin qua nhiều tool: tìm trên web, đọc URL, tìm tweet theo chủ đề/tài khoản, hỏi lại khi thiếu thông tin, và xin xác nhận trước hành động có side effect như gửi Telegram.

**Link dùng thử:** local Streamlit UI

- `http://localhost:8501`

## A2. Tool agent có

| Tên tool | Làm được gì | Tool mới nhóm thêm? |
|---|---|---|
| clarify | Hỏi lại người dùng khi thiếu thông tin hoặc cần xác nhận yes/no trước hành động nhạy cảm | Không |
| timeline | Lấy các bài đăng gần đây của một tài khoản Twitter/X cụ thể | Không |
| social_search | Tìm bài đăng theo chủ đề trên Twitter/X | Không |
| lookup | Tra cứu thông tin trên web/bài báo | Không |
| fetch | Đọc nội dung của một URL cụ thể | Không |
| format | Trình bày item thành markdown digest | Không |
| send | Gửi nội dung lên Telegram sau khi đã xác nhận | Không |
| policy | Tra cứu company policy nội bộ | Không |
| papers | Tìm paper arXiv | Không |
| paper_text | Tải PDF arXiv và trích text cục bộ | Không |
| hn_search | Tìm bài trên Hacker News, dùng cho chủ đề kỹ thuật/dev | Có |

## A3. Câu hỏi mẫu để thử

1. Tìm tin AI hôm nay và tóm tắt 5 ý chính.
2. Tóm tắt bài viết này giúp mình.
3. Đăng bản tin này lên Telegram giúp mình.
4. Trên Hacker News, mọi người đang bàn gì về Rust?
5. Cho mình 3 bài Hacker News về Kubernetes có trên 100 điểm.

## A4. Kịch bản demo đã rehearse

| Scenario | Tool trace cần thấy | Câu chuyện cải thiện version | Fallback run/transcript |
|---|---|---|---|
| Normal research | `lookup` / `social_search`, sau đó `format` nếu cần | Từ v0 đến v2 cải thiện routing và argument extraction | `runs/v6_B_base_groq_20260729T114135874252.json` |
| Missing info | `clarify(response_type="text")` | Cải thiện quy tắc hỏi lại khi thiếu handle / URL | `transcripts/v6_groq_20260729T114802176111.transcript.json` |
| Sensitive action | `clarify(response_type="yes_no")` | Chặt boundary xác nhận trước hành động ghi ra ngoài | `runs/v6_B_base_groq_20260729T114135874252.json` |
| Group tool demo | `hn_search` | Thêm tool mới cho Hacker News, đổi declaration và system prompt | `runs/v6_B_group_groq_20260729T114248150848.json` |

---

# PHẦN B - Chi tiết / Bằng chứng

> Điều kiện metric hợp lệ: `provider_error_cases = 0`, `measured_cases = total_cases`, và các `tool_results` có error phải xem thủ công.

## B1. Version evidence

| Version | Prompt/tool change | Hypothesis | Metric name | Before | After | Run File |
|---|---|---|---|---:|---:|---|
| v0 | Baseline | Chưa tối ưu routing, boundary và argument conventions | case_accuracy | - | 0.70 | `runs/v0_B_base_groq_20260729T111423811494.json` |
| v1 | `system_prompt.md` | Làm rõ khi nào hỏi lại và khi nào có thể gọi nhiều tool | case_accuracy | 0.70 | 0.75 | `runs/v1_B_base_groq_20260729T112231397830.json` |
| v2 | `tools.yaml` | Viết rõ convention cho tham số: `query`, `timeframe`, `screenname`, `response_type` | case_accuracy | 0.75 | 0.85 | `runs/v2_B_base_groq_20260729T112553705829.json` |
| v3 | `system_prompt.md` | Siết boundary hỏi lại/xác nhận, nhưng bị regression ở một số case | case_accuracy | 0.85 | 0.55 | `runs/v3_B_base_groq_20260729T112934661923.json` |

Ghi chú:
- Sau v3, nhóm tiếp tục tối ưu đến v6.
- V4, v5, v6 cho thấy quay về ổn định và có thêm tool `hn_search`.

## B2. Failure analysis

| Case ID | Failure Type | Actual Tool Calls | What Failed | Fix |
|---|---|---|---|---|
| R03_web_news_routing | wrong_tool | `lookup` | Agent giữ nguyên query quá rộng, có lúc gặp `AI news today` thay vì rút gọn về `AI` | Cập nhật prompt/tool description để quy định cách cắt bớt từ mô tả đã được biểu diễn bởi `topic` và `timeframe` |
| R10_missing_handle | missing_info | `timeline` | Không hỏi lại handle, tự đoán biết người dùng nào | Nhấn mạnh rule: thiếu handle thì phải `clarify` trước |
| R12_confirm_before_send | wrong_boundary | `lookup` | Cần xác nhận yes/no trước hành động ghi ra ngoài nhưng agent chọn tool sai | Đưa confirmation boundary vào `clarify(response_type="yes_no")` và `tools.yaml` |
| R13_parallel_web_and_tweets | wrong_tool | `lookup` hoặc thiếu `social_search` | Yêu cầu đa nguồn nhưng agent chỉ gọi một tool | Nhắc mô tả tool và prompt: request đa nguồn phải gọi cả hai tool trong cùng lượt |

## B3. Team eval cases

`data/eval_group.json` hiện có đúng 10 case:

- 5 single-turn
- 5 multi-turn

| Case ID | What It Tests | Expected Tool/Behavior | Result |
|---|---|---|---|
| G01_hn_routing | Rẽ về đúng nguồn Hacker News | `hn_search(query="Rust")` | PASS trong suite group v6 |
| G02_points_and_limit_args | Trích đúng `min_points` và `limit` | `hn_search(query="Kubernetes", min_points=100, limit=3)` | PASS |
| G03_web_news_not_hn | Tin web chung thì dùng `lookup` | `lookup(query="AI", topic="news", timeframe="day")` | PASS |
| G04_missing_topic | Thiếu chủ đề thì hỏi lại | `clarify(response_type="text")` | PASS |
| G05_meta_question_no_tool | Câu hỏi meta không cần tool | `no_tool` | PASS |
| G06_switch_source_to_hn | Chuyển nguồn sang HN trong multi-turn | `hn_search(query="AI")` | PASS |
| G07_correct_points_threshold | Sửa ngưỡng điểm | `hn_search(query="LLM", min_points=200)` | PASS |
| G08_sort_by_recent_correction | Sửa `sort_by` và `limit` | `hn_search(query="WebAssembly", sort_by="recent", limit=3)` | PASS |
| G09_clarify_then_timeframe | Bổ sung thời gian sau khi hỏi lại | `hn_search(query="Postgres", timeframe="month", limit=5)` | PASS |
| G10_confirm_before_publish | Xác nhận trước khi publish | `clarify(response_type="yes_no")` | PASS |

Run evidence:

- `runs/v6_B_group_groq_20260729T114248150848.json`
- Summary: `case_accuracy = 1.0`, `tool_routing_accuracy = 1.0`, `argument_accuracy = 1.0`, `multiturn_accuracy = 1.0`

## B4. Live chat evidence

Transcript:

- `transcripts/v6_groq_20260729T114802176111.transcript.json`
- Số turn: 4

Nội dung thể hiện:

- Có một turn `waiting_for_user` cho trường hợp thiếu handle khi người dùng hỏi tìm tweet.
- Có evidence boundary/clarify trong chat, nhưng transcript này cũng cho thấy provider instability ở một số turn khác.

`transcript` được dùng để:

- kiểm tra luồng hỏi lại
- kiểm tra user/assistant history
- lưu tool rounds và tool events

## B5. Tool capability evidence

| Category | Evidence File | What Worked | Risk / Guardrail |
|---|---|---|---|
| Must-have: tool mới đầu tiên | `tools/hn_search/TOOL.md`, `tools/hn_search/tool.py`, `artifacts/tools.yaml`, `tools/__init__.py`, `runs/v6_B_group_groq_20260729T114248150848.json` | Agent gọi đúng `hn_search` trong group suite, bao gồm routing, argument extraction và multi-turn correction | Cần giữ `query` sạch, không lặp lại câu mô tả, và phải xác định `sort_by`/`timeframe` đúng convention |
| Optional built-in | `tools/policy`, `tools/papers`, `tools/paper_text`, `tools/send` | Có declaration sẵn trong repo cho extension/demo | `send` phải luôn đi qua `clarify(response_type="yes_no")` |
| Bonus: tool mới thứ 4 trở đi | Chưa có thêm tool mới nào ngoài `hn_search` | - | Để bonus, cần thêm tool và cập nhật đồng bộ prompt, `tools.yaml` và eval |

## B6. Reflection

- Fix nên nằm trong `system_prompt.md` khi cần điều chỉnh khi nào hỏi lại, khi nào gọi nhiều tool, và boundary của hành động có side effect.
- Fix nên nằm trong `tools.yaml` khi cần làm rõ convention của tham số như `screenname`, `query`, `timeframe`, `sort_by`, `response_type`.
- Failure cần manual review nhiều nhất là `tool_results` có error, vì routing có thể đúng nhưng tool thực thi vẫn có thể fail do API/credential.
- Bước tiếp theo nên làm:
  - hoàn thiện screenshot/demo cho UI
  - bổ sung một vài run bằng provider ổn định nhất
  - nếu cần bonus, thêm một tool mới và ghi lại version log

---

## Appendix - current artifact snapshot

- Base runs: `v0` đến `v6`
- Group suite: 10/10 PASS
- Extension suite: 6/10 PASS
- Current UI: `app.py`

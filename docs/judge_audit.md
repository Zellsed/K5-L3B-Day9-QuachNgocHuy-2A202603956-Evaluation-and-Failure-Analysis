# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | đạt | dùng làm diagnostic judge; vẫn giữ code grader cho money/approval |
| helpful | 100 | 0.375 | 1.000 | 0.300 | không đạt (κ, recall) | loại khỏi gate |

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 1 | H-008 | PASS | FAIL | người | Judge bỏ qua lời hứa hoàn tiền thiếu bằng chứng; rubric cần yêu cầu căn cứ/trạng thái refund. |
| 2 | H-017 | PASS | FAIL | người | Reply khẳng định 25.000đ không có evidence; thêm check amount/ledger hoặc citation. |
| 3 | H-029 | PASS | FAIL | người | “đang xử lý” nhưng yêu cầu người dùng không nhắn thêm là không phù hợp tone; rubric phải nêu hành vi bị cấm. |
| 4 | H-042 | FAIL | PASS | người | Reply lịch sự, nêu đúng số tiền và thời gian chờ; giảm phạt các câu ngắn nhưng đầy đủ. |
| 5 | H-051 | FAIL | PASS | người | Từ “refund” không làm tone kém; normalise từ vựng Anh–Việt trước judge. |

## Kết luận
- `helpful` bị loại: TP=9, FP=0, FN=21, TN=70; recall 0.30 bỏ lọt 70% ca FAIL và κ=0.375 dưới floor 0.6. Precision 1.0 không cứu được một judge gần như không phát hiện lỗi.
- `tone_ok` được dùng ở mức diagnostic: TP=24, FP=4, FN=6, TN=66; đạt cả κ=0.757, P=0.857, R=0.8. Không dùng cho tiền/approval vì các điều đó có oracle code rõ ràng.
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay đã công khai; cần nhãn người mới để có held-out thật.

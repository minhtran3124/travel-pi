# Nghiên cứu: cấu trúc câu trả lời cho chatbot trợ lý du lịch thân thiện

> Nguồn: deep-research harness (6 góc nghiên cứu · 26 nguồn · 112 claim → 25 xác minh:
> 19 xác nhận, 6 bác bỏ qua bỏ phiếu đối kháng 3 phiếu). Ngày: 2026-06-27.
> Câu hỏi: khi nào và cách dùng tiêu đề, gạch đầu dòng, in đậm/điểm nhấn, và tóm tắt
> đưa thông tin quan trọng nhất lên trước; khảo sát cách các trợ lý du lịch AI hàng đầu
> định dạng câu trả lời; định dạng nên thích ứng ra sao giữa giao diện chat thuần và
> giao diện phong phú (rich UI).

## Kết luận cốt lõi

Trả lời thẳng vào vấn đề trước, giữ ngắn gọn và dễ quét mắt, rồi mới mở rộng chi tiết
khi cần. Người dùng coi chat của trợ lý như **một ô tìm kiếm, không phải cuộc trò
chuyện** — "câu trả lời dài hơn *không* phải là câu trả lời tốt hơn." Dùng tiêu đề /
gạch đầu dòng / in đậm để dễ quét, nhưng đừng định dạng quá đà với câu trả lời ngắn.
Khi giao diện hỗ trợ thành phần phong phú (thẻ/chip), thẻ tóm tắt-trước vượt trội hơn
hẳn markdown thuần.

## Các phát hiện đã xác minh (độ tin cậy cao trừ khi ghi chú)

**1. Trả lời thẳng vào vấn đề; người dùng hành xử như người tìm kiếm.** [3-0]
NN/g *Less Chat, More Answer* (2026): người dùng "tiếp cận chatbot website giống như
thanh tìm kiếm… thích câu trả lời quét mắt được nhanh"; câu trả lời dài hơn không được
đánh giá tốt hơn.
→ https://www.nngroup.com/articles/less-chat-more-answer/

**2. Quan trọng-nhất-trước — "kim tự tháp cụt" cho chat.** [3-0]
Kim tự tháp ngược cổ điển (đáp án → chi tiết → liên kết), nhưng riêng với chat: đưa
*chỉ* phần đáp án thiết yếu trước, rồi đẩy bối cảnh/trường hợp biên ra sau qua **gợi ý
câu hỏi tiếp theo** (tiết lộ dần) thay vì dồn tất cả lên đầu.
→ NN/g (trên) · https://www.nngroup.com/articles/concise-scannable-and-objective-how-to-write-for-the-web/ · https://cobbai.com/blog/chatbot-response-tuning

**3. Làm cho dễ quét: tiêu đề, gạch đầu dòng ngắn, in đậm, khoảng trắng.** [3-0]
Người dùng quét, không đọc kỹ (79% quét vs 16% đọc từng chữ). Viết súc tích + dễ quét
+ khách quan đo được **+124% khả dụng** (súc tích +58%, dễ quét +47%, khách quan +27%;
Morkes & Nielsen). Áp vào chat: câu ngắn, đoạn ≤2–3 câu.
→ NN/g concise-scannable · Less Chat More Answer · https://quickchat.ai/post/improve-chatbot-engagement

**4. Giữ tin nhắn ngắn / chia nhỏ; tránh "bức tường chữ".** [trung bình]
Khối dài gây quá tải, nhất là trên di động; chia thành phần dễ tiêu hóa. Mục tiêu ~60
từ cho di động và quy tắc "hai tin 40 từ tốt hơn một khối 80 từ" — con số chính xác chỉ
từ một nguồn (coi là định hướng). "Tránh khối dày đặc" thì vững; "phải tách nhiều bong
bóng" thì không (trợ lý hàng đầu thích *một* tin có cấu trúc tốt).
→ cobbai · https://fuselabcreative.com/chatbot-interface-design-guide/ · quickchat · https://www.lazarev.agency/articles/chatbot-ui-examples

**5. Hiển thị dưới dạng markdown, không phải văn bản thuần.** [3-0]
LLM tự nhiên xuất markdown (tiêu đề, danh sách, in đậm, bảng); render văn bản thuần
"lãng phí cấu trúc mà mô hình đang cung cấp."
→ https://docs.langchain.com/oss/javascript/langchain/frontend/markdown-messages · arXiv 2604.09577

**6. Điều chỉnh định dạng theo giao diện — rich UI thắng markdown khi có sẵn.** [3-0]
Google Research (arXiv 2604.09577, *Generative UI*): giao diện tương tác được ưa thích
**82.8%** so với chat markdown và **97.0%** so với văn bản thuần. → thẻ tóm tắt/chip +
tiết lộ dần khi giao diện hỗ trợ; markdown ngắn dễ quét khi chỉ có chat. (Lưu ý: so sánh
*rich UI đầy đủ vs văn bản*, không phải thủ thuật trong nội bộ chat.)
→ https://arxiv.org/html/2604.09577v1 · lazarev

## Các công cụ khác — cách trợ lý du lịch hàng đầu định dạng [3-0]

- **Mindtrip** — câu trả lời thành **thẻ phân loại/có tab**: Overview, Guides, Stays,
  Restaurants, Things to do, Reviews, Location. Thẻ địa điểm gắn liền trong chat.
- **Layla** — gói chuyến đi dạng **thẻ tóm tắt-trước**: dẫn đầu bằng
  `3 ngày · 1 thành phố · 20 trải nghiệm · 1 khách sạn · ~$1,548`, rồi mở rộng chi tiết
  từng ngày kèm tùy chọn tinh chỉnh.
- **ChatGPT/Claude** — ưu tiên *một* tin nhắn có cấu trúc hơn nhiều bong bóng.
→ https://aitravel.tools/mindtrip-review/ · https://aitravel.tools/layla-ai-review/ · https://www.imean.ai/blog/articles/chatgpt-vs-mindtrip-vs-layla-vs-imean-ai-i-tested-5-ai-trip-planners-on-the-same-route/

Khuôn mẫu chung: **tóm tắt-trước + thẻ phân loại + tiết lộ dần.**

## Đã bị bác bỏ (đừng dựa vào)

- "Định dạng quá đà mọi thứ" — chống chỉ định **"bức tường gạch đầu dòng"** là có thật;
  người dùng ChatGPT phàn nàn nó gạch đầu dòng cả văn xuôi. Định dạng thừa = nhiễu thị
  giác. [diễn đàn community.openai.com]
- Thủ thuật cụ thể gán cho Layla (in đậm giá, gạch đầu dòng hạng mục ngân sách) — **không
  qua xác minh** (1-2).
- "Mindtrip chủ yếu là bản đồ, không phải văn bản" — bác bỏ (1-2).
- "Định dạng phải chỉ định qua hướng dẫn markdown trong Knowledge Base" — bác bỏ (0-3);
  LLM hiện đại tự định dạng.

## Lưu ý / Hạn chế

Nguyên tắc nền tảng dựa trên nghiên cứu gốc NN/g (mạnh). Con số +124% từ nghiên cứu nhỏ
1997 (đã tái xác nhận). Con số 82.8%/97.0% từ preprint 2026 so sánh *rich UI vs văn bản*,
không phải thủ thuật trong chat. Quy tắc độ dài và quan sát sản phẩm từ blog nhà cung
cấp/đánh giá — đúng hướng nhưng con số chính xác chỉ một nguồn. Bối cảnh LLM/UI thay đổi
nhanh; nguồn 2026 là mới tại thời điểm báo cáo.

## Câu hỏi còn mở

- Trong một tin nhắn chat (không rich UI), tách câu trả lời phức tạp thành nhiều bong
  bóng có thực sự thắng một tin có cấu trúc tốt? (bằng chứng 2-1, cần test riêng cho
  domain du lịch).
- Ngưỡng độ dài/mật độ tối ưu cho câu trả lời du lịch (lịch trình, so sánh nhiều lựa
  chọn) trên di động vs desktop là bao nhiêu?
- Định dạng nên "xuống cấp duyên dáng" thế nào khi cùng một payload phục vụ cả chat
  markdown lẫn rich-card UI?
- Định dạng nặng (tiêu đề/đậm/bullet) bắt đầu gây hại khi nào — ranh giới giữa thân thiện
  và "quá cấu trúc"?

## Hệ quả với agent của dự án

`app/prompts/communication_style/v1.md` ban đầu cấm tiêu đề markdown (`##`/`###`) và bảng
— quy tắc đó kế thừa từ tham chiếu mizumi vốn nhắm WhatsApp (văn bản thuần). Web app của
ta render markdown (dependency `streamdown`), nên nghiên cứu khuyến nghị **đón nhận cấu
trúc nhẹ** thay vì cấm:

- **Tóm tắt-trước**: dẫn đầu bằng thông tin chính (tổng chi phí, lựa chọn hàng đầu, kết
  luận), rồi mới chi tiết.
- **Cho phép** in đậm điểm nhấn + gạch đầu dòng ngắn; **tiêu đề nhỏ chỉ** cho câu trả lời
  dài/nhiều phần (vd lịch trình nhiều ngày).
- **Rào chắn chống định dạng quá đà**: không bullet câu trả lời 2 câu; văn xuôi cho câu
  đơn giản, chỉ dùng cấu trúc khi nội dung thực sự dạng danh sách/nhiều phần.

Áp dụng tại `app/prompts/communication_style/v1.md` (nhánh `feat/agent-friendly-prompts`).

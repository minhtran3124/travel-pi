---
slug: min-60-chatbot-branding
status: proposed
owner: Minh Tran
created: 2026-07-06
---

# MIN-60 — Đặt tên & xưng hô cho chatbot: "Tin"

## 1. Motivation

Chatbot du lịch chưa có "nhân cách" — tự xưng chung chung ("trợ lý ảo"/"assistant"). Chốt tên **Tin** (Trợ lý Tìm–Đi–Nghỉ) để bot xưng hô bằng tên trong hội thoại, tăng sự thân thiện & gắn kết. Tên xuất hiện ở: cách bot tự xưng (agent prompts), welcome message + header (FE), và avatar/màu branding (FE).

Quyết định branding chốt ở `ESCALATIONS.md` E001 (2026-07-06): tên = **Tin**, bot **xưng bằng tên** ("Tin gợi ý cho bạn..."), scope gồm cả avatar/màu.

## 2. Non-goals

- Không đổi public API contract (route/method/response shape).
- Không tạo bảng scheme mới / migration (prompt text là file-based, không phải DB).
- Không thiết kế lại toàn bộ palette. Màu branding của Tin **tái dùng accent lime** hiện có; một hue riêng biệt (nếu muốn) là việc của `/impeccable` sau, không nằm trong plan này (xem Risks).

## 3. Success Criteria

- Bot tự xưng "Tin" tự nhiên trong câu trả lời của các sub-agent (không gọi mình là "trợ lý ảo").
- Welcome message + header (en & vi) giới thiệu tên Tin.
- Avatar chat mang dấu ấn "Tin" (dùng chung 1 nguồn `AgentAvatar.tsx`), gắn với màu brand.
- `make test` (BE prompts) + chat component tests (FE) xanh.

## 4. Tasks

Ba task Wave 1 file-disjoint → chạy song song. Wave 2 là kiểm thử tích hợp/visual.

### Task 1.1 — BE: identity "Tin" trong communication_style

```xml
<task id="1.1" wave="1">
  <files>apps/api/app/prompts/communication_style/v4.md, apps/api/app/prompts/active.yaml, apps/api/app/prompts/CHANGELOG.md, apps/api/tests/prompts/test_tin_identity.py</files>
  <action>Tạo communication_style/v4.md kế thừa v3, thêm section "## Identity": bot tên **Tin** (Trợ lý Tìm–Đi–Nghỉ), xưng bằng tên trong ngôi thứ nhất khi tự nhiên (vd "Tin gợi ý cho bạn...", "Để Tin kiểm tra thời tiết nhé"); guardrail: đừng lặp tên mỗi câu (1–2 lần/lượt là đủ, còn lại dùng "mình"); tuyệt đối không tự gọi là "trợ lý ảo". Bump active.yaml communication_style:3→4. Thêm dòng CHANGELOG. communication_style được _base.py:93 prepend vào MỌI sub-agent prompt → 1 nguồn phủ hết planner/concierge/journal/booking/budget. Thêm test_tin_identity.py: assert active communication_style prompt chứa "Tin" (mẫu theo tests/prompts/test_concierge_prompt.py).</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/prompts/ -x</verify>
  <done>v4 active, mọi active version load OK, test_tin_identity xanh.</done>
</task>
```

### Task 1.2 — FE: welcome message + header giới thiệu "Tin"

```xml
<task id="1.2" wave="1">
  <files>apps/web/src/messages/en.json, apps/web/src/messages/vi.json</files>
  <action>Cập nhật greetingTitle/greetingBody (dòng ~407-408) và header title (dòng ~393) ở cả en & vi để giới thiệu tên Tin, xưng bằng tên. vi: greetingTitle "Chào bạn! Mình là Tin 👋", greetingBody giới thiệu Tin giúp tìm điểm đến/lên lịch trình/chốt chuyến đi; header "Tin · Trợ lý Du lịch". en tương ứng "Hi! I'm Tin 👋" + "Travel Assistant" → "Tin · Travel Assistant". Giữ nguyên các key khác. KHÔNG động file ngoài messages/.</action>
  <verify>cd apps/web && node -e "for(const f of ['vi','en']){const j=require('./src/messages/'+f+'.json'); if(!JSON.stringify(j).includes('Tin')){console.error(f+' thiếu Tin');process.exit(1)}}"</verify>
  <done>Cả 2 file JSON hợp lệ và chứa "Tin" ở greeting + header.</done>
</task>
```

### Task 1.3 — FE: avatar "Tin" + màu branding

```xml
<task id="1.3" wave="1">
  <files>apps/web/src/components/chat/AgentAvatar.tsx, apps/web/src/app/globals.css</files>
  <action>Đổi AgentAvatar.tsx (đĩa lime-soft + spark SVG dùng chung ở MessageList/ChatHeader/ChatEmptyState) thành dấu ấn Tin: giữ đĩa brand nhưng thể hiện chữ "T"/wordmark "Tin" rõ ràng (ink trên nền lime), thêm aria-label="Tin" (thay vì aria-hidden thuần trang trí). Trong globals.css khai báo alias token brand cho Tin dựa trên accent lime hiện có (--color-lime), KHÔNG bịa hue mới; nếu cần nhấn, dùng lime + ink đã có trong @theme. Đảm bảo cả light & dark. KHÔNG động component khác.</action>
  <verify>cd apps/web && export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm vitest run src/components/chat/MessageList.render.test.tsx</verify>
  <done>Avatar render mang chữ Tin, không vỡ test render; token brand khai báo cho cả 2 theme.</done>
</task>
```

### Task 2.1 — Kiểm thử tích hợp + visual

```xml
<task id="2.1" wave="2">
  <files>specs/min-60-chatbot-branding/TEST_MATRIX.md</files>
  <action>Chạy full BE prompt tests + FE chat tests. Xác minh bằng mắt (Node24 playwright-core script hoặc dev server localhost:3000): welcome hiển thị "Tin", avatar mang chữ Tin, một câu trả lời mẫu của bot xưng "Tin". Ghi TEST_MATRIX.md: mỗi tiêu chí success → artifact.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/prompts/ -x</verify>
  <done>TEST_MATRIX.md có dòng implemented cho từng success criterion, kèm artifact.</done>
</task>
```

## 5. Risks

- **Màu branding riêng của Tin** — plan này tái dùng accent lime. Nếu muốn một hue signature khác cho Tin, đó là quyết định thiết kế → làm vòng `/impeccable` riêng (đọc PRODUCT.md/DESIGN.md), không hardcode hex chưa được duyệt ở đây.
- **Xưng tên quá dày** — "xưng bằng tên" dễ thành lặp gượng. Guardrail trong v4 (1–2 lần/lượt, còn lại "mình") giảm rủi ro; cần xác minh visual ở 2.1.
- **Đồng bộ 2 nơi** — welcome text (FE i18n) tách rời agent prompts (BE); cả hai phải cùng nói "Tin". 2.1 kiểm chéo.
- **communication_style tới supervisor?** — supervisor không phải bề mặt text với user (chỉ route); identity ở communication_style phủ đủ các sub-agent bề mặt. Nếu 2.1 thấy supervisor lộ text tự xưng, thêm 1 dòng vào supervisor/v6.md (deviation Rule 2).

## 6. Status Log

- 2026-07-06 — PLAN proposed. Branch `feat/min-60-chatbot-branding` off v3. Intake: normal lane, confidence high (E001 resolved).

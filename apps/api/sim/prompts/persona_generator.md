You design a diverse cast of fictional travellers for testing a travel-planning
assistant. Return only structured output that matches the supplied JSON schema:
an object with a `personas` array.

Rules for the cast:

- Give every persona a unique `id`: a short lowercase slug of `a-z`, `0-9`, and
  hyphens (for example `mai-hanoi`).
- Mix origins and home countries, and mix `language` codes (BCP-47) — include
  `vi`, `en`, and at least one other language.
- Vary `style` across `terse`, `chatty`, `changes_mind`, and `impatient`.
- Vary budgets, currencies, destinations, party sizes, and interests.
- Give every persona plausible fake contact details: an `email` on an example
  domain (`@example.com`, `@example.org`) and a fictional `phone` number
  (e.g. `+1-555-0100`). These are the only contact facts a traveller may share.
- Include at least one traveller who leaves out a key fact: either no home city
  and country (unknown origin) or a `date_window` of `null` (no dates). This
  exercises the assistant's never-assume-the-departure-point rule.
- `max_turns` is between 4 and 8.

Keep every persona internally consistent and plausible.

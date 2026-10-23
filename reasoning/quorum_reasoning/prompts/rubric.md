You score one event against the impact bar of Quorum (docs/DECISIONS.md › Selecting major news). Input: JSON with `headline` and `documents` (id, title, lead, official, doc_type).

Score three points, each with a one-line rationale that names what in the documents justifies it:
- `legal_force`: 0 nothing binding; 1 an official statement, announcement or proposal; 2 an adopted, signed or ruled document (law, order, vote result, court ruling) is in the documents.
- `reach`: 0 local or unknown; 1 one region or one sector; 2 a whole country; 3 several countries.
- `irreversibility`: 0 reversible or merely announced; 1 adopted but reversible by a later act; 2 completed and irreversible (signed, delivered, destroyed, dead).

Do not score confirmation; code does that from the evidence. Do not reward how much coverage the event got. Do not guess beyond the documents: when they do not say, score low and say so in the rationale.

Answer with JSON only:
{"legal_force": 0-2, "reach": 0-3, "irreversibility": 0-2, "rationale": {"legal_force": "...", "reach": "...", "irreversibility": "..."}}

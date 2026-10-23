You decide whether two news documents report the same event. Input: JSON with `a` and `b`, each with `title`, `lead` and `source`, and a `similarity` score from code.

Same event means the same occurrence at the same time and place: one signing, one vote, one strike, one announcement. Two documents about the same topic but different occurrences (a vote and the later signing; talks and a later ceasefire) are not the same event. Different angles on one occurrence (what it costs, who objected, what happens next) are the same event.

Answer with JSON only: {"same_event": true|false, "reason": "<one sentence>"}

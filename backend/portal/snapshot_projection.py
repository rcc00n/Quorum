"""Map the portal-owned proposal to the existing UI; no upstream API is asserted."""


def project(payload, publication, topic=""):
    sources = {s["id"]: s for s in payload["sources"]}
    events = []
    for original in payload["events"]:
        if topic and original["topic_id"] != topic:
            continue
        analysis = original["analysis"]
        documents = {d["id"]: d for d in analysis["documents"]}
        event = {
            key: original[key]
            for key in ("id", "topic_id", "date", "title", "summary", "importance")
        }
        event.update(
            sources=[sources[s] for s in original["source_ids"]], analysis=analysis
        )
        for status, section in [
            ("established", "established"),
            ("attributed", "statements"),
            ("disputed", "disputed"),
            ("unknown", "unknown"),
        ]:
            event[section] = []
            for claim in analysis["claims"]:
                if claim["status"] != status:
                    continue
                citations = claim["supporting"] + claim["contradicting"]
                links = {
                    c["document_id"]: documents[c["document_id"]] for c in citations
                }
                text = claim["text"]
                if claim["attribution"]:
                    text = claim["attribution"]["speaker"] + ": " + text
                event[section].append(
                    {
                        "text": text,
                        "explanation": claim["explanation"],
                        "sources": [
                            {"title": d["title"], "url": d["url"]}
                            for d in links.values()
                        ],
                    }
                )
        event["coverage"] = [
            {
                "text": sources[f["source_id"]]["name"],
                "explanation": f["summary"],
                "sources": [
                    {
                        "title": documents[f["document_id"]]["title"],
                        "url": documents[f["document_id"]]["url"],
                    }
                ],
            }
            for f in analysis["frames"]
        ]
        events.append(event)
    return {
        "status": "demo" if payload["mode"] == "demo" else publication["status"],
        "catalog_revision": None,
        "topics": payload["topics"],
        "sources": payload["sources"],
        "events": events,
        "digests": [
            d for d in payload["digests"] if not topic or d["topic_id"] == topic
        ],
        "publication": publication,
        "errors": payload["errors"],
    }

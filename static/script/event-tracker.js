// Lightweight fire-and-forget user interaction tracker.
// Call logEvent(type, action, details) anywhere to append an entry to log/event_log.jsonl.
function logEvent(type, action, details) {
    const body = { type, action };
    if (details !== undefined && details !== null) body.details = details;
    fetch('/event_log', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    }).catch(() => {});
}

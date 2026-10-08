"""The effective view of the event log.

The log is append-only, so undoing a turn appends a ``turn.retracted`` event
instead of deleting anything. The *effective* log is every event except those
of retracted turns. Every reader of history (conversation history, prompts,
state rebuilding, replay checks) goes through this one definition, so no path
can forget that a turn was taken back.
"""

RETRACTED_KIND = "turn.retracted"

_RETRACTED_TURNS = f"SELECT json_extract(payload, '$.turn') FROM events WHERE kind = '{RETRACTED_KIND}'"

# SQL condition on an ``events`` row aliased ``e``: the event belongs to no retracted turn.
EFFECTIVE = f"(e.turn_id IS NULL OR e.turn_id NOT IN ({_RETRACTED_TURNS}))"

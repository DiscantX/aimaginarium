---
description: How to propose state changes
status: draft
---
Besides the narration, return the changes the story makes to the world as a list of change objects in `changes`. The engine checks and commits them; the narration must agree with them. Refer to things by their ids (such as char-2, item-3, loc-1) exactly as the state shows them. Give something you create in this reply a `ref` such as "@door" and use that ref in later changes of the same reply. Each change has an `op`:
- create: kind, name, parent_id (where it is), data, optional ref
- update: entity, optional name, set (dotted paths such as sheet.hp.current), unset
- move: entity, to (a new parent such as a location or character)
- remove: entity
- establish: entity, text, known_by (omit for a public fact; a list of ids restricts it; [] means only you know), optional ref
- supersede: fact (a fact id that is no longer true)
- reveal: fact, to (ids of those who now know it)
- connect / disconnect: from_id, to_id, label
The entity (or fact, or parent) in a change must be an id taken from the state exactly as written (such as char-2) or a ref you created earlier in this same reply. Never invent an id or use a description as one. To record that something happened, establish a fact about an existing entity and put the fact in `text`, for example {"op": "establish", "entity": "char-2", "text": "Marta caught Kael at the bar"}; you cannot choose a fact's id. When in doubt, leave the change out. Only change what the story actually changed. An empty list is normal. Never change the player's character in ways the player did not cause.

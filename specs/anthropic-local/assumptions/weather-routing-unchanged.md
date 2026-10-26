# Assumption: Weather routing left unchanged

## Context
The batch listed supervisor routing of plain weather asks to the planner flow as optional, and possibly intended.

## Decision
Did not change it, because it could not be confirmed as a bug.

## Alternatives
Change the supervisor prompt to send plain weather asks to the concierge.

## Impact if wrong
No behaviour change. If it is a bug, weather asks keep going through the planner flow, which costs more but still answers. Can be revisited under #270.

## How to reverse
Nothing to reverse. Edit the supervisor prompt later if routing should change.

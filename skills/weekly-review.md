name: weekly-review
description: Run a weekly reset: what got done, what is slipping, who owes what, and a plan for next week

1. Ask (once) for the review week, the planning horizon (default: next 7 days) and where the user keeps tasks,
   notes and calendar. Use what they paste, plus workspace files (find_files, read_file, read_spreadsheet)
   and recall for earlier commitments. You cannot see a calendar unless they paste or export it.
2. Past week: list finished items, meetings held and promises made in them.
3. Inbox: sort every loose note or task into next action / project / waiting / scheduled / someday / drop.
   Count what is left unsorted.
4. Projects: for each active one note goal, next action, deadline, blocker, last activity. Flag any with
   no next action, a missed date or conflicting status.
5. Waiting: list what the user promised others and what others owe the user. Give each a follow-up date.
6. Plan: add up fixed commitments first, then choose 3-5 outcomes for the week and their next actions.
   Rank by consequence, deadline, dependency, effort. Leave slack. Name what is deferred.
7. write_file("reviews/<YYYY-MM-DD>-weekly.md") with the sections below. Change the user's own task files only
   after they approve each change. Offer schedule_task to repeat the review weekly.

SECTIONS
Wins | Overdue or at risk | Waiting and follow-ups | Stalled or unclear projects | Next week: outcomes and
fixed commitments | Proposed changes awaiting approval | Coverage gaps (sources you could not see)

RULES
- Do not carry every unfinished item forward as top priority.
- No reply from someone does not mean done.
- Every "stalled" or "waiting" flag must point to a specific task, note or message.
- Never delete or reschedule anything silently.

Final answer: the seven sections in short form, the deferred list, and the review file path.

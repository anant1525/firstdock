<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved. -->
<!-- SPDX-License-Identifier: MIT-0 -->
# Gap list

The challenge brief scores this file ("What to bring to judging", item 6):
*"what you could not close, and why. This is scored, and it scores well: one
honest failure beats a wall of green ticks."*

Delete this template text and write your own. One entry per gap — a control
you did not finish, an auditor question you can only partially answer, an
evidence surface you could not reach, a decision you made under time
pressure that a real deployment would need to revisit.

## Format

For each gap:

```
### <short title>

**What's missing:** one sentence.
**Why:** what actually stopped you — a platform limit, a time-box, a design
choice you'd reconsider. Be specific; "ran out of time" is fine if it's true,
but say what you would have done with more of it.
**Impact:** what an auditor cannot do because of this gap.
**If you had one more day:** the concrete next step.
```

## Example (delete before submitting)

### Control 9 (drift) has no frozen baseline yet

**What's missing:** `evaluate.py` has no metric function for control 9; the
register entry is still a placeholder.
**Why:** the diagnostic-quality measure we picked (disposition-match-rate
against `score-run.py`'s expected disposition) needs at least three
baseline runs to freeze a number against, and we spent our first two hours
on control 16 instead.
**Impact:** a judge asking "is control 9 satisfied for this run" gets no
verdict, only the raw disposition.
**If you had one more day:** run the three baseline scenarios, freeze the
match-rate as the threshold, and wire `_control_9_drift` into
`evaluate.py`'s `_METRICS` table the same way control 16 is wired.

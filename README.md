# AI Decision Intelligence

An agent that turns a vague request into a decision a person can approve, execute, and learn from.

It does not pick an action and stop. Each pass frames the decision, collects the evidence, scores the alternatives against the constraints, writes a brief, and waits. After the work ships, the outcome is compared with the estimate and the miss becomes a prior for the next decision of the same kind.

Product discovery finds the opportunity. Experimentation tests whether it is real. This agent is the layer that decides what to do, under the constraints the organization actually has.

```
Decision request
        ↓
Context & evidence
        ↓
Decision framing
        ↓
Alternatives          Constraints
        └──────┬───────┘
               ↓
     Scenario simulation
               ↓
     Risk & uncertainty
               ↓
       Decision brief
               ↓
   Human decision / approval
               ↓
      Execute decision
               ↓
      Outcome tracking
               ↓
    Learn & re-evaluate
```

## Run the sample

The sample is Harbor, a fictional payments company, deciding whether the billing service should migrate.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
decide demo
decide serve
```

Open http://127.0.0.1:8000. Approve partial migration, mark the plan done, record what happened, and write the lesson. The next migration you frame will carry that lesson.

## Framing

A request and the constraints around it become a decision, before any option is scored.

```
Decision:
Should service X migrate?

Objective:
Reduce operational cost and deployment time.

Options:
A. Do nothing
B. Partial migration
C. Full migration
D. Managed billing service

Constraints:
- 3 engineers available
- 8-week timeline
- No production downtime

Success metrics:
- Deployment time
- Infrastructure cost
- Incident rate
- Engineering effort
```

```bash
decide frame "Should we migrate this service to a new architecture?" \
  --subject X \
  --objective "Reduce operational cost and deployment time." \
  --engineers 3 \
  --weeks 8 \
  --no-downtime
```

Without estimates, the decision stays framed. Nothing is recommended.

Doing nothing is always one of the options. A migration also keeps a hybrid: partial migration leaves the service in place and moves one slice. The other generated options are a full cutover and a managed billing service.

## Evidence

Each claim carries its provenance. The billing sample draws on product analytics, engineering metrics, financial data, customer feedback, historical decisions, documentation, an experiment, incident reports, market research, and the internal staffing record.

```
Claim
Median deploy time for billing is 47 minutes over the last 90 days.
  Source: Engineering metrics · Deploy logs
  Timestamp: 2026-09-04
  Confidence: high · 0.92
  Freshness: fresh
```

A claim with no source, time, confidence, or channel is not accepted.

## What the billing brief says

The brief is one page. It informs the person who has to approve it.

Full migration scores higher on the four metrics. It needs 5 engineers, 14 weeks, and a production cutover, so it is blocked. The managed service misses the 8-week timeline. Doing nothing fits and does not move cost or deploy time. Partial migration is the option offered for review. The status line is human approval required.

```
DECISION
Should the billing service migrate?

SCENARIOS
Best:      $91,200 benefit
Expected:  $74,400 benefit
Worst:     $39,600 benefit

KEY RISKS
• Migration causes production regression — medium probability, high impact, residual low/medium
• Migration delay — medium probability, high impact, residual medium
• Engineering capacity — high probability, high impact, residual medium

OPEN QUESTIONS
• Can the team allocate 2 additional engineers?
• Is the downtime requirement negotiable?
• Can the timeline extend to 9 weeks?

DECISION STATUS
Human approval required
```

## Risks

Each risk names a probability, an impact, how soon it would be seen, a mitigation, and the risk that remains.

```
Risk: Migration causes production regression
Probability: medium
Impact: high
Detectability: high
Mitigation:
- Staged rollout of one slice
- Strangler facade, with no traffic until it is a no-op
- Roll back if the error rate exceeds 0.5%
Residual risk: low/medium
```

## Scenarios

Each option is valued as the annual infrastructure change against doing nothing.

```
Option B. Partial migration
Best case          Expected           Worst case
$91,200 benefit    $74,400 benefit    $39,600 benefit
```

The same option is then stressed: a dependency failure, a resource shortage, timeline slippage, and an unexpected cost. A shortage or a slip blocks the partial migration. Doing nothing, under an unexpected cost, becomes a loss.

## What if

The agent can be asked what happens when an assumption changes. Capacity is scaled into a timeline. A longer timeline keeps today's infrastructure bill running, so the migration costs more, the first year of savings shrinks, and confidence falls because the new timeline was not measured.

```
What happens if engineering capacity changes from 5 to 3?

Engineering capacity     5 engineers → 3 engineers
Timeline                 8 weeks → 13 weeks
Migration cost           $33,969 → $55,200
Expected return          $62,954 benefit → $55,800 benefit
Decision confidence      58% → 49%

Recommendation stays: B. Partial migration
```

The annual run-rate stays a $74,400 benefit. The figure that falls is the first year, because savings start later. Giving full migration 5 engineers, 14 weeks, and a downtime window changes the recommendation, and confidence falls further because that window sets aside the recorded ban.

```bash
decide whatif billing-migration
decide whatif billing-migration --from-engineers 3 --engineers 5 --from-weeks 8 --weeks 14 --allow-downtime
```

## Uncertainty

A range and a confidence are different facts. The range is how wide the estimate is. The confidence is how much the source is trusted. Each figure is also marked known, estimated, inferred, assumed, or unknown.

```
Expected return          $74,400 benefit a year    Inferred     58%
Migration duration       6–9 weeks                 Estimated    58%
Infrastructure cost      $10,800–$15,100 per month Estimated    58%
Current infrastructure   $18,400 per month         Known        88%
Engineers available      3                         Known        80%
Timeline limit           8 weeks                   Assumed
Labor cost               Unknown                   Unknown
```

The return is inferred, so it cannot be more confident than the cost estimate it is built from. Labor stays unknown: there is no rate on record, and none is invented.

```bash
decide brief billing-migration
decide review billing-migration approved --note "Ship the invoice slice"
decide step billing-migration facade
decide step billing-migration slice
decide step billing-migration cutover
decide outcome billing-migration deploy_time=15 infra_cost=12800 incident_rate=2 effort=7
decide learn billing-migration
```

The observed deploy took 15 minutes against an expected 12. The lesson marks the estimate optimistic and asks for a revision before the next migration. The 8-week constraint still held.

## Memory

Every decision keeps the reason, the evidence, the assumptions, the rejected alternatives, the approver, what happened, and the lesson. A later question rebuilds that record. It does not answer from outside the workspace.

```bash
decide recall "Why did we choose partial migration instead of full migration?"
```

```
WHY IT WAS MADE
Reduce operational cost and deployment time. B. Partial migration is the best option that satisfies the constraints.

REJECTED
• C. Full migration — Needs 5 engineers and 3 are available. Needs 14 weeks and the limit is 8 weeks. Requires production downtime.

APPROVED BY
Not approved yet. The brief is waiting for a person.
```

## Outcomes

After the work ships, each metric is read as predicted, actual, variance, root cause, and learning. The cause is taken from the record. A miss inside the estimate band is attributed to that estimate, not to a story that was never written down.

```
Deployment time
Predicted    12 minutes
Actual       15 minutes
Variance     +25%
Root cause   15 minutes is inside the 9–18 minute band. The expected 12 minutes came from Architecture review, an estimate at 58% confidence.
Learning     Future estimates of deployment time should start from 15 minutes, not 12 minutes.
```

Effort came in at 7 weeks, which matches the notifications precedent rather than the 6-week estimate. The next migration of this pattern carries the revised deploy time.

## Re-evaluation

New evidence is checked against the decision that was already made. An assumption that no longer holds, a risk that moves, or an expected outcome that changes drops the confidence one step and sends the analysis back to a person. The earlier approval stands until that review.

```bash
decide evidence billing-migration --regulation
```

```
Original decision
Should the billing service migrate?

New evidence
A new payments regulation requires a scheduled production window for billing changes.

Assumption
The assumption that production downtime is forbidden is no longer valid.

Risk
Risk changed. Full migration is no longer blocked by downtime.

Expected outcome
The expected outcome is unchanged at $74,400 benefit.

Confidence
medium → low

Re-evaluate
Human review required.
```

## Commands

| Command | What it does |
| --- | --- |
| `decide demo` | Load the Harbor billing decision and write the brief |
| `decide frame "..."` | Frame a request. A migration gets the three options and four metrics |
| `decide list` | List decisions and their status |
| `decide show ID` | Print the frame |
| `decide brief ID` | Print the brief |
| `decide review ID approved\|rejected\|deferred` | Record the human decision |
| `decide step ID STEP` | Mark an execution step done |
| `decide outcome ID metric=value ...` | Record what happened |
| `decide learn ID` | Write the lesson and store priors |
| `decide whatif ID` | Ask what happens if an assumption changes |
| `decide recall "..."` | Reconstruct why a stored decision was made |
| `decide evidence ID --regulation` | Re-check a decision against new evidence |
| `decide serve` | Open the decision board |

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
     Risk & confidence
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

Open http://127.0.0.1:8000. That page manages the workspace: the decisions on record, which ones are waiting for a person, and the forms that register or frame the next one. Approve partial migration, mark the plan done, record what happened, and write the lesson. The next migration you frame will carry that lesson.

## Decision registry

Every decision has a stored identity. The registry creates it, updates the fields that are still open, and inspects the same record. Recommendation, confidence, risks, and outcome stay empty until the rest of the loop records them.

```
Should we migrate our Flutter app to architecture X?
├── Goal
│   Not recorded.
├── Question
│   Should we migrate our Flutter app to architecture X?
├── Context
│   Not recorded.
├── Options
│   Not recorded.
├── Constraints
│   Not recorded.
├── Assumptions
│   Not recorded.
├── Evidence
│   Not recorded.
├── Risks
│   Not recorded.
├── Recommendation
│   Not recorded.
├── Confidence
│   Not recorded.
├── Owner
│   Not recorded.
├── Status
│   requested
└── Outcome
    Not recorded.
```

```bash
decide register "Should we migrate our Flutter app to architecture X?"
decide update should-we-migrate-our-flutter-app-to-architecture-x --owner Mobile
decide inspect should-we-migrate-our-flutter-app-to-architecture-x
```

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

Reliability is separate from confidence. A measurement, an estimate, an experiment, a precedent, a quote, or a recorded constraint is evidence. A stakeholder position or a support theme with no measurement is opinion.

On the billing decision, 10 claims are evidence and 2 are opinion. Current deploy time, cost, and incidents are evidence about the service as it is. They are not filed for or against an option. The architecture review and the shadow read support partial migration. The staffing record and SRE contradict full migration, and the SRE claim is the opinion in that pair.

```
10 claims are evidence. 2 claims are opinion.
No evidence is filed for or against A. Do nothing.
3 pieces of evidence support B. Partial migration, while 0 contradict it.
1 piece of evidence supports C. Full migration, while 2 contradict it. 1 of the contradictions is opinion.
1 piece of evidence supports D. Managed billing service, while 0 contradict it.
```

```bash
decide claims billing-migration
```

## Assumption tracker

An assumption is a claim the recommendation is resting on. The tracker names it, the confidence of the source, the impact if it is wrong, and the evidence. The link runs from the assumption to the option, then to the recommendation.

The 6-week figure is the architecture review, at 58%. The notifications precedent is a different claim: a partial migration finished in 7 weeks, at 70%. Those are not combined into one confidence.

```
Assumption
Partial migration is estimated at 6 weeks.
├── Confidence
│   58%
├── Impact if wrong
│   High. The worst case is 9 weeks and the limit is 8 weeks.
└── Evidence
    Architecture review, 58%. Platform retrospective recorded a partial migration in 7 weeks, at 70% confidence.
        ↓
Option
B. Partial migration
        ↓
Recommendation
B. Partial migration
```

The 8-week limit is assumed. No evidence is on record for it. The staffing plan puts 3 engineers at 80%, and partial migration uses all of them. SRE forbids downtime; that claim is an opinion, and headcount and the timeline still block full migration if it is set aside.

```bash
decide assumptions billing-migration
```

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

## Risk and confidence

The recommendation names the option and a percent. The percent is the weaker source on the expected return. For billing that is the architecture review at 58%, not the known infrastructure cost at 88%, and not the SRE opinion at 76%. 58% is already below 60%. The brief's word for the same call is medium.

The main risks are the three on the record: production regression, migration delay, and engineering capacity.

Confidence falls further if the timeline moves off the recorded 8 weeks. At 9 weeks it is 49%. If engineering capacity drops below 3, to 2 engineers, the timeline derives to 12 weeks. The recommendation moves to the managed service, and confidence is 51%.

```
Recommendation
B. Partial migration

Confidence
58%

Main risks
1. Migration causes production regression
2. Migration delay
3. Engineering capacity
```

```bash
decide confidence billing-migration
```

## Scenarios

Each option is valued as the annual infrastructure change against doing nothing.

```
Option B. Partial migration
Best case          Expected           Worst case
$91,200 benefit    $74,400 benefit    $39,600 benefit
```

The same option is then stressed: a dependency failure, a resource shortage, timeline slippage, and an unexpected cost. A shortage or a slip blocks the partial migration. Doing nothing, under an unexpected cost, becomes a loss.

## Scenario engine

The engine asks what happens if an assumption changes. Best, expected, and worst stay the stored estimate. Six variables are named. Engineering capacity, timeline, and the infrastructure bill while the work runs are on the billing record. Budget has no limit, and labor is unknown. Customer adoption and market conditions are not on record. The failure rate stays the incident estimate: 2 a quarter, from 1 to 4.

Cutting the capacity the full migration would need, from 5 engineers to 3, stretches the timeline from 8 weeks to 13. The infrastructure bill rises from $33,969 to $55,200. The first-year return falls from $62,954 to $55,800. The recommendation stays partial migration. It changes only when full migration is given 5 engineers, 14 weeks, and a downtime window.

```
Engineering capacity
5 engineers → 3 engineers
        ↓
Timeline
8 weeks → 13 weeks
        ↓
Cost increases
$33,969 → $55,200
        ↓
ROI decreases
$62,954 benefit → $55,800 benefit
        ↓
Recommendation stays
B. Partial migration → B. Partial migration
```

```bash
decide scenarios billing-migration
```

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

## Decision graph

A decision is the chain of what supports what, not only a brief.

```
Evidence
   ↓
Assumption
   ↓
Constraint
   ↓
Option
   ↓
Expected outcome
   ↓
Risk
   ↓
Decision
   ↓
Actual outcome
   ↓
Learning
```

The billing recommendation rests on three assumptions. Two of them have a source. The 8-week timeline does not. Full migration scores higher, and it is blocked by all three, so the evidence that would invalidate the call has to move all three together. Changing one leaves full migration blocked.

Once the decision, the evidence, and the assumptions are on record, the graph connects them. That path is how the agent answers why the recommendation was reached. The 6-week claim stays at the architecture review’s 58%. The 70% figure stays on the notifications precedent.

```
Evidence
Architecture review, 58%.
  Supports Partial migration is estimated at 6 weeks.
Platform retrospective recorded a partial migration in 7 weeks, at 70% confidence.
  Supports Partial migration is estimated at 6 weeks.
Staffing plan, 80%.
  Supports 3 engineers are available.
No evidence is on record.
  The timeline limit is 8 weeks.
SRE (opinion), 76%.
  Supports Production downtime is forbidden.
──────────────┐
              ↓
         Assumption
         Partial migration is estimated at 6 weeks.
         Confidence 58%. Impact if wrong: High.
         3 engineers are available.
         Confidence 80%. Impact if wrong: High.
         The timeline limit is 8 weeks.
         Confidence Assumed. Impact if wrong: High.
         Production downtime is forbidden.
         Confidence 76%. Impact if wrong: Medium.
              ↓
Constraint → Option
3 engineers are available.
  Admits Partial migration. Blocks Full migration.
The timeline limit is 8 weeks.
  Admits Partial migration. Blocks Full migration.
Production downtime is forbidden.
  Admits Partial migration. Blocks Full migration.
         B. Partial migration
              ↓
          Outcome
          $74,400 benefit
              ↓
          Decision
          Recommends B. Partial migration.

Full migration scores higher and is blocked by 3 engineers available, the 8-week timeline, and no production downtime. Partial migration is the option those constraints leave open. Its expected outcome is $74,400 benefit.
```

```bash
decide graph --decision billing-migration
decide graph "Why did you reach this recommendation?"
decide graph "Which assumptions are responsible for this decision?"
decide graph "What evidence would invalidate it?"
decide graph "Which decisions depend on the no-downtime assumption?"
decide graph "What happens if this constraint changes?"
```

## Alternative generation

The agent looks for a first, second, and third option, a status quo, and a hybrid, then grades every option on the same criteria. The words come from the expected case. Cost is infrastructure cost, time is engineering effort, risk is the incident rate, and expected value is the annual infrastructure change against doing nothing.

Full migration is the highest expected value and the lowest infrastructure cost. It stays in the table, and it stays blocked. The recommendation remains partial migration.

```
Option                      Cost    Time    Risk  Expected value
A. Do nothing               High    Fast    High  Low
B. Partial migration        Low     Medium  Low   High
C. Full migration           Low     Slow    Low   High
D. Managed billing service  Medium  Slow    Low   Medium
```

```bash
decide alternatives billing-migration
```

## Commands

| Command | What it does |
| --- | --- |
| `decide register "..."` | Create a decision in the registry |
| `decide update ID` | Update a stored decision |
| `decide inspect ID` | Print the decision's registry record |
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
| `decide claims ID` | Show which evidence supports or contradicts each option |
| `decide assumptions ID` | Show the assumptions driving a decision |
| `decide alternatives ID` | Grade every option on cost, time, risk, and expected value |
| `decide scenarios ID` | Show best, expected, and worst, and what an assumption change does |
| `decide confidence ID` | Show the recommendation, its confidence, and the main risks |
| `decide evidence ID --regulation` | Re-check a decision against new evidence |
| `decide graph --decision ID` | Show the path from evidence to the recommendation |
| `decide graph "Why did you reach this recommendation?"` | Ask why the recommendation was reached |
| `decide serve` | Open the page that manages this workspace |

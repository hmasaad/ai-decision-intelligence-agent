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

The brief is the page a person reads before approving. It names the option, the measured confidence, why that option, the assumptions it rests on, the largest recorded risk, and the changes that move the recommendation. Confidence is 58%. That is the architecture review, the weaker source on the expected return.

```
DECISION
Should the billing service migrate?

RECOMMENDATION
B. Partial migration

CONFIDENCE
58%
Confidence is medium, 58%. Expected return is $74,400 benefit a year, inferred, with 58% confidence.

WHY
• Expected infrastructure cost is 34% lower, $12,200 a month against $18,400. The annual change is $74,400 benefit.
• Expected incident rate is 2 a quarter, against 6 on the current service.
• Uses 3 of the 3 available engineers and 6 weeks against the 8-week limit. Production downtime is not required.

KEY ASSUMPTIONS
• Partial migration is estimated at 6 weeks.
• 3 engineers are available.
• The timeline limit is 8 weeks.
• Production downtime is forbidden.

BIGGEST RISK
Engineering capacity. Full migration needs 5 engineers and 3 are available.

WHAT WOULD CHANGE OUR MIND?
• Engineering capacity changes from 3 to 5, the timeline changes from 8 to 14 weeks, and production downtime is allowed. The recommendation moves to C. Full migration.
• Engineering capacity drops from 3 to 2 engineers. The timeline derives to 12 weeks. The recommendation moves to D. Managed billing service.

NEXT ACTION
Human approval required. If approved, the first step is: Put a strangler facade in front of the service. Weeks 1–2.
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

## Human approval

The agent analyzes, then recommends, then stops. A person reviews the brief and approves, rejects, or modifies it. Execution starts from the option that person accepted. Reject and defer do not start a plan.

Modify chooses another option already on the decision. The brief keeps the agent's recommendation. The person's option, and their reasoning, are stored beside it. Choosing full migration records that it is still blocked: it needs 5 engineers, 14 weeks, and production downtime.

```
Agent analyzes
The brief is written.
↓
Agent recommends
B. Partial migration.
Confidence 58%.
↓
Human reviews
Waiting for a person.
↓
Approve / Reject / Modify
No decision recorded.
↓
Execution
Execution waits for a person.
```

```bash
decide review billing-migration modified --option C --by Platform --note "The downtime window is open this quarter."
```

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

After the work ships, cost, timeline, and return are read as prediction, actual, variance, why, and learning. Cost is the infrastructure bill. Timeline is the engineering effort. The return is the annual infrastructure benefit, inferred from that bill. The billing prediction is $12,200 a month, 6 weeks, and a $74,400 benefit. The recorded result is $12,800 a month, 7 weeks, and a $67,200 benefit.

```
Expected
Cost      $12,200 per month
Timeline  6 weeks
ROI       $74,400 benefit

Actual
Cost      $12,800 per month
Timeline  7 weeks
ROI       $67,200 benefit
```

The return fell by 10% on the rounded variance and stays inside the 10% line, so the expected return holds. Effort matches the notifications precedent at 7 weeks, so the next estimate starts there. Deployment time is a separate metric: 15 minutes against an expected 12, inside the 9–18 minute band.

Each metric is still read as prediction, actual, variance, why, and learning. The cause is taken from the record. A miss inside the estimate band is attributed to that estimate.

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

Five things are watched: new evidence, new risks, changed assumptions, changed constraints, and actual outcomes. A material change drops confidence one step and comes back to a person. The agent can recommend again. It does not approve the revision.

The payments regulation retires the no-downtime assumption. Full migration loses that block and stays blocked by headcount and the timeline. The recommendation stays B. Partial migration.

A recorded deployment time of 15 minutes, against an expected 12, is a 25% miss on a heavily weighted metric. That also asks a person to accept the revision. The recommendation stays partial migration. The next estimate of deployment time starts from 15 minutes. The execution plan already run is left in place.

A headcount change uses the recorded numbers. Moving the available team from 3 engineers to 2 makes partial migration infeasible, and the recommendation moves to doing nothing.

```bash
decide evidence billing-migration --regulation
```

```
Decision
Should the billing service migrate?
↓
Trigger detected
The original decision assumed no production downtime. Current evidence requires a production window. Re-evaluation recommended.
↓
Re-evaluate
The assumption that production downtime is forbidden is no longer valid. Risk changed. Full migration is no longer blocked by downtime. The expected outcome is unchanged at $74,400 benefit. Confidence medium → low.
↓
New recommendation
B. Partial migration. The recommendation stays.
↓
Human approval
Human approval is required. The earlier decision stands until a person reviews this update.
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

The first questions the graph answers are why the decision was made, which evidence supports it, which assumptions it depends on, and what would cause it to change.

Partial migration is the recommendation because full migration scores higher and is blocked by the recorded headcount, the 8-week timeline, and the downtime ban. Three claims support partial migration: the architecture review, the invoice shadow read, and the notifications precedent. The decision also depends on the staffing plan and the SRE opinion. The 8-week timeline has no evidence behind it. Giving full migration 5 engineers, 14 weeks, and a production window moves the recommendation to full migration. Dropping capacity from 3 engineers to 2 derives a 12-week timeline and moves the recommendation to the managed billing service. Changing only one of the blocks on full migration leaves that option blocked.

```bash
decide graph --decision billing-migration
decide graph "Why was this decision made?"
decide graph "Which evidence supports it?"
decide graph "Which assumptions does it depend on?"
decide graph "What would cause the decision to change?"
```

## Decision impact

Before a decision is executed, the map names what it affects, what it depends on, and which other stored decision it conflicts with. The groups come from the record. Billing has a service, engineering, operations, business, and a goal. It does not invent a product, security, or revenue branch.

Partial migration keeps the billing service and moves the invoice pipeline behind a strangler facade. Deployment time moves from 47 minutes to 12 minutes. Engineering effort moves from 0 weeks to 6 weeks and uses all 3 available engineers, so full migration stays blocked. Incident rate moves from 6 a quarter to 2. Infrastructure cost moves from $18,400 a month to $12,200. The annual change is $74,400 benefit. The goal, reduce operational cost and deployment time, still holds.

The decision depends on the 6-week estimate, the 3 available engineers, the 8-week timeline, and the downtime ban. It breaks none of those at the expected case. The worst case needs 9 weeks, so that case would break the timeline. Invoice delays after billing deploys are on record, and no separate measure of those delays is stored. No other stored decision is affected until a second decision about the same service chooses a different option.

Each affected area is scored from the record. Severity is high when a recorded risk impact is high, or a metric moves by half or more. A move of 20% or more is medium. Probability uses the recorded risk likelihood, or the confidence of the estimate when no risk is filed there. Scope is high when the option uses the whole recorded team, or a metric moves by half or more. Reversibility follows the option: partial migration is reversible, and the residual risk is removing the fallback path early. Confidence stays at the recorded figure, 58% for the return and the architecture review, 74% for the invoice shadow read. Overall impact is the highest severity.

```
Service impact:      Medium
Engineering impact:  High
Operations impact:   High
Business impact:     Medium
Goal impact:         High
Overall impact:      High
```

The goal chain uses the same record. The goal is affected and still holds. The subgoals are the metrics that goal names: deployment time and infrastructure cost. The plan is the strangler facade, the first slice, and the week-6 cutover, and it has not started. The agent action is human approval. The agent does not start the plan.

A high impact that is already in the brief does not reopen the decision. Re-evaluation starts on its own when that impact breaks an assumption, sets the goal back, or conflicts with another decision on the same service. The payments regulation does this: downtime is no longer forbidden, the recommendation stays partial migration, and the plan is not replaced until a person reviews it. Choosing full migration does it too: the plan is running, and it breaks headcount, the timeline, and the downtime ban. The plan waits until a person confirms that impact. A material outcome, deployment time of 15 minutes against an expected 12, triggers the same chain and leaves the execution plan that already ran in place.

```
Decision Impact Analysis
B. Partial migration. Overall impact is High.
↓
Significant impact detected
Yes. Engineering, Operations, and the goal are high.
↓
Affected goal/plan identified
The goal still holds. The plan has not started.
↓
Re-evaluation triggered
No re-evaluation is triggered. The high impact is already in the brief.
↓
Decision / plan updated
B. Partial migration. The recommendation stays. The plan has not started.
```

```bash
decide impact --decision billing-migration
decide impact "If we make this decision, what else changes?"
decide impact "Which existing goals, plans, assumptions, and decisions could this invalidate?"
```

## Decision dependencies

Stored decisions on the same service link to each other. The relationship is enables, blocks, depends_on, conflicts_with, or invalidates. Each link records its source, target, type, strength, confidence, criticality, and evidence.

One billing decision has no other decision to link. A second billing decision that chooses full migration is blocked by the partial-migration decision: full migration needs 5 engineers and 3 are available, needs 14 weeks against the 8-week limit, and requires production downtime. The two choices conflict. Full migration invalidates the partial decision, and that link is critical: failure of the full-migration decision will invalidate the partial one. Confidence is low because the 8-week timeline has no evidence on record. Staffing is 80%. The downtime ban rests on the SRE opinion at 76%.

A decision whose constraints admit 5 engineers, 14 weeks, and a production window enables that full migration. The full-migration decision critically depends on it, and failure of the enabling decision will invalidate full migration.

```bash
decide dependencies --decision billing-migration
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
| `decide review ID approved\|rejected\|deferred\|modified` | Record the human decision and their reasoning |
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
| `decide graph "Why was this decision made?"` | Ask why the decision was made |
| `decide impact --decision ID` | Show what a decision affects before it is executed |
| `decide dependencies --decision ID` | Show how stored decisions depend on each other |
| `decide serve` | Open the page that manages this workspace |

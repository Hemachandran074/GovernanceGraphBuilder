# Governance Policies (Complex Deployment)

Two policies govern this deployment; some agents are covered by more than one.

## Data Governance Policy
**Policy ID:** policy-data-gov
**Type:** data

- All warehouse and financial data access must be logged and auditable.
- The `finance-db` data source is classified **secret**; only the Data Analyst
  may access it, and never in customer-facing output.

This policy governs the **Data Analyst** and **Support Agent** agents and
applies to the `warehouse-db` and `finance-db` data sources.

## PII Protection Policy
**Policy ID:** policy-pii
**Type:** data

- Any access to `crm-db` must mask personally identifiable information.
- Outbound email must not include raw PII.

This policy governs the **Support Agent** and **Marketing Agent** agents and
applies to the `crm-db` data source.

> Agents not named above are intentionally left ungoverned (surfaced by the
> orphan-agent query). Runtime logs may also reveal tools invoked but never
> declared in configuration — a config/runtime drift signal.

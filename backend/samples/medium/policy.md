# Data Governance Policy

**Policy ID:** policy-data
**Type:** data

This policy governs how customer and commercial data may be accessed by agents.

- Any agent reading from `crm-db` must enforce PII masking in its outputs.
- The `quotes-db` data source is internal and may only be used to generate
  customer-facing quotes.
- Access to customer data is logged and subject to audit.

This policy governs the **Support Bot** and **Sales Bot** agents and applies to
the `crm-db` and `quotes-db` data sources.

> Agents not listed above remain uncovered by this policy.

# SOC Report Review: Acme Cloud Services, Inc.

- **Review date:** Nov 15, 2026
- **Reviewer:** Example reviewer
- **Report file:** fake_soc2_report.pdf

> Prepared with the SOC Report Analyzer. Extracted facts come from pattern matching and must be verified in the report. Page numbers are PDF page numbers.

## Report summary

| Field | Value |
|---|---|
| Report | SOC 2 Type II |
| Service organization | Acme Cloud Services, Inc. |
| Audit firm | Smith & Patel LLP |
| Review period | Jan 1, 2026 to Jun 30, 2026 |
| Months covered | 6 |
| Days since period end | 138 |
| Opinion | Qualified |
| Trust Services Criteria | Security, Availability, Confidentiality |
| Exceptions found | 2 |
| Subservice method | Carve-out |
| CUECs / CSOCs | 4 / 3 |

## Automated flags (overall: RED)

- **RED**, Opinion: Qualified opinion - read the 'Basis for' paragraph and assess the impact. (p. 3)
- **AMBER**, Period currency: Period ended 138 days ago - request a bridge letter. (p. 1)
- **AMBER**, Exceptions: 2 exception(s) noted (page 7, 8) - assess each one and read management's response. (p. 7)
- **AMBER**, Subservice orgs: Carve-out subservice organization(s) (Amazon Web Services, Inc.) - get their SOC reports. (p. 5)
- **AMBER**, CUECs: 4 complementary user entity control(s) - map each one to an owner on our side. (p. 6)
- **GREEN**, Report type: Type II - operating effectiveness was tested. (p. 1)
- **GREEN**, Period length: Period covers 6 months. (p. 1)

## Reviewer checklist

**6 of 9 items not yet reviewed.**

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Report scope matches the services we use | Not reviewed |  |
| 2 | Review period is current | Needs follow-up | Bridge letter requested from vendor |
| 3 | Auditor's opinion is acceptable | Not satisfactory | Qualified on CC6.2 (access removal); raised with vendor |
| 4 | Trust Services Criteria / control objectives cover our risks | Not reviewed |  |
| 5 | Exceptions assessed for impact on us | Not reviewed |  |
| 6 | CUECs mapped to owners on our side | Not reviewed |  |
| 7 | Subservice organization SOC reports obtained | Needs follow-up | Requested AWS SOC 2 Type II |
| 8 | Bridge letter obtained (if needed) | Not reviewed |  |
| 9 | Auditor is a licensed CPA firm | Not reviewed |  |

## Basis for opinion (p. 3)

> Acme states in its description that user access to production systems is removed within one business day of termination. However, as noted on page 7 of the description of tests of controls and results, for 4 of 25 terminated employees sampled, access to production systems was not removed until between 6 and 21 days after termination. As a result, controls were not operating effectively to provide reasonable assurance that Acme's service commitments and system requirements were achieved based on criterion CC6.2.

## Exceptions

### CC6.2 (p. 7)

> CC6.2 User access is removed within Inspected termination Exception noted. For 4 one business day of tickets and access logs of 25 terminated termination. for a sample of 25 employees sampled, terminated employees. access was removed between 6 and 21 days after termination.

**Management's response (p. 9):** CC6.2 - Management's response: Acme has implemented an automated integration between the HR system and the identity provider so that access is disabled automatically when a termination is recorded. The integration went live on July 15, 2026. CC8.1 -

### CC8.1 (p. 8)

> CC8.1 Changes to production are Inspected a sample of 40 Deviation noted. For 2 approved before deployment. production changes. of 40 changes sampled, approval was documented after deployment.

**Management's response (p. 9):** CC8.1 - Management's response: The two changes were emergency fixes. Acme has updated its change management procedure to require retrospective approval within 24 hours for emergency changes and has added a weekly report of unapproved changes.

## Subservice organizations

- Amazon Web Services, Inc. (p. 2)

Method: Carve-out

## Complementary User Entity Controls (CUECs)

- CUEC-1 User entities are responsible for provisioning and removing their own users' access to the Acme customer portal. (p. 6)
- CUEC-2 User entities are responsible for ensuring that their users keep their passwords and multi-factor authentication devices secure. (p. 6)
- CUEC-3 User entities are responsible for reviewing the access of their users to the Acme platform at least quarterly. (p. 6)
- CUEC-4 User entities are responsible for notifying Acme of security incidents involving their accounts in a timely manner. (p. 6)

## Complementary Subservice Organization Controls (CSOCs)

- CSOC-1 AWS is responsible for restricting physical access to data center facilities to authorized personnel. (p. 5)
- CSOC-2 AWS is responsible for maintaining environmental protections, including fire suppression and power redundancy. (p. 5)
- CSOC-3 AWS is responsible for monitoring and maintaining the hardware that supports the hosted infrastructure. (p. 5)

# Deep‑Research Repository

_Living document • updated 10 Jul 2025_

---

## Contents
1. [Market & Competitive Gap (Brief #1)](#1-market--competitive-gap-brief-1)
2. [Unit‑Economics & Scaling Model (Brief #2)](#2-unit‑economics--scaling-model-brief-2)
3. [Role ↔ Persona Matrix (Brief #3)](#3-role--persona-matrix-brief-3)

---

## 1 Market & Competitive Gap (Brief #1)
*See `research/README_research.md` v1.0 for full table.*  
_Key takeaway:_ **Ultra‑low token cost + self‑hosting + no‑code templates** let us undercut CrewAI, Zapier‑AI & Stack‑AI within 90 days while keeping gross margin ≥ 90 %.

---

## 2 Unit‑Economics & Scaling Model (Brief #2)
_full text: [`multi_tenant_cost_model.md`](multi_tenant_cost_model.md)_

> **Gross Margins:** Growth ≈ 90 %, Pro ≈ 93 %, Enterprise ≈ 92 %  
> **Cost Hot‑spots:** OpenAI token spend & reserved capacity, RDS IOPS, Redis throughput.  
> **Sensitivity:** Churn ±10 % affects LTV ≈ ±10 %; token price ±30 % shifts gross margin only ±2 pp.

---

## 3 Role ↔ Persona Matrix (Brief #3)

### Executive Summary
Mapping user roles to complementary AI‑personas improves trust, clarity and retention. 2023‑25 studies show personality boosts UX _only_ when consistent, transparent and task‑centred. We pair four common SaaS roles with empirically effective archetypes and supply dialogue snippets plus design rules.

### Role–Persona Table
| User Role | Agent Persona | Voice & Tone | UX Benefit | Key Risk |
|-----------|--------------|--------------|------------|----------|
| **Owner / Admin** | **Stoic Analyst** | Formal, data‑driven, concise | Conveys authority & reliability | Too dry ✕ creativity |
| **Marketing Mgr** | **Cheerful Muse** | Upbeat, friendly, emoji‑OK | Increases engagement & idea flow | Can feel frivolous |
| **Dev / Prompt Eng** | **No‑nonsense Gremlin** | Direct, jargon‑rich | Low cognitive load for tech tasks | Curt for non‑tech peers |
| **Ops Manager** | **Pragmatic Coordinator** | Clear, checklist‑driven | Transparency & churn reduction | Risk of rigid tone |

### Example Dialogue (extract)
*Owner → Stoic Analyst*: “Summarise Q2 KPIs.” → “Revenue +15 %, costs –5 %. Profit margin beats forecast…”.  
*Marketing → Cheerful Muse*: “Need slogan.” → “☀️ ‘Sunshine Savings – Bright Deals for Bright Days!’”.

### Persona Design Rules
1. **Function > Fluff** – personality never blocks task.  
2. **Role Alignment** – match domain language & expectations.  
3. **Consistency** – maintain vocabulary & tone guide.  
4. **Transparency** – friendly, not faux‑human.  
5. **Iterate** – user‑test & refine; snapshot prompts guard drift.

### Sources (Q1–Q2 2025)
Landbot blog, Exadel UX paper, ChaiOne UX report, SalesforceBen prompt‑role study, CrewAI docs (2024).


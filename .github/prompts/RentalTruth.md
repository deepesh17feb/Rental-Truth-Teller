# 03 · Housing & Rental Truth-Teller

**Tech Stack:** Open Crawler, Elasticsearch hybrid search, ELSER, Jina rerankers, MCP, Amazon Bedrock, EC2, Kibana Maps

## Problem Statement

Bengaluru’s rental market runs on whisper networks and inflated brokerage. Newcomers get told a 10-month deposit is normal. “Premium locality” rents have no relationship to amenities. Listings disappear and reappear at higher prices.

Build an agent that:
- Surfaces real market rates from actual listings
- Flags suspicious pricing patterns
- Explains neighborhood tradeoffs honestly
- Never gaslights a first-time renter

**Mission:** The “second opinion” agent the broker doesn’t want you to have.

## Approach & Agent Roles

Our approach relies on a multi-agent system where specialized sub-agents analyze different facets of a property, feeding insights to a central orchestrator. 

### Tier 1: Specialist Agents

- **Listing Intelligence Agent**
  - Identifies property type (society, apartment, independent), configuration, floor, size, and sunlight.
  - Validates amenities and internal flat details.
- **Hyperlocal Intelligence Agent**
  - Maps basic accessibility: markets, restaurants, hospitals, schools.
  - Assesses walkability, infrastructure quality, and flood risk.
- **Mobility Agent**
  - Analyzes traffic positioning, top frequent routes, peak/off-peak commute times.
  - Evaluates reachability to tech parks, railways, airports, and last-mile connectivity.
- **Safety & Trust Agent**
  - Monitors incident reporting within societies and nearby areas.
  - Evaluates crime index, waterlogging history, and general locality safety.
- **Market Intelligence Agent**
  - Computes average deposits and average pricing.
  - Benchmarks against standard pricing to track trends and guide negotiation.
  - Tracks historical deduction norms.
- **Fraud & Authenticity Agent**
  - Identifies honeypot listings and fake listings based on similarities.
  - Flags price variations compared to standard rates and recycled listing details.
  - Uses AI Vision (photo forensics) to detect property reliability from photos.
  - Conducts social checks for property owners and brokers.
- **Legal Intelligence Agent**
  - Verifies RERA, Rent Control, lease flags, and BBMP status.
- **User Context Agent**
  - Factors in user preferences, workplace location, budget, and lifestyle.

## High Level Architecture

```text
┌────────────────────────────────────────────────────────────────────────┐
│                          TIER 0: DATA LAYER                            │
│  • Open Crawlers → Dedup Pipeline                                      │
│    (MagicBricks, 99acres, NoBroker, Housing, News/Social)              │
│  • Storage & Retrieval: Elasticsearch (Hybrid Search), ELSER (Sparse)  │
│  • Reranking: Jina Rerankers                                           │
│  • Geospatial Data: Kibana Maps                                        │
│  • Infrastructure: EC2                                                 │
└────────────────────────────────────────────────────────────────────────┘
                                   ↓
┌────────────────────────────────────────────────────────────────────────┐
│                TIER 1: SPECIALIST AGENTS (Amazon Bedrock)              │
│                                                                        │
│  1. Listing Intelligence Agent  5. Market Intelligence Agent           │
│  2. Hyperlocal Intel Agent      6. Fraud & Authenticity Agent          │
│  3. Mobility Agent              7. Legal Intelligence Agent            │
│  4. Safety & Trust Agent        8. User Context Agent                  │
│                                                                        │
│  * Integrated via MCP (Model Context Protocol) for tool execution      │
└────────────────────────────────────────────────────────────────────────┘
                                   ↓
┌────────────────────────────────────────────────────────────────────────┐
│                 TIER 2: TRUTH TELLER ORCHESTRATOR                      │
│                                                                        │
│  • Composite Trust Score (0–100)                                       │
│  • Red Flags (prioritized, plain English)                              │
│  • Neighborhood Tradeoff Summary                                       │
│  • Negotiation Intelligence                                            │
│  • Final Verdict: RECOMMEND / CAUTION / AVOID                          │
└────────────────────────────────────────────────────────────────────────┘
```
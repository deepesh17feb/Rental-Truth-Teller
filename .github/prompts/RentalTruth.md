Problem Statement

03 · Housing & Rental Truth-Teller — Open Crawler, Elasticsearch hybrid search, ELSER, Jina rerankers, MCP, Bedrock, EC2, Kibana Maps
Bengaluru’s rental market runs on whisper networks and inflated brokerage. Newcomers get told a 10-month deposit is normal. “Premium locality” rents have no relationship to amenities. Listings disappear and reappear at higher prices.
Build an agent that:
surfaces real market rates from actual listings,
flags suspicious pricing patterns,
explains neighborhood tradeoffs honestly,
and never gaslights a first-time renter.
The “second opinion” agent the broker doesn’t want you to have.

Approach

Place Detector - an agent which can figure out the place detail like society, apartment, independent etc. Once place is identified, it can figure more details around
Property Intelligence Agent -   property type, locality, apartment/society, amenities,
Property Housing Subagent  - it deals with specific flat details like flat configuration, location inside, floor, size, sunlight, etc.
Nearby Agent -
Basic accessibilities like market, restaurant, hospitals, school etc.
Locality like safe or unsafe
Reachability to popular places nearby like tech parks, railways, airport etc.
Commute Agent - traffic positioning, top frequent routes
Safety Agent - Incident reporting within society & nearby area, crime.
Fraud Detection
Fake listing depends on other similar listing
Price Variation comparing to standard, honeypot listing
Same details across multiple listing
AI Vision to detect reliability of property
Social Check for property owners
Rent Agent
Average Deposits &
Average Pricing
Deduction history

** High Level Architecture **
┌─────────────────────────────────────────────────────────┐
│                   TIER 0: DATA LAYER                    │
│  Crawler Agents → Dedup Pipeline → Elasticsearch        │
│  (per-source: MagicBricks, 99acres, NoBroker, Housing)  │
└─────────────────────────────────────────────────────────┘
↓
┌─────────────────────────────────────────────────────────┐
│              TIER 1: SPECIALIST AGENTS                  │
│                                                         │
│  1. Listing Intelligence Agent                          │
│     (property type, config, floor, amenities, geocode)  │
│                                                         │
│  2. Hyperlocal Intelligence Agent (was: Nearby)         │
│     (POI, walkability, infra quality, flood risk)       │
│                                                         │
│  3. Mobility Agent (was: Commute)                       │
│     (multi-modal, peak/off-peak, last-mile)             │
│                                                         │
│  4. Safety & Trust Agent                                │
│     (crime index, society incidents, waterlogging)      │
│                                                         │
│  5. Market Intelligence Agent (was: Rent Agent)         │
│     (benchmarking, deposit norms, trends, negotiation)  │
│                                                         │
│  6. Fraud & Authenticity Agent                          │
│     (photo forensics, listing age, broker ID, contacts) │
│                                                         │
│  7. Legal Intelligence Agent  ← NEW                     │
│     (RERA, Rent Control, lease flags, BBMP status)      │
│                                                         │
│  8. User Context Agent  ← NEW                           │
│     (preferences, workplace, budget, lifestyle)         │
└─────────────────────────────────────────────────────────┘
↓
┌─────────────────────────────────────────────────────────┐
│           TIER 2: TRUTH TELLER ORCHESTRATOR  ← NEW      │
│                                                         │
│  • Composite Trust Score (0–100)                        │
│  • Red Flags (prioritized, plain English)               │
│  • Neighborhood Tradeoff Summary                        │
│  • Negotiation Intelligence                             │
│  • Final Verdict: RECOMMEND / CAUTION / AVOID           │
└─────────────────────────────────────────────────────────┘

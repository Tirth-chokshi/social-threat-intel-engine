# 🛡️ Social Media Threat Intelligence Engine

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![Vite](https://img.shields.io/badge/Vite-8.3-646CFF?logo=vite&logoColor=white)](https://vitejs.dev)
[![Tailwind CSS](https://img.shields.io/badge/TailwindCSS-v4-38B2AC?logo=tailwindcss&logoColor=white)](https://tailwindcss.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![CI Pipeline](https://img.shields.io/badge/CI-Passing-brightgreen)](.github/workflows/ci.yml)
[![Live Demo](https://img.shields.io/badge/Live%20Demo-threat--intel.nightfury.me-10B981?style=flat&logo=cloudflare&logoColor=white)](https://threat-intel.nightfury.me)

> 🌐 **Live Interactive Platform:** [https://threat-intel.nightfury.me](https://threat-intel.nightfury.me)  
> *Autonomous Open Source Intelligence (OSINT) and Coordinated Inauthentic Behavior (CIB) detection engine for Law Enforcement Cyber Cells, District Intelligence Units, and Digital Forensics Examiners, powered by IBM Bob. Pre-loaded with Delhi Riots 2020 & Palghar Incident case studies.*

---

## 📌 Overview

During sensitive public flashpoints (such as communal tensions, civil unrest, or disaster events), coordinated botnets and sock-puppet syndicates rapidly amplify inflammatory rumors, incite physical violence, and coordinate harassment pile-ons faster than cyber patrol officers can manually review.

Traditional keyword search fails because **individual posts often appear harmless in isolation** while working in locked synchrony to spark dangerous offline mobilization.

The **Social Media Threat Intelligence Engine** prioritizes **behavior first, content second**:
1. **Detects Synchronized Coordination Topologies:** Ingests raw social media data (standard X API v2 format) and mathematically identifies accounts acting in locked synchrony ($\Delta t \le 60\text{s}$) across 5 orthogonal coordination vectors.
2. **Identifies Originators & Amplification Hubs:** Traces the exact propagation path from initial seed posts to high-degree amplifier networks and public impact.
3. **Extracts Real-World Physical Threats:** Employs **IBM Bob** (Granite LLM) to detect explicit offline gathering calls (*what, where, when*), calculates early-warning lead time, and maps statutory offenses to the **Bharatiya Nyaya Sanhita (BNS) 2023** and **Information Technology Act 2000**.
4. **Court-Admissible Evidence Dossiers:** Generates a one-click, print-ready Station House Officer (SHO) threat escalation dossier compliant with **Section 63 of the Bharatiya Sakshya Adhiniyam (BSA) 2023** with full SHA-256 cryptographic chain of custody.

---

## ✨ Key Features

- **Multi-Signal CIB Detection:** Detects coordinated inauthentic behavior across 5 orthogonal networks (co-tweet, co-similarity, co-link, co-retweet, co-reply) within configurable 60-second sliding windows using the QUT coordination-network-toolkit and Louvain community detection.
- **Physical Gathering & Early Warning Extraction:** IBM Bob extracts offline gathering locations and timings directly quoted from posts, calculating the critical lead time between digital coordination and planned offline assembly.
- **X API v2 Native Relational Normalization:** Ingests native X API v2 JSON (search, user timelines, filtered stream), stores it in a per-dataset SQLite relational schema (`x.db`), and provides forensic exploration of posts, quotes, and threads.
- **Statutory Indian Legal Mapping:** Automatically suggests validated legal sections from a strict BNS 2023 (Sections 196, 197, 351, 353, 356, 79) and IT Act 2000 (Sections 66D, 69A) reference table for legal officer review.
- **Section 63 BSA Court-Admissible Dossier:** Generates time-stamped, print-ready Police Threat Escalation Briefs with SHA-256 cryptographic hashes of the entire dataset and every cited evidence post for judicial scrutiny.
- **Conversational Investigation via FastMCP:** Features a dedicated Model Context Protocol server allowing duty officers to investigate campaigns conversationally directly inside Bob Chat.

---

## 🛠️ Architecture & Pipeline

```
[ Raw X API v2 JSON Stream / Batch ]
             │
             ▼
┌───────────────────────────────────────┐
│ 1. Ingestion & Relational Storage     │ ➔ SQLite (`x.db`) relational normalization
│    (`engine/xstore.py`)               │    Unified SQL view (`posts`)
└───────────────────┬───────────────────┘
                    │
                    ▼
┌───────────────────────────────────────┐
│ 2. Multi-Signal Graph Fusion          │ ➔ 5 Temporal networks (Δt ≤ 60s)
│    (`engine/coordination.py`)         │    Repeat-edge thresholding (min_weight ≥ 2)
└───────────────────┬───────────────────┘
                    │
                    ▼
┌───────────────────────────────────────┐
│ 3. Campaign Clustering & Scoring      │ ➔ Deterministic Louvain Modularity (seed=42)
│    (`engine/campaigns.py`, `scoring`) │    6-Factor CIB Risk Score (0–100)
└───────────────────┬───────────────────┘
                    │
                    ▼
┌───────────────────────────────────────┐
│ 4. IBM Bob Threat Intelligence Layer  │ ➔ Headless CLI (`bob run --format json`)
│    (`src/bob/client.py`, `legal.py`)  │    Physical event extraction + BNS sections
└───────────────────┬───────────────────┘
                    │
                    ▼
┌───────────────────────────────────────┐
│ 5. Dissemination & Operational UI     │ ➔ React 19 + Cytoscape.js interactive graph
│    (`src/web/`, `brief/render.py`)    │    Print-ready SHO Dossier (HTML / PDF)
└───────────────────┬───────────────────┘
                    │
                    ▼
┌───────────────────────────────────────┐
│ 6. Model Context Protocol (MCP)       │ ➔ FastMCP server (`src/mcp_server/server.py`)
│    (`src/mcp_server/`)                │    Conversational investigation via Bob Chat
└───────────────────────────────────────┘
```

Detailed architectural diagrams and component specifications are documented in [`docs/architecture.md`](docs/architecture.md) and [`PROJECT_SPECIFICATION.md`](PROJECT_SPECIFICATION.md).

---

## 📸 Interface & Workflow

| Overview: Threat, Timeline & Spread | Network: Coordinated Community Topology |
|---|---|
| ![Overview](demo/screenshots/02-overview.png) | ![Network](demo/screenshots/03-network.png) |

| IBM Bob Threat Assessment & Spread Detail | Section 63 BSA Threat Dossier |
|---|---|
| ![IBM Bob assessment](demo/screenshots/04-bob-assessment.png) | ![Threat Brief](demo/screenshots/05-threat-brief.png) |

*(Full screenshot walkthrough available in [`demo/screenshots/README.md`](demo/screenshots/README.md).)*

---

## 🏛️ Indian Legal Framework (BNS 2023 & IT Act)

All statutory suggestions are filtered against our verified legal reference table (`.bob/rules-osint-analyst/01-legal-table.md`) and clearly marked for legal officer verification:

| Section Code | Law (2024) | Corresponding IPC | Forensic Scope |
|---|---|---|---|
| `BNS-353` | BNS Section 353 | IPC 505 | Statements conducing to public mischief (rumours causing fear or alarm) |
| `BNS-61` | BNS Section 61 | IPC 120A/120B | Criminal conspiracy (coordinated multi-account rings) |
| `BNS-196` | BNS Section 196 | IPC 153A | Promoting enmity between religious or regional groups |
| `BNS-351` | BNS Section 351 | IPC 506 | Criminal intimidation |
| `BNS-356` | BNS Section 356 | IPC 499/500 | Defamation and reputational attacks |
| `BNS-79` | BNS Section 79 | IPC 509 | Word, gesture or act insulting the modesty of a woman |
| `ITA-66D` | IT Act Section 66D | — | Cheating by personation using computer resources (sock puppets) |
| `ITA-69A` | IT Act Section 69A | — | Platform takedown requests through proper government channels |
| `BNSS-163` | BNSS Section 163 | CrPC 144 | Preventive public order directives |
| `BSA-63` | BSA Section 63 | Evidence Act 65B | Electronic record hash certificate (SHA-256 integrity chain) |

*Note: Banned or struck-down sections (e.g. IT Act Section 66A) are strictly blocked.*

---

## ⚡ Quickstart & Installation

### 1. Prerequisites
- **Python 3.10+**
- **Node.js 22+** and **npm**
- **Git**
- (Optional) **IBM Bob Shell** for live AI inference (`bob.ibm.com/download`)

### 2. Setup
```bash
# Clone the repository
git clone https://github.com/Tirth-chokshi/social-threat-intel-engine.git
cd social-threat-intel-engine

# Install backend dependencies
python -m pip install -r src/requirements.txt

# Build the React frontend
cd src/web && npm ci && npm run build && cd ../..

# Configure environment variables (optional for pre-assessed cached datasets)
cp src/.env.example src/.env
```

### 3. Run Application
```bash
python src/main.py
```
Open **http://127.0.0.1:8000** in your browser. Upload any X API v2 JSON dataset or connect to an live stream; analysis triggers automatically.

Full setup instructions, troubleshooting, and configuration options: [`docs/setup-guide.md`](docs/setup-guide.md).

To deploy a password-protected demo on Render, follow [`docs/deployment.md`](docs/deployment.md). The deployment does not include local environment files or data and leaves IBM Bob and X API credentials unset.

---

## 🔍 Conversational Investigation via Bob Chat (MCP)

Investigate detected campaigns conversationally in Bob Chat:
1. In the repository root, start Bob Chat:
   ```bash
   bob chat
   ```
2. Switch to the OSINT Analyst mode:
   ```
   /mode osint-analyst
   ```
3. Interrogate the dataset:
   - *"List all datasets and summarize the top coordinated campaign."*
   - *"Which accounts started campaign c1, on which platform, and does any campaign call an offline gathering?"*
   - *"Show the first posts of campaign c3 and tell me which account posted first."*

Bob queries the read-only `threat-intel` FastMCP server (`src/mcp_server/server.py`) and cites verified post IDs from the analyzed data.

---

## 👥 Core Maintainers & Authors

| Name | Role | Email | Focus Area |
|---|---|---|---|
| **Tirth Chokshi** | Lead / Forensics Architect | chokshitirth4@gmail.com | System Architecture, Coordination Engine & Pipeline |
| **Milind Pawar** | Frontend Engineering Lead | milindpawar1639@gmail.com | React 19 UI, Cytoscape Graph & Interactive Timeline |
| **Jainik Devada** | Bob Layer & MCP Engineer | jainikmali123@gmail.com | IBM Bob Integration, MCP Server, Legal Mapping |
| **Jigar Jariwala** | Data & Evaluation Engineer | jigarjari09@gmail.com | Scenario Synthesis, Real Data Adapters, Evaluation |

---

## ⚖️ Ethics, Safety & Responsible AI

1. **Behavior First, Content Agnostic:** Detection focuses on inauthentic synchronization patterns rather than suppressing political speech.
2. **Strict Non-Profiling Guardrail:** The system enforces `.bob/rules-osint-analyst/03-no-profiling.md`—it never infers or labels religion, caste, community, or political affiliation.
3. **Decision Support, Not Executive Verdicts:** All AI outputs are designated as intelligence leads for trained investigating officers and require legal verification before executive action.

---

## 📜 Documentation Index

- [Project Specification & Technical Whitepaper](PROJECT_SPECIFICATION.md)
- [System Architecture & Data Flow](docs/architecture.md)
- [Setup & Deployment Guide](docs/setup-guide.md)
- [Render Demo Deployment](docs/deployment.md)
- [Problem Statement & Background](docs/problem-statement.md)
- [Solution Overview & Pipeline Mechanics](docs/solution-overview.md)
- [UI Design System ("Case File")](docs/design-system.md)
- [X API v2 Relational Data Model](docs/data-model.md)
- [Contributing Guidelines](CONTRIBUTING.md)

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

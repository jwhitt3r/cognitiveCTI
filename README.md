# Cognitive CTI

**An open-source, AI-driven pipeline for automated Cyber Threat Intelligence (CTI) aggregation, analysis, and correlation.**

---

## Overview

Cognitive CTI is a project designed to implement enterprise-grade CTI technologies using open-source tools. It answers the question: *Can we implement non-trivial automation and AI analysis without compromising on modern work environment features?*

This pipeline ingests threat data from various layers (Vendor, Research, IOCs, Threat Actor), filters noise via tiered routing, and utilizes local Large Language Models (LLMs) to generate structured intelligence assessments and cross-report correlations.

For a deep dive into the architecture and the philosophy behind this project, please read the full [Architecture Documentation](docs/README.md) or visit the blog at [blog.overresearched.net](https://blog.overresearched.net).

## Architecture

The system follows an Extract, Load, Transform (ELT) pattern augmented by an AI Cognitive Layer.

![High Level Architecture](docs/diagrams/high_level_architecture.png)

### Key Capabilities
* **Layered Intelligence Collection:** Aggregates data from Vendor Bulletins, Independent Research, IOC feeds, and Telegram channels.
* **Tiered Routing:** Automatically classifies reports to filter out noise (e.g., bulk CVEs, telegram chatter) and prioritize high-value intelligence.
* **AI-Powered Analysis:** Uses **Ollama** (Llama 3.2 & Phi-4) to extract entities, summarize content, and map TTPs to MITRE ATT&CK.
* **Cross-Report Correlation:** Identifies patterns and trends across 12-hour batches of intelligence reports.
* **Multi-Channel Output:** Delivers real-time summaries to Discord and stores structured data in PostgreSQL/OpenCTI.

## Tech Stack

The pipeline is built on the "shoulders of giants," leveraging:

* **Orchestration:** [N8N](https://n8n.io/) (via [AI-Starter-Kit](https://docs.n8n.io/hosting/starter-kits/ai-starter-kit/))
* **TI Platform:** [OpenCTI](https://github.com/OpenCTI-Platform/docker)
* **AI/Inference:** Ollama & Qdrant (Vector Store)
* **Database:** PostgreSQL & PGAdmin
* **Ingestion:** RSSBridge (for Telegram & Web scraping)

## System Requirements

To run the full pipeline (including local LLM inference), the following minimum specifications are required:

* **RAM:** 32GB Minimum (Required for running OpenCTI stack + LLMs concurrently).
* **CPU:** Modern Multi-core CPU.
* **GPU (Optional):** Highly recommended for faster model processing, though CPU-only inference is supported.
* **Software:** Docker & Docker Compose.

## Getting Started

### 1. Configuration & API Keys
Before deploying, you must generate the necessary API keys and UUIDs.

**Required API Keys:**
* [MalwareBazaar](https://auth.abuse.ch/)
* [AlienVault OTX](https://otx.alienvault.com/)
* [NIST CVE Database](https://nvd.nist.gov/developers/request-an-api-key)

**Environment Setup:**
1.  Navigate to `docker/opencti/`.
2.  Copy `.env.example` to `.env`.
3.  Generate UUIDv4 strings for any fields marked `<NEEDS GENERATING_UUIDv4>` using [uuidgenerator.net](https://www.uuidgenerator.net/).
4.  Populate the API keys at the bottom of the file:

```bash
MALWAREBAZAAR_API=your_key_here
ALIENVAULT_API=your_key_here
NIST_CVE_API=your_key_here
```

### 2. Deployment
The Docker Compose configurations are located in the docker/ directory.

```Bash
cd docker/opencti
docker-compose up -d
```

### 3. Database Initialization
Once the PostgreSQL container is running:

1. Access PGAdmin.

2. Run the initialization script located at database/initdb.sql.

3. This will create the necessary schema to store structured threat records.

### 4. N8N Pipeline Setup
- Access your N8N instance.

- Import the pipeline workflow from n8n/cognitive_cti_pipeline.json.

- Configure the following credentials within N8N:

    - Discord Bot: Create a new application in the Discord Developer Portal.

    - PostgreSQL: Connect to your local DB.

    - OpenCTI: Connect to your local OpenCTI instance.

### 5. Feed Configuration
A list of recommended feeds is available in `opencti/opencti_feeds_dump.txt`. Telegram feed utility scripts can be found in the telegram/ directory to assist with RSS-Bridge configuration.

🧠 Models
For details on the specific models (Llama 3.2, Phi-4) and system prompts used in this pipeline, please refer to the [Models Documentation](models/README.md).

This repository contains the code and systems to allow anyone to adapt or use Cognitive CTI within their own network.
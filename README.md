# 🔭 NetLens — Enterprise NetDevOps Orchestration & Observability Platform

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python&logoColor=white)](https://python.org)
[![Framework: Flask](https://img.shields.io/badge/Framework-Flask-000000.svg?logo=flask)](https://flask.palletsprojects.com/)
[![Tests](https://img.shields.io/badge/Tests-27%20Automated%20Suites-brightgreen.svg)]()
[![NetDevOps](https://img.shields.io/badge/Architecture-NetDevOps%20%7C%20IaC-blueviolet)]()
[![Security](https://img.shields.io/badge/Security-Fernet%20%7C%20Anti--TOCTOU%20%7C%20Sanitized-red)]()

> **NetLens** is an enterprise-grade NetDevOps automation, device provisioning, and network observability engine designed for mission-critical campus and datacenter infrastructures. It combines deterministic infrastructure-as-code principles, real-time telemetry, and multi-vendor hardware driver abstractions.

---

## 🏛️ System Architecture

```text
               ┌────────────────────────────────────────────────────────┐
               │          Web UI / RESTful Client Interface             │
               └───────────────────────────┬────────────────────────────┘
                                           │
                                  [ Change Intent ]
                                           ▼
┌───────────────────────────────────────────────────────────────────────────────────────┐
│                           PROVISION ORCHESTRATOR                                      │
│                                                                                       │
│   ┌────────────────────┐     ┌───────────────────────┐     ┌──────────────────────┐   │
│   │   Policy Engine    │ ──▶ │   Dependency Engine   │ ──▶ │  Idempotency Engine  │   │
│   │ (Freshness Guard)  │     │ (Read-Only Discovery) │     │ (Re-execution Safety)│   │
│   └────────────────────┘     └───────────────────────┘     └──────────────────────┘   │
│                                          │                                            │
│                                          ▼                                            │
│   ┌────────────────────┐     ┌───────────────────────┐     ┌──────────────────────┐   │
│   │    Risk Engine     │ ──▶ │ Plan Hash (SHA-256)   │ ──▶ │ Approval & Anti-     │   │
│   │(Predictive Scoring)│     │ Immutable Artifact    │     │ Tamper Quad-Check    │   │
│   └────────────────────┘     └───────────────────────┘     └──────────────────────┘   │
└──────────────────────────────────────────┬────────────────────────────────────────────┘
                                           │
                         [ Asynchronous Execution Queue ]
                                           ▼
┌───────────────────────────────────────────────────────────────────────────────────────┐
│                                 JOB ENGINE                                            │
│      (ThreadPoolExecutor · Atomic State Transitions · Crash Recovery · Flock Locks)   │
└──────────────┬───────────────────────────┬────────────────────────────┬───────────────┘
               │                           │                            │
               ▼                           ▼                            ▼
   ┌───────────────────────┐   ┌───────────────────────┐   ┌────────────────────────┐
   │    Network Drivers    │   │ Source of Truth (DCIM)│   │ Telemetry & Monitoring │
   │  Aruba · Dell · HPE   │   │        NetBox         │   │   Zabbix · LibreNMS    │
   │   Comware · 3Com      │   │     (REST API v3)     │   │   NetDisco (LLDP/CDP)  │
   └───────────────────────┘   └───────────────────────┘   └────────────────────────┘
```

---

## ⚡ Key Highlights

### 1. Deterministic Change Planning & State Machine
* **Plan-Before-Apply:** Zero direct mutations without dry-run preview and explicit validation.
* **Cryptographic Anti-Tamper:** Every plan receives a deterministic **SHA-256 hash**. If the configuration or state mutates between generation and approval, execution is strictly rejected.
* **Autonomous Governance Engines:**
  * **`PolicyEngine`**: Enforces compliance windows and data freshness policies.
  * **`DependencyEngine`**: Performs non-intrusive discovery to check pre-conditions.
  * **`IdempotencyEngine`**: Evaluates whether the target state is already active, eliminating redundant network write operations.
  * **`RiskEngine`**: Calculates risk scores for operations (trunk changes, VLAN reassignments, uplink alterations).
  * **`ReconciliationEngine`**: Continuously diffs Canonical State vs. Desired State.

### 2. Multi-Vendor Network Drivers
Modular command builders, terminal screen scrappers, and parsers supporting:
* **Aruba** (AOS-S, ArubaOS-CX, HP ProCurve)
* **Dell EMC** (PowerSwitch / Force10)
* **HPE Comware** (V5 / V7)
* **Stanton & 3Com Legacy Switches**
* SSH Transport with automated retry, backoff, and strict `readonly_guard` defenses.

### 3. Native Source-of-Truth & Observability Integrations
* **NetBox (DCIM / IPAM):** Full bi-directional synchronization of devices, interfaces, IP addresses, and virtualization clusters.
* **Zabbix (JSON-RPC):** Automated host provisioning, SNMP interface alignment, template assignment, and active alert queries.
* **LibreNMS & NetDisco:** Real-time port discovery, LLDP/CDP topology tracking, and link state correlation.

### 4. Real-Time Telemetry & Heuristics
* **`stp_tracker.py`**: Topology change detection, root bridge migration tracking, and Spanning Tree loop mitigation.
* **`port_event_tracker.py`**: Flapping detection, speed/duplex mismatch diagnostics.
* **`bottleneck_detector.py`**: Identification of interface saturation and dropped frames.
* **`path_tracer.py`**: Layer-2 and Layer-3 path reconstruction across the fabric.

### 5. Enterprise Security & Concurrency Defense
* **Deep Secret Redaction (`SecretSanitizer`):** Recursive textual and dictionary parsing removing SNMP communities, passwords, JWTs, and bearer tokens before log emission.
* **Encryption at Rest (`SecretService`):** High-entropy Fernet symmetric encryption for sensitive configuration attributes.
* **Anti-TOCTOU File Locking:** File-level synchronization using `fcntl.flock` to prevent race conditions during parallel state updates.

---

## 🧪 Testing & Quality Assurance

NetLens contains **27 comprehensive automated test suites** covering unit, integration, and security regression domains:

```bash
# Run the complete test suite
pytest -v
```

Highlights of tested behaviors:
* `test_provision_orchestrator.py`: Multi-stage change plan generation and hash verification.
* `test_provision_idempotency_engine.py`: Validation of zero-mutation when state matches desired intent.
* `test_provision_risk_engine.py`: Verification of risk score ceilings on critical uplinks.
* `test_port_events_stp_flapping.py`: Real-time STP anomaly and flap simulation.
* `test_sprint_10_9_0_security_hardening.py`: Verification of token redaction and credentials protection.

---

## 🚀 Quickstart

### Prerequisites
* Python 3.10+
* Linux / macOS / WSL2

### Installation

```bash
# Clone the repository
git clone https://github.com/LucasMereu/netlens.git
cd netlens

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp config.example.json config.json
# Edit config.json with your laboratory/production endpoints
```

### Running the Application

```bash
python main.py
# Server will start on http://127.0.0.1:5001
```

---

## 📄 License
This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

**Developed with precision by [Lucas Mereu](https://github.com/LucasMereu)**  
*Cibersegurança & NetDevOps Engineering*

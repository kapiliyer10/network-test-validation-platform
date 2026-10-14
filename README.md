# Network Test & Validation Platform

## 1. Project Overview

The Network Test & Validation Platform is a Python-based framework for validating network behavior in a controlled lab.

It is a separate project from the Network Automation & Programmability Platform (Project 1).

- **Project 1** configures network devices, discovers state, detects configuration drift, and applies configuration.
- **Project 2** tests network behavior, validates connectivity and routing, and reports test results.

Project 2 reuses Project 1's existing Containerlab testbed. It does not maintain a duplicate topology or configuration system.

## 2. Current Scope

The initial implementation establishes the test environment and verifies that Project 2 can discover the running Project 1 router containers.

Planned capabilities include:

- Connectivity validation
- Routing and OSPF validation
- Failure and recovery testing
- Traffic performance testing
- Packet capture and analysis
- Automated test reporting
- CI/CD integration

These are planned capabilities, not all completed features.

## 3. Technology Stack

- Python 3.12
- Docker SDK for Python
- Docker Engine
- pytest
- Containerlab
- Nokia SR Linux

## 4. Relationship with Project 1

Project 2 uses the existing three-router Project 1 lab:

```text
        R1
       /  \
      /    \
     R2----R3
```

The logical router names are R1, R2, and R3. Their containers are named:

```text
clab-srl-lab-R1
clab-srl-lab-R2
clab-srl-lab-R3
```

Project 1 remains responsible for creating, configuring, and managing this lab. Project 2 checks whether the environment is ready for testing.

Repository separation is intentional: the projects have independent Python environments, dependencies, source code, and responsibilities.

## 5. Prerequisites

Before running Project 2, ensure that you have:

- Python 3.12
- Docker Engine running and accessible to your user
- The Project 1 repository and its Containerlab prerequisites
- The Project 1 lab running in the same Docker environment that Project 2 can access

The Docker Python package does not install or start Docker Engine.

## 6. Start the Project 1 Lab

From the Project 1 repository:

```bash
cd ~/network-automation-platform
./scripts/lab_up.sh
```

Wait for the lab to start before running Project 2 checks.

Project 1's topology references configuration files beneath `~/network-automation-platform`. Keep that expected location unless the topology paths have been deliberately adapted.

## 7. Set Up Project 2

From the Project 2 repository:

```bash
cd ~/network-test-validation-platform

python3.12 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The `requirements.txt` file pins the Python package versions used by the current environment.

Check for dependency conflicts:

```bash
python -m pip check
```

Expected output:

```text
No broken requirements found.
```

## 8. Check Lab Readiness

With the Project 2 virtual environment activated, run:

```bash
python -m scripts.check_lab_readiness
```

When all required router containers exist and are running, the output is:

```text
Project 1 lab is READY.
Running routers: R1, R2, R3
```

The check reports an error when Docker cannot be accessed, a required router is missing, or a router is not running.

This is an environment-readiness check; it does not by itself prove that routing or end-to-end connectivity works.

## 9. Run the Integration Test

Run the router-discovery integration test:

```bash
pytest -v tests/integration/test_lab_discovery.py
```

This test uses the real Docker environment to verify that R1, R2, and R3 are discoverable and running.

The test requires the Project 1 lab to be running.

## 10. Current Status

**Milestone 1 — Test Environment Foundation:** In progress.

Completed:
- Separate Project 2 repository and virtual environment
- Pinned Python dependencies
- Real Docker-based router discovery
- Router-discovery integration test
- Lab-readiness command
- Manual connectivity checks for the three directly connected router pairs

Remaining:
- Complete and verify the environment setup documentation
- Confirm the environment can be prepared reliably by following the documented procedure

Connectivity automation and the later validation capabilities remain subsequent milestones.

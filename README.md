# Network Test & Validation Platform

## 1. Project Overview

The Network Test & Validation Platform is a Python-based framework for
testing and validating network behavior in a controlled lab.

It is separate from Project 1, the Network Automation & Programmability
Platform.

- **Project 1** configures network devices, discovers device state,
  detects configuration drift, and applies configuration.
- **Project 2** validates connectivity, network behavior, protocol state,
  failure recovery, and traffic performance, and collects test evidence.

Project 2 reuses the existing Project 1 Containerlab environment. It does
not duplicate Project 1's configuration management or network-state
management systems.

## 2. Architecture

The current test execution flow is:

    Test definitions in configs/lab.yaml
                    |
                    v
             src/testbed.py
                    |
                    v
             RouterDevice
                    |
                    v
            src/cli_runner.py
                    |
                    v
        Docker exec -> SR Linux CLI
                    |
                    v
           Output validation
                    |
                    v
              Test result

The `Testbed` abstraction resolves logical router names to the existing
Docker containers. `RouterDevice` provides a common command-execution
interface, and the existing CLI runner performs the actual interaction.

The implementation intentionally remains small. It does not recreate
Project 1's inventory, discovery, configuration, or drift-detection
architecture.

## 3. Technology Stack

Core:
- Python 3.12
- Linux
- Git
- Docker Engine and Docker SDK for Python
- Containerlab
- pytest
- pyATS AEtest
- PyYAML

Network testing and troubleshooting:
- ICMP connectivity tests
- TCP-probe diagnostics
- Planned routing, protocol, and interface validation
- Planned iPerf3 traffic testing
- Planned tcpdump and Wireshark analysis

Genie parsing and native pyATS/Unicon integration for Nokia SR Linux have
not been established. The current AEtest implementation reuses the
existing Docker-based CLI runner.

## 4. Relationship with Project 1

Project 2 uses the existing three-router Project 1 lab:

        R1
       /  \
      /    \
     R2----R3

The Docker containers are:

    clab-srl-lab-R1
    clab-srl-lab-R2
    clab-srl-lab-R3

Project 1 remains responsible for creating, configuring, and managing the
network. Project 2 verifies behavior through tests.

The repositories and Python environments are separate. The projects
share the existing lab but maintain separate responsibilities,
dependencies, source code, and test workflows.

## 5. Prerequisites

Before running Project 2, ensure that:

- Python 3.12 is available.
- Docker Engine is running and accessible to your user.
- The Project 1 repository and its Containerlab prerequisites are installed.
- The Project 1 lab is running and accessible from Project 2.

The Docker Python package does not install or start Docker Engine.

## 6. Start the Project 1 Lab

From the Project 1 repository:

    cd ~/network-automation-platform
    ./scripts/lab_up.sh

Wait for the lab to start before running Project 2 integration tests.

The existing Project 1 topology expects its configuration files beneath
`~/network-automation-platform`. Keep that location unless the topology
paths have been deliberately adapted.

## 7. Set Up Project 2

Create and activate the Project 2 virtual environment:

    cd ~/network-test-validation-platform

    python3.12 -m venv .venv
    source .venv/bin/activate

Install the pinned dependencies:

    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt

The requirements file includes the verified pyATS 26.9 dependency set
alongside the project's existing Python dependencies. Genie is not
currently included.

Check dependency health:

    python -m pip check

Expected output:

    No broken requirements found.

## 8. Check Lab Readiness

With the Project 2 environment activated:

    python -m scripts.check_lab_readiness

The check verifies that Docker is accessible and the required router
containers are present and running.

Expected output when the lab is ready:

    Project 1 lab is READY.
    Running routers: R1, R2, R3

Readiness alone does not prove that routing or connectivity works.

## 9. Run pytest

Run the complete pytest suite:

    pytest -q

Run unit tests independently:

    pytest -q -m unit

Run integration tests independently:

    pytest -q -m integration

Current verified results:

- Full pytest suite: 10 passed
- Unit tests: 6 passed
- Integration tests: 4 passed

The unit tests cover the Docker client and testbed configuration
resolution. Integration tests include real Docker-based router discovery
and TCP-probe diagnostics.

The TCP-probe tests do not establish successful application-level TCP
connections. Their results are diagnostic evidence about TCP probe
responses.

## 10. Run pyATS AEtest Suites

Activate the Project 2 virtual environment before running these commands.

Run the connectivity tests:

    python tests/aetest/connectivity.py

Run interface validation:

    python tests/aetest/interfaces.py

Run OSPF neighbor validation:

    python tests/aetest/ospf.py

Run route validation:

    python tests/aetest/routes.py

The current AEtest suites cover 21 configured validation cases:

- 3 ICMP connectivity checks across the configured router pairs
- 6 Ethernet interface operational-state checks
- 6 OSPF neighbor checks covering expected router IDs and FULL adjacency
  state
- 6 OSPF-learned remote loopback route checks, including prefix, route
  type, next hop, outgoing interface, and best-route status

The tests execute commands through the existing Project 2 testbed and CLI
runner. The runner uses Docker to invoke the SR Linux CLI within each
router container.

These tests validate actual operational output from the running lab.
They do not establish native Unicon connection-plugin support or built-in
Genie parsing for Nokia SR Linux. The route and interface validation
currently uses parsing tailored to the observed SR Linux CLI output.

## 11. Current Implementation Status

### Milestone 1 — Test Environment and Project 1 Integration

Status: Complete.

- Separate repository and virtual environment
- Pinned dependencies
- Docker-based router discovery
- Lab-readiness check
- Setup documentation

### Milestone 2 — pytest Framework and Testbed Foundation

Status: Foundation established.

- Unit and integration test categories
- pytest markers
- YAML-based lab and test definitions
- Reusable Testbed and RouterDevice abstractions
- Unit tests for testbed resolution and validation

### Milestone 3 — Connectivity and Transport Validation

Status: In progress.

- Three ICMP connectivity cases verified through AEtest
- TCP traceroute probes retained as diagnostics
- Application-level TCP connectivity not yet verified
- Dedicated TCP/UDP traffic endpoints not yet implemented

### Milestone 4 — Testbed and pyATS Integration

Status: Initial integration verified.

- pyATS AEtest runs YAML-driven network validation scenarios
- pyATS 26.9 dependencies are pinned
- Existing Docker-based CLI execution is reused
- Native SR Linux Unicon support and built-in Genie parsing remain
  unverified

### Milestone 5 — Interfaces, Routing, Protocols, and Management

Status: In progress.

- Six Ethernet interface operational-state checks verified
- Six expected OSPF neighbor adjacencies verified as FULL
- Six OSPF-learned remote loopback routes validated
- Additional protocol, management-interface, and VLAN validation
  remains planned

### Remaining milestones

6. Negative testing, failure recovery, and regression
7. Traffic and performance testing
8. Packet capture and troubleshooting
9. Test reporting and quality metrics
10. CI/CD and end-to-end validation

These milestones remain planned until their functionality has been
implemented and verified.

## 12. Development Principles

- Keep Project 1 and Project 2 separate.
- Reuse the existing network instead of rebuilding its configuration
  management in Project 2.
- Write tests that validate observable behavior and meaningful
  requirements.
- Distinguish diagnostic responses from successful application-level
  communication.
- Prefer real-lab integration tests where appropriate and unit tests for
  isolated logic.
- Introduce additional frameworks and abstractions only when they add
  demonstrated value.
- Collect evidence and report failures clearly.

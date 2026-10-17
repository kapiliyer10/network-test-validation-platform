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
- Interface operational-state, OSPF neighbor, and route validation
- Planned iPerf3 traffic testing
- Planned tcpdump and Wireshark analysis

Native pyATS testbed loading and a custom Docker connection adapter
have been verified against the baseline SR Linux lab. The adapter reuses
the existing CLI runner and does not establish a persistent SSH session.
Genie parsers are not used for SR Linux. Structured interface state is
validated using native JSON output and Python's json module.

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

The test suite covers two Containerlab topologies. Until Milestone 10
automates deployment and cleanup, run the test group that matches the
topology currently running. Do not run the entire suite with `pytest -q`
when only one topology is deployed.

### Run the baseline suite

The baseline `srl-lab` contains R1, R2, and R3.

    unset NETWORK_TESTBED_CONFIG
    pytest -q -m "not expanded_lab"

Most recently verified result:

    17 passed, 2 deselected

The two deselected tests are the expanded-lab TCP and UDP application
tests. The baseline suite includes unit tests and router-only integration
tests, including TCP-probe diagnostics.

Run unit tests independently:

    pytest -q -m unit

Run baseline integration tests independently:

    unset NETWORK_TESTBED_CONFIG
    pytest -q -m "integration and not expanded_lab"

### Run the expanded-lab TCP and UDP application tests

The application tests use `configs/lab-expanded.yaml` directly and are
marked `expanded_lab`. They require the expanded topology with H1 and H2.

Deploy that topology from Project 1, after stopping the baseline lab if
required by available memory:

    cd ~/network-automation-platform
    sudo containerlab destroy --topo topology/srl-lab.clab.yml
    sudo containerlab deploy --topo topology/srl-expanded.clab.yml

Then run the application tests from Project 2:

    cd ~/network-test-validation-platform
    pytest -q -m expanded_lab

To inspect which tests will be selected without executing them:

    pytest --collect-only -q -m expanded_lab

Pytest markers select tests; they do not deploy, destroy, or switch
Containerlab topologies. Automating topology lifecycle and the sequential
execution of both groups is reserved for Milestone 10.

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

### Milestone 1 — Test Environment & Project 1 Integration

Status: Complete.

- Separate repository and virtual environment
- Pinned dependencies
- Docker-based router discovery
- Lab-readiness check
- Setup documentation

### Milestone 2 — pytest Framework & Initial Tests

Status: Foundation established.

- Unit and integration test categories
- pytest markers
- YAML-based lab and test definitions
- Reusable Testbed and RouterDevice abstractions
- Unit tests for testbed resolution and validation
- 10 pytest tests collected and passing: 6 unit and 4 integration
- Successful test selection using `pytest -m unit` and `pytest -m integration`
- Separate pyATS AEtest execution for live network validation

### Milestone 3 — Connectivity & Transport Validation

Status: Complete.

- ICMP reachability and TCP-probe diagnostics
- Command timeouts and failure diagnostics
- Expanded-lab TCP and UDP application servers
- Automated TCP/UDP request-response validation from H1 to H2
- Baseline and expanded-lab tests separated using pytest markers

### Milestone 4 — Testbed Abstraction & pyATS Integration

Status: In progress.

- Native pyATS testbed defines R1, R2, and R3
- Custom Docker connection adapter reuses the existing CLI runner
- Native pyATS command execution verified on all three routers
- Native pyATS connectivity validation passed
- Structured interface-state validation passed using SR Linux JSON
- Final regression, documentation, and commit review remain

### Milestone 5 — Interfaces, Routing, Protocols & Management

Status: In progress.

- Six Ethernet interface operational-state checks verified
- Six expected OSPF neighbor adjacencies verified as FULL
- Six OSPF-learned remote loopback routes validated
- Additional protocol, management-interface, and VLAN validation
  remains planned

### Remaining milestones

6. Negative, Failure, Recovery & Regression Testing
7. Traffic & Performance Testing
8. Packet Capture & Troubleshooting
9. Reporting & Quality Metrics
10. CI/CD & End-to-End Validation

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

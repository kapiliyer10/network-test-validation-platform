# Network Test & Validation Platform

## 1. Project Overview

The Network Test & Validation Platform is a Python-based framework for
validating network connectivity, protocol behavior, failure recovery, and
traffic performance in a containerized Nokia SR Linux environment.

The platform is designed around a practical network quality assurance
workflow: define expected behavior, execute tests against a live lab,
compare observed results with expectations, and report failures with
diagnostic evidence.

It is a separate project from the Network Automation & Programmability
Platform.

- **Project 1 — Network Automation:** discovers device state, manages
  configuration, detects configuration drift, and applies changes.
- **Project 2 — Network Validation:** checks whether the network behaves
  as expected before, during, and after normal operations or failures.

Project 2 reuses Project 1's network lab rather than duplicating its
configuration-management and state-management systems.

## 2. Architecture

The platform combines two test execution approaches.

### Router and protocol validation

    YAML test definitions / pyATS testbed
                    |
                    v
            pytest or pyATS AEtest
                    |
                    v
          Testbed and device abstraction
                    |
                    v
            Docker CLI connection
                    |
                    v
            Nokia SR Linux CLI
                    |
                    v
        Parse output and validate state
                    |
                    v
             Test result / evidence

The pytest framework handles conventional unit and integration tests.
Native pyATS AEtest organizes structured network validation into test
cases and sections. The testbed abstraction maps logical device names to
the appropriate lab devices, while the shared CLI runner executes router
commands through Docker.

Validation includes connectivity, interface operational state, OSPF
neighbor state, routing information, LLDP adjacencies, and controlled
failure and recovery scenarios.

### Traffic and performance validation

    configs/lab-expanded.yaml
                |
                v
        pytest performance test
                |
                v
        H1: iperf3 client
                |
                v
        R1 ------ R2
                |
                v
        H2: iperf3 server
                |
                v
    JSON measurements and assertions

The expanded lab provides dedicated Linux traffic endpoints. TCP and UDP
application tests verify request/response behavior, while iperf3 tests collect
structured JSON measurements for throughput, TCP retransmissions, UDP packet
loss, and jitter. ICMP tests measure round-trip latency and packet loss,
including a controlled-delay scenario.

A reusable `src/packet_capture.py` helper runs filtered `tcpdump` captures on
H1's `eth1` interface during each expanded-lab scenario. It waits for capture
readiness, copies the resulting PCAP into `artifacts/pcap/`, and verifies that
packets can be decoded. These files provide packet-level evidence alongside
test results and performance metrics.

Keeping traffic generation on Linux endpoints allows the tests to measure
the routed data path without requiring traffic-generation applications
inside the Nokia routers.

## 3. Technology Stack

### Programming and test automation

- **Python 3.12** — test logic, command execution, result parsing, and
  reusable validation utilities.
- **pytest** — unit tests, integration tests, fixtures, assertions, and
  regression execution.
- **pyATS AEtest** — structured network test cases and validation steps.
- **PyYAML** — configuration-driven test definitions and lab settings.

### Network lab and execution

- **Linux** — endpoint networking and diagnostic utilities.
- **Docker Engine** — runs the router and Linux endpoint containers.
- **Containerlab** — defines and deploys the network topologies.
- **Nokia SR Linux CLI** — interface, routing, protocol, and connectivity
  observations.
- **iperf3** — TCP/UDP traffic generation and performance measurement.
- **tcpdump/libpcap** — filtered packet capture on Linux endpoints.
- **PCAP artifacts** — packet-level evidence for troubleshooting test traffic.

### Validation coverage

Implemented test areas include:

- ICMP connectivity and expected negative connectivity.
- TCP and UDP application-level request/response tests.
- Ethernet interface operational-state validation.
- OSPF neighbor and route validation.
- LLDP adjacency validation.
- Controlled link failure, OSPF failover, and recovery verification.
- TCP throughput profiles at 10, 25, and 50 Mbps with retransmission checks.
- UDP throughput, packet-loss, and jitter validation, including controlled impairments.
- ICMP round-trip latency and packet-loss checks, including controlled delay.
- Automated filtered packet capture for expanded-lab test scenarios.

The native pyATS testbed and custom Docker connection adapter have been
verified against the baseline SR Linux lab. The adapter reuses the
existing CLI runner instead of opening a persistent SSH session. Genie
parsers are not used for SR Linux; structured state is validated using
native JSON output and Python's JSON parser where applicable.

## 4. Relationship with Project 1

Project 1 owns the network automation implementation and the Containerlab
topology definitions. Project 2 consumes the resulting lab as a test
environment and validates its behavior.

Two lab profiles are used for different testing needs.

### Baseline lab — `srl-lab`

The baseline lab contains three Nokia SR Linux routers connected in a
triangle:

    R1 ------ R2
     \        /
      \      /
        R3

Its container names include:

    clab-srl-lab-R1
    clab-srl-lab-R2
    clab-srl-lab-R3

This profile supports router connectivity, interface, OSPF, LLDP, route,
and failure/recovery validation.

### Expanded lab — `srl-expanded`

The expanded lab retains the three-router topology and adds two Linux
traffic endpoints:

    H1 ------ R1 ------ R2 ------ H2
                \      /
                 \ R3 /

H1 connects to R1 using `10.0.14.2/30`, and H2 connects to R2 using
`10.0.24.2/30`. The routers' interconnections provide the routed path
between the endpoints.

The expanded profile supports TCP/UDP application tests, iperf3 throughput,
packet-loss and jitter validation, ICMP latency testing, and automated packet
capture. Its container names use the `clab-srl-expanded-` prefix.

The baseline and expanded profiles are run separately when local resource
constraints prevent both labs from running simultaneously. Tests must
target the lab profile they are configured to use.

The repositories maintain separate responsibilities, source code,
dependencies, and test workflows. Project 1 manages the network;
Project 2 measures and validates its behavior.

## 5. Prerequisites

Before running Project 2, ensure that:

- Python 3.12 is available.
- Docker Engine is running and accessible to your user.
- The Project 1 repository and its Containerlab prerequisites are installed.
- The Project 1 lab is running and accessible from Project 2.

The Docker Python package does not install or start Docker Engine.

## 6. Start the Baseline Project 1 Lab

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

The test suite covers two Containerlab topologies. Run the test group
that matches the topology currently running. Do not run the entire suite
with `pytest -q` when only one topology is deployed.

### Recommended regression command

When the expanded lab is running, use this command to run the expanded-lab
tests and the isolated unit-test group:

```bash
pytest -q -m "expanded_lab or unit"
```

The markers have distinct purposes:

- `unit` selects isolated tests that do not require a live lab.
- `original_lab` selects tests for the baseline `srl-lab` topology.
- `expanded_lab` selects tests for `srl-expanded`.

Markers select tests; they do not deploy, stop, or switch topologies.
Run only the test group that matches the environment currently deployed.

### Run the baseline suite

The baseline `srl-lab` contains R1, R2, and R3.

    pytest -q -m "unit or original_lab"

Last recorded baseline result before the iperf3 performance test was added:

```text
19 passed, 2 deselected
```

This result predates the later TCP/UDP performance tests and the UDP
impairment test. Treat it as historical, not as the current verified result.
Refresh the baseline result with `srl-lab` running before recording a new result.

Run unit tests independently:

    pytest -q -m unit

Run baseline integration tests independently:

    unset NETWORK_TESTBED_CONFIG
    pytest -q -m "integration and original_lab"

### Run the Expanded-Lab Application, Performance, and Latency Tests

The expanded-lab tests require the `srl-expanded` topology with three Nokia SR Linux routers and two Linux endpoints, H1 and H2.

These tests cover:

- TCP application-level request/response validation.
- UDP application-level request/response validation.
- TCP throughput profiles at 10, 25, and 50 Mbps using iperf3.
- UDP throughput, packet-loss, and jitter validation using iperf3.
- Controlled UDP packet-loss detection and cleanup.
- ICMP round-trip latency and packet-loss validation.
- Controlled 20 ms delay detection and cleanup.
- Automated filtered packet capture producing a separate PCAP artifact per test.

#### 1. Prepare the expanded lab

If the baseline `srl-lab` is running and your system cannot accommodate both labs, stop it first.

From the Project 1 repository:

```bash
cd ~/network-automation-platform
./scripts/lab_down.sh
```

Build the endpoint image. It includes the networking utilities, TCP/UDP
application servers, iperf3, and `tcpdump` for packet capture.

```bash
docker build -t network-test-endpoint:1.0 topology/tcp-endpoint
```

Deploy the expanded topology:

```bash
./scripts/lab_expanded_up.sh
```

The expanded topology configures the H1 and H2 interfaces with an MTU of 1500 bytes. It also starts the iperf3 server on H2.

#### 2. Run the expanded-lab test group

Activate the Project 2 virtual environment and run:

```bash
cd ~/network-test-validation-platform
source .venv/bin/activate
pytest -q -m expanded_lab
```

This selects the ten expanded-lab tests covering TCP/UDP applications, iperf3
performance, latency, packet-capture generation, and controlled impairments.

To inspect the selected tests without executing them:

```bash
pytest --collect-only -q -m expanded_lab
```

#### 3. Run an individual performance or impairment test

Run the TCP performance profiles at 10, 25, and 50 Mbps:

```bash
pytest -v -s tests/integration/test_iperf3_performance.py
```

Run the consolidated UDP performance, packet-loss, and jitter tests:

```bash
pytest -v -s tests/integration/test_iperf3_udp.py
```

This module contains three scenarios: normal UDP performance, controlled
packet-loss detection, and controlled jitter detection. The impairment tests
temporarily apply `tc netem` rules to H1's `eth1` egress interface and verify
that the measured impairment exceeds its configured threshold.

Run these impairment tests only in the controlled expanded lab, not on a
production network or while unrelated traffic uses the interface. If cleanup
fails or an unexpected interface state is reported, stop and investigate
before running more tests.

Run the baseline and controlled-delay ICMP latency tests:

```bash
pytest -v -s tests/integration/test_latency.py
```

The baseline test uses BusyBox `ping` to measure minimum, average, and maximum
round-trip time (RTT), as well as packet loss. Its configured limits are an
average RTT of at most 10 ms and zero packet loss.

The controlled-delay test adds 20 ms of delay to traffic leaving H1's `eth1`
interface. It checks that the measured average RTT reaches at least 15 ms and
verifies that the interface returns to its original `noqueue` state afterward.
Run this test only in the controlled expanded lab. If cleanup fails or an
unexpected interface state is reported, stop and investigate before running
more tests.

These thresholds are for the controlled lab, not production performance
requirements.

#### Packet-capture artifacts

Each expanded-lab test saves a PCAP file named after its test case under
`artifacts/pcap/`. The directory is excluded from version control because
these files are generated test artifacts.

The reusable `PacketCapture` helper starts `tcpdump` inside the H1 container,
confirms that capture is ready, stops it after traffic generation, copies the
PCAP to the host, and verifies that packets can be decoded. The capture filter
matches the scenario's destination and TCP/UDP port or ICMP traffic.

If capture shutdown or PCAP validation fails, remote capture files are
preserved for diagnosis. The helper removes remote temporary files after a
successful validation.

**Known limitation:** The current helper stops capture using
`killall -INT tcpdump`, which affects all `tcpdump` processes in H1. Keep
these tests sequential; do not run captures in parallel until shutdown is
limited to the individual test's process.

#### 4. Stop the expanded lab

After testing, stop the expanded topology:

```bash
cd ~/network-automation-platform
./scripts/lab_expanded_down.sh
```

To return to the baseline lab:

```bash
./scripts/lab_up.sh
```

The baseline and expanded labs are separate execution environments. Pytest markers select tests; they do not deploy, destroy, or switch topologies.

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
- Successful test selection using `pytest -m unit` and `pytest -m integration`
- Separate pyATS AEtest execution for live network validation

### Milestone 3 — Connectivity & Transport Validation

Status: Complete.

- ICMP reachability and TCP-probe diagnostics
- Command timeouts and failure diagnostics
- Expanded-lab TCP and UDP application servers
- Automated TCP/UDP request-response validation from H1 to H2
- Baseline and expanded-lab tests separated using pytest markers

### Milestone 4 — Testbed Abstraction & Native pyATS Integration

Status: Complete.

- Native pyATS testbed defines R1, R2, and R3
- Custom Docker connection adapter reuses the existing CLI runner
- Native pyATS command execution verified on all three routers
- Native pyATS connectivity validation passed
- Structured interface-state validation passed using SR Linux JSON
- Native pyATS LLDP validation passed for all six expected Ethernet neighbor relationships
- Baseline pytest regression suite passed after LLDP integration
- Existing AEtest suites also cover six Ethernet interface operational-state
  checks, six OSPF neighbor adjacencies in FULL state, and six OSPF-learned
  remote loopback routes

### Milestone 5 — Negative, Failure, Recovery & Regression Testing

Status: Complete.

- Negative connectivity validation using native pyATS.
- Expected packet loss verified from SR Linux ping statistics.
- CLI runner supports explicit handling of expected non-zero exit codes.
- Unit tests cover optional return-code handling.
- Controlled R1–R2 interface failure tested using a confirmed commit with a 300-second rollback timeout.
- OSPF failover validated by checking the route to R2's loopback through R3.
- Failover convergence checked against a configurable timeout.
- Recovery verified through interface-state checks, bounded ping retries, and restoration of the preferred direct OSPF route through R2.
- The test identifies its own confirmed commit by comparing commit state before and after the change.
- The rejection command runs in the shared default candidate. The test checks that the identified commit reaches status `failed` before the fallback timer could expire and fails if SR Linux explicitly reports that `confirmed-reject` was ignored.
- Preflight checks refuse to start if the shared candidate is already dirty or another confirmed commit is active.
- Cleanup runs `discard now` and verifies that the shared candidate contains no remaining changes.

**Issue encountered and resolution**

The initial cleanup used `enter candidate private`, and the verification expected the rejected commit to reach status `complete`. The router reported the identified rejected commit as `failed`, so the earlier verification incorrectly marked the test as failed. In earlier runs, the test also left `admin-state disable` staged in the shared candidate even after the running interface had recovered.

The test now uses the shared default candidate, identifies the specific confirmed commit, checks its rejection status before the 300-second fallback deadline, detects an explicit ignored-command response, and discards and verifies candidate changes during cleanup. The live test passed with the interface enabled and operationally up, ping connectivity recovered, and the shared candidate clean.

The aggregated CLI output still displayed `Warning: Commit confirmed is still in progress (rollback in 4 minutes)`. Since the runner combines output from candidate entry and the rejection command, that line alone does not identify which command emitted the warning. The passing result is based on the identified commit's early terminal status, the absence of an explicit ignored-command response, and the interface, connectivity, and candidate-cleanup checks.

**Latest validation**

- Focused pyATS failure/recovery run: 2 passed, 0 failed.
- Baseline regression tests using `pytest -q -m "not expanded_lab"`: 27 passed, 10 deselected in 4.52s.

### Milestone 6 — Traffic & Performance Testing

Status: Complete.

#### TCP performance validation

- Added three configuration-driven TCP performance profiles using iperf3: 10 Mbps, 25 Mbps, and 50 Mbps.
- The pytest test uses iperf3 JSON output to validate receiver throughput and TCP retransmissions.
- Each profile specifies its target bitrate, test duration, TCP MSS, minimum receiver throughput, and maximum retransmission count.
- The three profiles passed their individual repeatability checks. Receiver throughput remained close to the target rates under the current expanded-lab conditions.

Representative repeatability results:

| Target bitrate | Receiver throughput observed | Retransmissions observed |
| -------------- | ---------------------------: | -----------------------: |
| 10 Mbps        |              9.96–10.07 Mbps |                      1–4 |
| 25 Mbps        |                   25.06 Mbps |                      4–5 |
| 50 Mbps        |             49.90–50.01 Mbps |                      7–8 |

An earlier exploratory 50 Mbps run exhibited substantial degradation, with 31.8 Mbps receiver throughput and 248 retransmissions. Subsequent runs were stable, but the earlier observation demonstrates that performance variability should not be ignored.

#### UDP performance validation

- Added a separate configuration-driven UDP performance test using iperf3.
- The test validates receiver throughput, packet loss, and jitter using structured JSON results.
- The initial UDP profile targets 10 Mbps for 10 seconds, with a minimum receiver throughput of 9 Mbps, maximum packet loss of 0.1%, and maximum jitter of 1 ms.
- Three automated runs passed, each reporting approximately 10 Mbps receiver throughput and zero packet loss. Measured jitter ranged from 0.034 to 0.092 ms across those runs.

#### Controlled UDP impairment and recovery

- Added an automated negative test that applies a temporary 1% packet-loss rule to H1's `eth1` egress interface using `tc netem`.
- The test passes when measured loss exceeds 0.1%, confirming that the test detects the deliberately introduced packet loss.
- A verified run measured 1.031% loss, or 89 lost packets out of 8,634.
- Cleanup removed the temporary rule and verified that H1's interface returned to `qdisc noqueue`.
- A subsequent normal UDP test passed with 9.998 Mbps receiver throughput, zero packet loss, and 0.066 ms jitter.

The impairment test is intended for the controlled test lab only. Do not run
it on a production network or while unrelated traffic uses the interface.

#### Controlled UDP jitter validation

- Added a configuration-driven jitter scenario to the consolidated UDP test module.
- The test applies 20 ms of base delay with 5 ms of delay variation to H1's `eth1` egress interface.
- UDP traffic runs at a configured 1 Mbps target for the experiment.
- A verified run measured 0.999 Mbps receiver throughput, 2.905 ms jitter, and 0% packet loss (0/864 packets).
- The test passed its minimum-jitter requirement of 1.0 ms and verified that the interface returned to `qdisc noqueue`.

Run this controlled experiment only in the expanded test lab. It temporarily
changes traffic handling on H1 and must not run on a production network or
while unrelated traffic uses the affected interface.

#### ICMP latency and controlled delay validation

- Added a configuration-driven ICMP latency test using BusyBox `ping`.
- The baseline test checks minimum, average, and maximum RTT, plus packet loss.
- The baseline profile requires an average RTT of at most 10 ms and zero packet loss.
- Added a controlled-delay test that applies a temporary 20 ms delay to H1's `eth1` egress interface.
- The impairment test passes when average RTT reaches at least 15 ms and verifies that the interface returns to `qdisc noqueue` during cleanup.

Verified results:

| Scenario | RTT result | Packet loss | Result |
| --- | --- | --- | --- |
| Baseline | Min 0.750 ms, avg 1.001 ms, max 1.266 ms | 0% (5/5 replies) | Passed |
| 20 ms added delay | Average 21.032 ms | 0% | Passed |

The controlled-delay test changes the running lab temporarily. Use it only in
the expanded test lab, not on a production network or while unrelated traffic
uses the affected interface.

#### Integration and regression validation

At Milestone 6 completion, before packet-capture integration, the
expanded-lab test group contained ten tests:

- TCP and UDP application request/response validation.
- TCP performance profiles at 10, 25, and 50 Mbps.
- Three UDP scenarios in `test_iperf3_udp.py`: normal performance, packet-loss detection, and jitter detection.
- Baseline ICMP latency validation.
- Controlled ICMP delay detection and cleanup.

Before Milestone 7 packet-capture integration, the expanded-lab suite passed:

```text
10 passed, 19 deselected in 65.91s
```

Before Milestone 7 packet-capture integration, the recommended regression
command passed:

```text
25 passed, 4 deselected in 65.72s
```

The command used for that historical regression result was:

```bash
pytest -q -m "expanded_lab or not integration"
```

These results validate the configured tests under the current containerized
lab conditions. They do not establish maximum network capacity or production
performance limits.

### Milestone 7 — Packet Capture & Troubleshooting

**Status:** Complete. Packet-capture implementation, both topology-specific regressions, Wireshark analysis, and controlled-failure investigation are verified.

#### Reusable packet-capture utility

- Added `src/packet_capture.py` with the `PacketCapture` lifecycle and
  `PacketCaptureError` exception.
- The helper starts filtered `tcpdump` in a Docker endpoint, waits for
  readiness, stops the capture after traffic generation, copies the PCAP to
  the project, and verifies that decoded packets are present.
- Unique remote filenames prevent temporary capture files from different
  test cases from colliding.
- Remote files are removed after successful validation and retained for
  diagnosis when capture shutdown or PCAP validation fails.
- The endpoint image includes `tcpdump` alongside the existing networking
  utilities and traffic-generation tools.
- Added `/artifacts/pcap/` to `.gitignore` so generated captures are not
  committed.

#### Test integration

Automated packet capture is integrated into all ten expanded-lab tests:

- TCP and UDP application request/response tests.
- TCP iperf3 profiles at 10, 25, and 50 Mbps.
- UDP iperf3 normal-performance, packet-loss, and jitter scenarios.
- Normal ICMP latency and controlled 20 ms delay scenarios.

Each scenario saves a separate PCAP file and fails if its capture contains
no decoded packets.

#### Verification

Latest unit-test result:

```text
23 passed, 14 deselected in 0.21s
```

Latest expanded-lab test result:

```text
10 passed, 27 deselected in 96.81s
```

Latest combined regression result using the README-recommended command
`pytest -q -m "expanded_lab or unit"`:

```text
33 passed, 4 deselected in 106.78s
```

The expanded-lab run verified TCP/UDP exchanges, throughput, packet-loss and
jitter detection, ICMP latency, PCAP generation, and restoration of `noqueue`
after controlled impairments. Python compilation and `git diff --check`
also passed.

The original-lab test group contains four tests: router discovery and three
TCP-probe cases. With the baseline `srl-lab` deployed, all four tests passed:

    4 passed, 33 deselected in 4.29s

The original-lab tests and expanded-lab tests were run separately against
their intended topologies. Across the unit, expanded-lab, and original-lab
runs, all 37 collected tests passed, with no failures.

#### Wireshark analysis and controlled-failure investigation

The following representative captures were opened and inspected in Wireshark.

- **TCP echo** (`H1_to_H2_tcp_echo.pcap`): the capture showed the TCP handshake,
  application data in both directions, and FIN/ACK closure. Follow TCP Stream
  displayed the request `NETWORK_VALIDATION` and response
  `TCP_OK:NETWORK_VALIDATION`.
- **UDP echo** (`H1_to_H2_udp_echo.pcap`): two UDP datagrams showed the request
  `NETWORK_VALIDATION` and response `UDP_OK:NETWORK_VALIDATION`. This confirms
  the captured exchange, not guaranteed delivery of other UDP datagrams.
- **Baseline ICMP** (`H1_to_H2_icmp_latency.pcap`): five Echo Requests and
  five matching Echo Replies were visible, with no missing reply among those
  five exchanges.
- **Normal UDP performance** (`H1_to_H2_udp_10Mbps.pcap`): the inspected
  sequence numbers were consecutive, and a Wireshark packet-details search
  for `UDP packet loss or out of order delivery` found no match.
- **Controlled UDP loss** (`H1_to_H2_udp_10Mbps_with_1pct_loss.pcap`):
  Wireshark flagged an iPerf3 sequence gap, showing sequence 14 after
  sequence 12. The recorded receiver report measured 89 lost packets out of
  8,634 (1.031%). This exceeded the configured 0.1% detection threshold for
  the 1% impairment test. The test verified cleanup back to `qdisc noqueue`.

**Evidence limitations:** The UDP-loss PCAP was captured on H1's sending
interface. Its sequence-gap warning is supporting evidence, but that capture
alone cannot establish where packets were lost or the end-to-end loss count.
The receiver-side iperf3 statistics provide the measured loss result.

For the controlled 20 ms ICMP delay, Wireshark displayed a response time of
0.910 ms for the first request/reply pair in the inspected capture. This did
not match the RTT measured by ping. A direct ping under the impairment measured
21.113 ms average RTT.

Seven focused pytest runs reported average RTTs of 63.503, 20.957, 50.534,
21.191, 21.193, 21.393, and 21.116 ms. Five readings were close to 21 ms,
while two were elevated. The elevated results were not consistently reproduced,
and their cause remains undetermined. Transient warm-up or ARP/neighbour-cache
resolution is a possible explanation, but it was not isolated or confirmed.

For this scenario, use ping statistics to validate RTT. The inspected H1-side
PCAP confirmed the captured ICMP exchanges, but its Wireshark response-time
value did not agree with ping and is not treated as a reliable latency result.
The temporary impairment was removed, and H1's interface was verified to
have returned to `qdisc noqueue`.

#### Known limitation

The capture helper currently uses `killall -INT tcpdump` within H1. This
works for the verified sequential test runs but is not isolated to a single
capture process. Parallel capture execution is not supported until
process-specific shutdown is implemented.

### Milestone 8 — Reporting & Quality Metrics

**Status:** Complete. JUnit XML, HTML, raw JSON, and quality-metrics reporting are implemented and verified for both baseline and expanded labs. Failure reporting, exit-code propagation, category metrics, and repository checks passed.

#### Reporting outputs

The reporting workflow generates four artifacts from one pytest execution:

- **JUnit XML** using pytest's built-in `--junitxml` option.
- **HTML** using `pytest-html` with `--self-contained-html`.
- **Raw JSON** using `pytest-json-report`, including test outcomes, phase timings,
  and failure diagnostics where available.
- **Quality metrics JSON** generated by `src/quality_metrics.py` from the raw
  pytest JSON report.

Reports are written under `artifacts/reports/`, which is excluded from Git.
Packet captures remain separately stored under `artifacts/pcap/`.

The reporting dependencies are pinned in `requirements.txt`:

- `pytest-html==4.2.0`
- `pytest-json-report==1.5.0`
- `pytest-metadata==3.1.1`

JUnit XML reporting uses pytest's built-in support.

#### Reusable reporting commands

Activate the project's virtual environment before running these commands.

For the expanded lab, with `srl-expanded` deployed:

```bash
python -m scripts.run_test_reports \
  --markers "expanded_lab or unit" \
  --name expanded-unit
```

For the baseline lab, with `srl-lab` deployed:

```bash
python -m scripts.run_test_reports \
  --markers "original_lab or unit" \
  --name original-unit
```

Run only the command that matches the currently deployed topology. Pytest markers
select tests; they do not deploy, stop, or switch labs.

The command runs the selected tests once and generates JUnit XML, HTML, raw JSON,
and the quality-metrics JSON summary. It preserves pytest's exit code, so a
failing test run remains a failure for shell automation and CI.

Reports are named using the supplied `--name` prefix and stored in
`artifacts/reports/`.

#### Quality metrics

The reusable `build_quality_metrics()` function in `src/quality_metrics.py`
summarizes:

- Collected, executed, deselected, passed, failed, errored, and skipped tests.
- Pass rate and overall pytest-reported duration.
- Summed setup, call, and teardown durations per test, including category totals
  and average phase duration per test.
- Failure details, including test ID, failing phase, and the available failure
  message.
- Results grouped by `unit`, `integration`, `expanded_lab`, and `original_lab`.

Category counts can overlap. For example, an expanded-lab test also marked as
integration is included in both category summaries; category totals must not be
added together to calculate the overall test count.

The summary utility can also process an existing JSON report independently:

```bash
python -m scripts.summarize_quality_metrics \
  --input artifacts/reports/expanded-unit.json \
  --output artifacts/reports/expanded-unit-quality.json
```

#### Verification

The initial all-in-one reporting run for the unit and expanded-lab tests passed:

```text
39 passed, 4 deselected in 96.16s
```

The generated JUnit XML contained 39 test cases, with zero failures and errors.
The raw JSON and quality summary both recorded 39 passing tests, 43 collected
tests, and 4 deselected tests.

Verified category counts for that run:

- Unit: 29 passed.
- Expanded lab: 10 passed.
- Integration: 10 passed, overlapping with the expanded-lab category.
- Original lab: 0 tests in this run because the original-lab group was excluded.

The failure path was also tested using a temporary assertion-failing test. All
four report formats were generated, the quality JSON retained the test ID,
failing phase, and assertion message, and the reporting command returned exit
code 1. The temporary test was removed afterward, and the unit suite passed
again with 29 passed and 14 deselected.

The dependency check completed with `No broken requirements found.`

The baseline-lab reporting workflow was also verified with `srl-lab` deployed:

- 33 passed, 10 deselected in 7.05s.
- JUnit XML contained 33 test cases, with zero failures or errors.
- Raw JSON recorded 33 passed, 43 collected, and 10 deselected.
- Quality metrics recorded 29 unit tests and 4 original-lab tests, all passed.
- All four report artifacts were generated, and generated reports are ignored
  by Git.

Milestone 8 verification is complete. Both topology-specific reporting workflows, intentional-failure handling, unit tests, dependency consistency, and generated-artifact exclusions were verified.

### Milestone 9 — CI/CD & End-to-End Validation

**Status:** In progress. The GitHub Actions unit-test workflow has been
committed, pushed, and successfully executed. Broader end-to-end validation
against the live Containerlab/SR Linux network remains outstanding.

#### GitHub Actions workflow

The workflow is defined in `.github/workflows/ci.yml`. It runs on pushes and
pull requests targeting `master` or `main`, and through manual workflow
dispatch.

The current hosted job:

- Runs on `ubuntu-latest` using Python 3.12.
- Installs the pinned project dependencies and checks them with `pip check`.
- Runs unit tests and generates reports using
  `python -m scripts.run_test_reports --markers unit --name ci-unit`.
- Uploads the reports as the `unit-test-reports` workflow artifact, with a
  14-day retention period. The upload step runs even if an earlier step fails.

#### Local verification

The local equivalent of the workflow completed successfully:

- Dependency check: `No broken requirements found.`
- Unit tests: 29 passed, 14 deselected in 0.40s.
- JUnit XML: 29 test cases, zero failures.
- HTML, raw JSON, and quality-metrics JSON reports were generated and checked.
- Generated reports remain under `artifacts/reports/`, which is excluded
  from Git.

#### GitHub Actions verification

The hosted workflow completed successfully:

- The `Unit tests and reports` job succeeded.
- The `unit-test-reports` artifact was uploaded.
- The run completed in approximately 36 seconds.

Run details: https://github.com/kapiliyer10/network-test-validation-platform/actions/runs/39537923669

This verifies the hosted unit-test and reporting workflow. The hosted run
should not be interpreted as evidence that the live network integration tests
were executed.

Workflow commit: `4f69544` — `Add GitHub Actions unit test workflow`.

#### Remaining work and limitations

The current hosted job does not deploy the Containerlab/SR Linux network or
run the lab-dependent integration suites. Those tests have been verified
locally against the baseline and expanded labs, but hosted end-to-end execution
has not been established.

Milestone 9 remains in progress until the remaining CI/end-to-end validation
scope is addressed.

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

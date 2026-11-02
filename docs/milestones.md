# Project 2 — Implementation Milestones

This document preserves the development history, implementation details, verification records, and completion status of all nine Project 2 milestones.

### Milestone 1 — Test Environment & Project 1 Integration

Status: Complete.

- Separate repository and virtual environment
- Pinned dependencies
- Docker-based router discovery
- Lab-readiness check
- Setup documentation

### Milestone 2 — pytest Framework & Initial Tests

Status: Complete.

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
- Router and endpoint tests configured to use the expanded lab

### Milestone 4 — Testbed Abstraction & Native pyATS Integration

Status: Complete.

- Native pyATS testbed defines R1, R2, and R3
- Custom Docker connection adapter reuses the existing CLI runner
- Native pyATS command execution verified on all three routers
- Native pyATS connectivity validation passed
- Structured interface-state validation passed using SR Linux JSON
- Native pyATS LLDP validation passed for all six expected Ethernet neighbor relationships
- Pytest regression suite passed after LLDP integration
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
- The normal latency test checks minimum, average, and maximum RTT, plus packet loss.
- The normal latency profile requires an average RTT of at most 10 ms and zero packet loss.
- Added a controlled-delay test that applies a temporary 20 ms delay to H1's `eth1` egress interface.
- The impairment test passes when average RTT reaches at least 15 ms and verifies that the interface returns to `qdisc noqueue` during cleanup.

Verified results:

| Scenario          | RTT result                               | Packet loss      | Result |
| ----------------- | ---------------------------------------- | ---------------- | ------ |
| No added delay    | Min 0.750 ms, avg 1.001 ms, max 1.266 ms | 0% (5/5 replies) | Passed |
| 20 ms added delay | Average 21.032 ms                        | 0%               | Passed |

The controlled-delay test changes the running lab temporarily. Use it only in
the expanded test lab, not on a production network or while unrelated traffic
uses the affected interface.

#### Integration and regression validation

At Milestone 6 completion, before packet-capture integration, the
expanded-lab test group contained ten tests:

- TCP and UDP application request/response validation.
- TCP performance profiles at 10, 25, and 50 Mbps.
- Three UDP scenarios in `test_iperf3_udp.py`: normal performance, packet-loss detection, and jitter detection.
- ICMP latency validation.
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

**Status:** Complete. Packet-capture implementation, expanded-lab regression tests, Wireshark analysis, and controlled-failure investigation are verified.

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

Unit-test result recorded at Milestone 7 completion:

```text
23 passed, 14 deselected in 0.21s
```

Expanded-lab result recorded at Milestone 7 completion:

```text
10 passed, 27 deselected in 96.81s
```

Combined regression result recorded at Milestone 7 completion using the then-recommended command
`pytest -q -m "expanded_lab or unit"`:

```text
33 passed, 4 deselected in 106.78s
```

The expanded-lab run verified TCP/UDP exchanges, throughput, packet-loss and
jitter detection, ICMP latency, PCAP generation, and restoration of `noqueue`
after controlled impairments. Python compilation and `git diff --check`
also passed.

#### Wireshark analysis and controlled-failure investigation

The following representative captures were opened and inspected in Wireshark.

- **TCP echo** (`H1_to_H2_tcp_echo.pcap`): the capture showed the TCP handshake,
  application data in both directions, and FIN/ACK closure. Follow TCP Stream
  displayed the request `NETWORK_VALIDATION` and response
  `TCP_OK:NETWORK_VALIDATION`.
- **UDP echo** (`H1_to_H2_udp_echo.pcap`): two UDP datagrams showed the request
  `NETWORK_VALIDATION` and response `UDP_OK:NETWORK_VALIDATION`. This confirms
  the captured exchange, not guaranteed delivery of other UDP datagrams.
- **Normal ICMP** (`H1_to_H2_icmp_latency.pcap`): five Echo Requests and
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

**Status:** Complete. JUnit XML, HTML, raw JSON, and quality-metrics reporting are implemented and verified for unit and expanded-lab test runs. Failure reporting, exit-code propagation, category metrics, and repository checks passed.

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
- Results grouped by `unit`, `integration`, and `expanded_lab`.

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
  The failure path was also tested using a temporary assertion-failing test. All
  four report formats were generated, the quality JSON retained the test ID,
  failing phase, and assertion message, and the reporting command returned exit
  code 1. The temporary test was removed afterward, and the unit suite passed
  again with 29 passed and 14 deselected.

The dependency check completed with `No broken requirements found.`

Milestone 8 verification is complete. The expanded-lab reporting workflow, intentional-failure handling, unit tests, dependency consistency, and generated-artifact exclusions were verified.

### Milestone 9 — CI/CD & End-to-End Validation

**Status:** Complete. Project 2 uses the expanded Containerlab topology
for network validation. The latest local pytest run passed all 43 tests, and
the updated unified CI workflow has passed on GitHub Actions.

#### Expanded lab topology

Project 2 uses `configs/lab-expanded.yaml` as its default testbed
configuration. The expanded topology contains three Nokia SR Linux routers
(R1, R2, R3) and two Linux endpoints (H1, H2).

The expanded topology is used for Project 2's router, connectivity, protocol,
endpoint-application, performance, latency, failure, and recovery validation
where applicable. Project 2's pytest and pyATS configurations target this lab.

#### GitHub Actions workflow

The workflow is defined in `.github/workflows/ci.yml` and runs on pushes and
pull requests targeting `master` or `main`, as well as through manual
workflow dispatch.

It contains two jobs:

- **Unit tests and reports:** installs the pinned dependencies, checks
  dependency consistency, runs unit tests, and generates the four report
  formats.
- **Expanded-lab integration and reports:** checks out Project 1, installs
  Containerlab, builds the endpoint image, deploys the expanded topology,
  waits for endpoint services, runs the expanded-lab tests, uploads reports,
  and destroys the lab even if an earlier step fails.

Reports are stored under `artifacts/reports/`, which is excluded from Git.
Packet captures are uploaded separately if the expanded-lab integration job
fails.

#### Local verification

The latest full pytest run was executed against the expanded lab:

- `pytest -v`: 43 passed in 103.07 seconds.
- Unit tests: 29 passed.
- Expanded-lab integration tests: 14 selected, including router discovery,
  three TCP probes, TCP/UDP application exchanges, throughput, latency, and
  controlled impairment tests.
- `pytest --collect-only -q -m expanded_lab`: 14 tests collected and
  29 deselected.

The separate pyATS AEtest scripts are not automatically executed by
`pytest -v`; they require their own AEtest invocation.

#### Hosted verification

The updated GitHub Actions workflow passed after router discovery and TCP
probes were migrated into the expanded-lab test group. The workflow runs the
unit-test/report job followed by the expanded-lab integration/report job.

Locally, the expanded-lab marker selects 14 integration tests. The earlier
successful hosted run executed 10 expanded-lab tests before this migration;
those results are retained here as historical context.

#### Jenkins pipeline (additional CI option)

The repository also includes a declarative Jenkins pipeline in `Jenkinsfile`.
It provides an alternative CI execution path alongside GitHub Actions.

The Jenkins agent must be Linux-based and have the `network-lab` label.
It requires:

- Python 3.12
- Docker Engine with access to the Docker daemon
- Containerlab
- Git
- Jenkins Pipeline and JUnit reporting support

The pipeline contains the following stages:

1. Validate agent prerequisites and inspect the existing expanded-lab state.
2. Run `scripts/setup_environment.sh` to prepare Project 1 and Project 2.
3. Run unit tests and generate JUnit XML, HTML, JSON, and quality-metrics reports.
4. Run expanded-lab integration tests and generate the same report formats.

JUnit XML results are published to Jenkins. HTML, JSON, and quality-metrics
files are archived as build artifacts. PCAP files are archived when a build
fails.

The pipeline disables concurrent builds to prevent simultaneous changes to
the shared network lab.

Lab cleanup depends on the state detected before the build:

- If the expanded lab was already running, Jenkins preserves it.
- If no expanded-lab containers existed, Jenkins removes containers created
  during the build.
- If a partial lab already existed, the pipeline stops before deployment so
  that the existing environment can be investigated.

**Execution status:** Jenkins was installed and configured on the local Ubuntu/WSL2 environment. Project 2's Jenkins job completed successfully as Build #7. The Jenkins dashboard reported no test failures and the build archived eight reporting artifacts. The job currently uses manual Build Now execution; GitHub webhook triggering has not been configured.


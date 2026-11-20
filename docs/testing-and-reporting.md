# Test Execution and Reporting

This guide explains how to prepare the expanded lab, run pytest and pyATS tests, execute traffic experiments, inspect packet captures, generate reports, and clean up the environment.

## 1. Environment requirements

- Linux environment.
- Python 3.12.
- Docker Engine running and accessible to your user.
- Containerlab.
- Git.

The expanded-lab tests use the companion Network Automation & Programmability Platform repository. By default, the setup script expects it at **$HOME/network-automation-platform**.

## 2. Prepare the environment

From the Network Test & Validation Platform repository root:

~~~bash
./scripts/setup_environment.sh
source .venv/bin/activate
python -m pip check
python -m scripts.check_lab_readiness
~~~

The setup script checks prerequisites, prepares the companion repository if the expected checkout does not exist, creates the project virtual environment, installs pinned Python dependencies, builds the Linux endpoint image, deploys the expanded lab when necessary, waits for endpoint services, and checks router readiness.

If the companion repository is in a different location, set **PROJECT1_DIR**:

~~~bash
PROJECT1_DIR="$HOME/projects/network-automation-platform" \
  ./scripts/setup_environment.sh
~~~

An existing companion-repository checkout is reused by the setup script. Review the script before running it in an environment where deploying or reusing the lab is not appropriate.

## 3. Run pytest

### Unit tests

Unit tests do not require the live expanded lab:

~~~bash
pytest -q -m unit
~~~

### Expanded-lab integration tests

The expanded topology must be deployed and its services ready:

~~~bash
pytest -q -m expanded_lab
~~~

Inspect the selected tests without running them:

~~~bash
pytest --collect-only -q -m expanded_lab
~~~

The recorded test selection contains 14 expanded-lab tests. The exact selection can change as tests are added or markers are updated.

### Complete pytest regression suite

~~~bash
pytest -v
~~~

The complete pytest run includes the unit tests and expanded-lab integration tests. The expanded lab must already be available. Pytest does not deploy, destroy, or switch the lab.

A recorded local regression run completed with 43 passed in 103.07 seconds. The separate pyATS AEtest scripts are not included in this count.

## 4. Router and protocol validation with pyATS AEtest

The native AEtest scripts are separate entry points. Run them from the repository root with the project virtual environment active:

~~~bash
python tests/aetest/connectivity.py
python tests/aetest/interfaces.py
python tests/aetest/ospf.py
python tests/aetest/routes.py
python tests/aetest/lldp.py
python tests/aetest/negative_connectivity.py
python tests/aetest/failure_recovery.py
~~~

These suites cover:
- Router connectivity and expected negative connectivity.
- Ethernet interface operational state.
- OSPF neighbor adjacencies and learned routes.
- LLDP neighbor and port relationships.
- Controlled link failure, alternate route selection, and recovery.

The YAML file **configs/lab-expanded.yaml** supplies router and test-case parameters. **configs/pyats-testbed.yaml** defines the native pyATS testbed.

The failure/recovery suite changes router state in the shared lab. Run it only when the lab is dedicated to this test, the relevant router candidate is clean, and no other person or process is changing the same router configuration. Inspect the router and lab after any interrupted run.

## 5. Application, performance, and latency tests

The expanded-lab tests exercise traffic between H1 and H2.

### TCP and UDP application exchanges

~~~bash
pytest -v -s tests/integration/test_tcp_application.py
pytest -v -s tests/integration/test_udp_application.py
~~~

The tests send an application payload from H1 to H2 and assert that the expected response is received.

### TCP performance

~~~bash
pytest -v -s tests/integration/test_iperf3_performance.py
~~~

The configuration defines 10, 25, and 50 Mbps TCP profiles. The test parses iperf3 JSON and checks receiver throughput and TCP retransmissions against configured thresholds.

### UDP performance, packet loss, and jitter

~~~bash
pytest -v -s tests/integration/test_iperf3_udp.py
~~~

The UDP test module covers normal throughput, controlled packet-loss detection, and controlled jitter detection. The tests use receiver-side iperf3 JSON metrics to evaluate throughput, loss, and jitter.

### ICMP latency and controlled delay

~~~bash
pytest -v -s tests/integration/test_latency.py
~~~

The normal latency test measures minimum, average, and maximum RTT and packet loss. A separate controlled-delay scenario adds 20 ms to traffic leaving H1 and checks that the measured RTT increases.

### Safety and cleanup for impairment tests

The controlled packet-loss, jitter, and delay scenarios temporarily modify H1's **eth1** traffic handling with Linux **tc netem**. They first inspect the existing qdisc and refuse to overwrite an unexpected state. Cleanup removes the temporary impairment and verifies restoration to **qdisc noqueue**.

Run impairment tests only in the isolated expanded lab. Do not run them on a production network or while unrelated traffic uses the affected interface. If cleanup fails or an unexpected qdisc state is reported, stop and investigate the endpoint before running further tests.

The configured thresholds are test-lab assertions, not production performance requirements.

## 6. Packet capture and Wireshark

The integration tests use **src/packet_capture.py** to start filtered tcpdump captures on the Linux endpoint. The helper stores a PID for each capture, stops the recorded process, copies the PCAP to the host, and checks that packets can be decoded.

Generated captures are written to:

~~~text
artifacts/pcap/
~~~

Open a generated PCAP in Wireshark to inspect the TCP handshake and application stream, UDP request/response datagrams, ICMP exchanges, or iperf3 traffic.

For the controlled UDP packet-loss scenario, the receiver-side iperf3 report is the source for the measured end-to-end loss percentage. A sender-side PCAP can provide supporting evidence such as sequence gaps, but it cannot by itself establish where packets were lost or the receiver's final loss count.

The current test workflow uses sequential pytest execution. Parallel capture execution has not been established as a supported test mode.

## 7. Generate test reports

Run a selected test group and generate all report formats:

~~~bash
python -m scripts.run_test_reports \
  --markers "expanded_lab or unit" \
  --name expanded-unit
~~~

The command runs pytest once and generates:

| File type | Contents |
|---|---|
| JUnit XML | Structured test cases and outcomes |
| HTML | Self-contained human-readable report |
| Raw JSON | pytest results and phase information |
| Quality-metrics JSON | Counts, pass rate, timings, category summaries, and failure details |

Output location:

~~~text
artifacts/reports/
~~~

To summarize an existing pytest JSON report independently:

~~~bash
python -m scripts.summarize_quality_metrics \
  --input artifacts/reports/expanded-unit.json \
  --output artifacts/reports/expanded-unit-quality.json
~~~

The **unit**, **integration**, and **expanded_lab** category summaries can overlap because an expanded-lab test can also carry the integration marker. Do not add category totals to calculate the overall test count.

The reporting command propagates pytest's exit code so a failed test run remains a failure for shell automation and CI.

## 8. CI execution

### GitHub Actions

Workflow: **.github/workflows/ci.yml**

It runs on pushes and pull requests targeting **master** or **main**, and on manual workflow dispatch. The workflow has:
1. A unit-test and report job.
2. An expanded-lab integration and report job.

The expanded-lab job checks out the companion repository, installs Containerlab, builds the endpoint image, deploys the topology, waits for endpoint readiness, runs the expanded-lab tests, uploads reports, uploads PCAP files on failure, and attempts to destroy the lab.

### Jenkins

Pipeline: **Jenkinsfile**

The Jenkins agent must be Linux-based and use the **network-lab** label. It requires Python 3.12, Docker, Containerlab, Git, and Jenkins Pipeline/JUnit reporting support.

The pipeline validates the agent and lab state, prepares the environment, runs unit tests, runs expanded-lab tests, publishes JUnit results, and archives reports. Concurrent Jenkins builds are disabled to protect the shared lab.

The documented local Jenkins verification was Build #7, manually started using **Build Now**. Automatic GitHub webhook triggering is not configured.

## 9. Stop the expanded lab

After testing, use the companion repository's cleanup script:

~~~bash
cd "$HOME/network-automation-platform"
./scripts/lab_expanded_down.sh
~~~

If the companion repository was checked out elsewhere, change to that directory instead. Do not stop a shared lab while another test run or user is using it.

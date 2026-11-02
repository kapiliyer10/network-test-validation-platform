# Test Execution and Reporting

This document contains the detailed pytest, expanded-lab, performance, packet-capture, and pyATS execution instructions.

Project 2 tests target the expanded Containerlab topology. Deploy the
expanded lab before running the full regression suite.

### Recommended regression command

Run the one-command environment setup from Section 6 before executing
the complete pytest suite from the Project 2 repository root:

    cd ~/network-test-validation-platform
    source .venv/bin/activate
    pytest -v

This runs the unit tests and expanded-lab integration tests together.
Pytest does not deploy or destroy the lab; the expanded topology must
already be running.

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

The recommended setup command builds the endpoint image and deploys the
expanded topology:

```bash
./scripts/setup_environment.sh
```

Run this command from the Project 2 repository root. If the environment
is already deployed and its services are ready, the script reuses it.

To manually rebuild the endpoint image:

```bash
docker build -t network-test-endpoint:1.0 \
  "$HOME/network-automation-platform/topology/tcp-endpoint"
```

To manually redeploy the topology:

```bash
"$HOME/network-automation-platform/scripts/lab_expanded_up.sh"
```

The expanded topology configures the H1 and H2 interfaces with an MTU of
1500 bytes. It also starts the iperf3 server on H2.

#### 2. Run the expanded-lab test group

Activate the Project 2 virtual environment and run:

```bash
cd ~/network-test-validation-platform
source .venv/bin/activate
pytest -q -m expanded_lab
```

This selects 14 expanded-lab tests covering router discovery, TCP probes,
TCP/UDP applications, iperf3 performance, latency, packet capture, and
controlled impairments.

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

Run the normal and controlled-delay ICMP latency tests:

```bash
pytest -v -s tests/integration/test_latency.py
```

The normal latency test uses BusyBox `ping` to measure minimum, average, and maximum
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

Pytest markers select tests; they do not deploy or destroy the expanded lab.

## Run pyATS AEtest Suites

Activate the Project 2 virtual environment before running these commands.

Run the connectivity tests:

    python tests/aetest/connectivity.py

Run interface validation:

    python tests/aetest/interfaces.py

Run OSPF neighbor validation:

    python tests/aetest/ospf.py

Run route validation:

    python tests/aetest/routes.py

The expanded-lab configuration defines 23 cases for the connectivity,
interface, OSPF-neighbor, and route AEtest suites:

- 3 connectivity checks across the configured router pairs
- 8 interface operational-state checks, including the R1 and R2 endpoint-facing interfaces
- 6 OSPF neighbor checks covering expected router IDs and FULL adjacency
- 6 OSPF-learned remote loopback route checks, including prefix, route
  type, next hop, outgoing interface, and best-route status

It also defines six LLDP neighbor checks, one negative-connectivity case,
and one failure/recovery scenario for their corresponding AEtest suites.

The tests execute commands through the existing Project 2 testbed and CLI
runner. The runner uses Docker to invoke the SR Linux CLI within each
router container.

These tests validate actual operational output from the running lab.
They do not establish native Unicon connection-plugin support or built-in
Genie parsing for Nokia SR Linux. The route and interface validation
currently uses parsing tailored to the observed SR Linux CLI output.


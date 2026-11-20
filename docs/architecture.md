# System Architecture

## 1. Purpose and boundaries

The Network Test & Validation Platform validates observable network behavior in a running Nokia SR Linux environment. It does not own the network topology or duplicate the companion Network Automation & Programmability Platform's configuration-management functions.

The platform has two validation paths:

1. **Router and protocol validation** — uses pytest and native pyATS AEtest to inspect router connectivity, interfaces, OSPF, LLDP, routes, and failure recovery.
2. **Endpoint traffic and performance validation** — uses Linux endpoints to exercise TCP/UDP applications and measure throughput, packet loss, jitter, and ICMP latency.

## 2. High-level architecture

~~~mermaid
flowchart TB
    CFG["YAML lab and test definitions"] --> RUN["pytest / pyATS AEtest"]
    RUN --> ROUTER["Router and protocol tests"]
    RUN --> ENDPOINT["Endpoint traffic and performance tests"]
    ROUTER --> LAB["Expanded Containerlab lab"]
    ENDPOINT --> LAB
    LAB --> ASSERT["Assertions and diagnostics"]
    ENDPOINT --> CAPTURE["tcpdump / PCAP evidence"]
    ASSERT --> REPORT["JUnit · HTML · JSON · quality metrics"]
    CAPTURE --> REPORT
~~~

The two test paths share the same network environment but interact with it differently. Router tests execute Nokia SR Linux CLI commands in router containers. Traffic tests execute Linux tools and application clients from H1/H2.

## 3. Network topology

The expanded lab contains three Nokia SR Linux routers and two Linux endpoints. The routers form a triangle. H1 is attached to R1 and H2 to R2.

~~~mermaid
flowchart TB
    H1["H1<br/>Linux endpoint"] --- R1["R1<br/>Nokia SR Linux"]
    R1 ---|"Direct link"| R2["R2<br/>Nokia SR Linux"]
    R1 --- R3["R3<br/>Nokia SR Linux"]
    R3 ---|"Alternate route"| R2
    R2 --- H2["H2<br/>Linux endpoint"]
~~~

| Segment or endpoint | Address |
|---|---|
| R1–R2 | 10.0.12.0/30 |
| R1–R3 | 10.0.31.0/30 |
| R2–R3 | 10.0.23.0/30 |
| H1 | 10.0.14.2/30 |
| H2 | 10.0.24.2/30 |

H1's traffic to H2 normally traverses R1–R2. The R1–R3–R2 path is used for OSPF failover validation when the direct R1–R2 link is disabled.

## 4. Router and protocol validation path

Router test cases are defined in YAML and the pyATS testbed file. pytest tests and native AEtest scripts use the project's testbed/device abstractions and shared Docker CLI runner.

~~~text
YAML test cases / pyATS testbed
              |
              v
      pytest or pyATS AEtest
              |
              v
     Testbed / RouterDevice
              |
              v
       Docker CLI runner
              |
              v
    Docker exec -> sr_cli
              |
              v
    Parse output and assert
              |
              v
    Test result and diagnostics
~~~

The shared runner executes commands inside the SR Linux router containers. The test code validates observed output against expected state.

Validation includes:
- Router connectivity and negative connectivity.
- Ethernet interface operational state.
- OSPF neighbor state and learned routes.
- LLDP neighbor and port relationships.
- Controlled link failure, OSPF alternate-path selection, and recovery.

The custom pyATS Docker connection adapter reuses the CLI runner. It does not establish a persistent SSH session.

## 5. Endpoint traffic and performance path

H1 and H2 are Linux traffic endpoints connected through the router topology. Traffic tools run in the endpoints rather than on the Nokia routers.

| Test type | Mechanism | Main assertions |
|---|---|---|
| TCP application | Python sockets | Expected request/response payload |
| UDP application | Python UDP sockets | Expected request/response payload |
| TCP performance | iperf3 JSON | Receiver throughput and retransmissions |
| UDP performance | iperf3 JSON | Receiver throughput, packet loss, and jitter |
| ICMP latency | ping statistics | RTT and packet-loss thresholds |
| Controlled impairment | Linux tc/netem | Injected loss, delay, or jitter is detected and cleaned up |

The impairment tests inspect the initial qdisc state before modifying it. Cleanup removes the test's temporary netem rule and verifies that the interface returns to its expected noqueue state. These tests are intended for the isolated lab only.

## 6. Packet capture and reporting

The reusable **src/packet_capture.py** helper:

1. Starts filtered tcpdump in the selected Linux endpoint.
2. Records the process ID for that individual capture.
3. Waits for capture readiness.
4. Stops that process using its recorded PID.
5. Copies the PCAP to **artifacts/pcap/**.
6. Decodes the capture and verifies that packets are present.

The helper preserves remote diagnostic files when shutdown or validation fails. The current test workflow uses normal sequential pytest execution; parallel capture execution is not claimed as verified.

The report utility **scripts/run_test_reports.py** generates four outputs from a single pytest run:

| Output | Purpose |
|---|---|
| JUnit XML | CI test-result integration |
| Self-contained HTML | Human-readable report |
| Raw JSON | Machine-readable pytest results |
| Quality-metrics JSON | Test counts, pass rate, timings, categories, and failure details |

Reports are saved under **artifacts/reports/**. PCAP files are saved separately under **artifacts/pcap/**. Generated artifacts are excluded from version control.

## 7. Project responsibilities

| Network Automation & Programmability Platform | Network Test & Validation Platform |
|---|---|
| Owns Containerlab topology definitions | Consumes the running lab |
| Deploys and removes the network | Prepares and checks the test environment |
| Owns router configuration and state-management implementation | Executes router and endpoint tests |
| Provides the expanded topology | Measures traffic and performance |
| — | Validates failure, recovery, and regression behavior |
| — | Captures packets and generates test reports |

This separation keeps network management and network validation as distinct projects.

## 8. Implementation scope and limitations

- pytest and pyATS AEtest are separate execution paths. The pytest full-suite result does not include AEtest scripts.
- Genie parsers and native Unicon connection plugins are not used for SR Linux. Structured router state is validated using native JSON output and Python parsing where applicable; other checks use parsing tailored to observed SR Linux CLI output.
- Performance measurements are specific to the configured containerized lab and are not production SLAs.
- Controlled impairment tests change traffic handling on H1 and must only run in the isolated expanded lab.
- Packet capture shutdown is process-specific. Although each capture uses its own PID and temporary files, the repository's current verification does not establish parallel test execution as supported.

## 9. Related documentation

- [Test Execution and Reporting](testing-and-reporting.md)
- [Implementation Milestones](milestones.md)
- [Detailed Development History](development-history.md)

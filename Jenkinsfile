pipeline {
    agent {
        label 'network-lab'
    }

    options {
        disableConcurrentBuilds()
        timestamps()
        timeout(time: 90, unit: 'MINUTES')
    }

    environment {
        PROJECT1_DIR = "${WORKSPACE}/network-automation-platform"
        LAB_STATE = 'UNKNOWN'
    }

    stages {
        stage('Validate Jenkins Agent') {
            steps {
                sh '''
                    #!/usr/bin/env bash
                    set -euo pipefail

                    for command in python3.12 docker containerlab git; do
                        command -v "$command" >/dev/null 2>&1 || {
                            echo "Missing prerequisite: $command"
                            exit 1
                        }
                    done

                    python3.12 --version
                    docker info
                    containerlab version
                    git --version
                '''

                script {
                    env.LAB_STATE = sh(
                        script: '''#!/usr/bin/env bash
                            set -euo pipefail

                            containers=(
                                clab-srl-expanded-R1
                                clab-srl-expanded-R2
                                clab-srl-expanded-R3
                                clab-srl-expanded-H1
                                clab-srl-expanded-H2
                            )

                            found=0
                            running=0

                            for container in "${containers[@]}"; do
                                if docker inspect "$container" >/dev/null 2>&1; then
                                    found=$((found + 1))

                                    state="$(docker inspect \
                                        --format '{{.State.Running}}' "$container")"

                                    if [[ "$state" == "true" ]]; then
                                        running=$((running + 1))
                                    fi
                                fi
                            done

                            if [[ "$found" -eq 0 ]]; then
                                echo ABSENT
                            elif [[ "$found" -eq 5 && "$running" -eq 5 ]]; then
                                echo READY
                            else
                                echo PARTIAL
                            fi
                        ''',
                        returnStdout: true
                    ).trim()

                    echo "Expanded lab state before build: ${env.LAB_STATE}"

                    if (env.LAB_STATE == 'PARTIAL') {
                        error(
                            'A partial expanded lab already exists. ' +
                            'Inspect the containers before running Jenkins.'
                        )
                    }
                }
            }
        }

        stage('Set Up Environment') {
            steps {
                sh '''
                    set -euo pipefail

                    PROJECT1_DIR="$PROJECT1_DIR" \
                        ./scripts/setup_environment.sh
                '''
            }
        }

        stage('Unit Tests and Reports') {
            steps {
                sh '''
                    set -euo pipefail

                    .venv/bin/python -m scripts.run_test_reports \
                        --markers unit \
                        --name jenkins-unit
                '''
            }
        }

        stage('Expanded-Lab Integration Tests and Reports') {
            steps {
                sh '''
                    set -euo pipefail

                    .venv/bin/python -m scripts.run_test_reports \
                        --markers expanded_lab \
                        --name jenkins-expanded-lab
                '''
            }
        }
    }

    post {
        always {
            // Publish test evidence before cleanup.
            junit(
                testResults: 'artifacts/reports/jenkins-*.xml',
                allowEmptyResults: true
            )

            archiveArtifacts(
                artifacts: 'artifacts/reports/**',
                allowEmptyArchive: true
            )

            script {
                if (env.LAB_STATE == 'ABSENT') {
                    echo 'Checking whether this build created expanded-lab containers.'

                    def containers = sh(
                        script: '''#!/usr/bin/env bash
                            docker ps -aq --filter name=clab-srl-expanded
                        ''',
                        returnStdout: true
                    ).trim()

                    if (containers) {
                        def cleanupStatus = sh(
                            script: '''#!/usr/bin/env bash
                                set -euo pipefail
                                "$PROJECT1_DIR/scripts/lab_expanded_down.sh"
                            ''',
                            returnStatus: true
                        )

                        if (cleanupStatus != 0) {
                            currentBuild.result = 'FAILURE'
                            echo 'WARNING: Expanded-lab cleanup failed.'
                        }
                    } else {
                        echo 'No expanded-lab containers remain. Cleanup skipped.'
                    }
                } else if (env.LAB_STATE == 'READY') {
                    echo 'The expanded lab existed before this build. Preserving it.'
                }
            }
        }

        failure {
            archiveArtifacts(
                artifacts: 'artifacts/pcap/*.pcap',
                allowEmptyArchive: true
            )
        }
    }
// CI pipeline: pull repo -> run the API smoke suite against the local Toolshop
// -> let the triage agent analyse the failures.
//
// Prereqs (one-time, in Jenkins):
//   * Plugins: Pipeline, Git, JUnit
//   * Credential (Secret text) with id 'openai-api-key' = your OpenAI key
//   * The local Toolshop (sprint5-with-bugs) running on http://localhost:8091
//   * python3 available on the Jenkins host (native brew Jenkins -> your host python)
//
// Jenkins is native on the host here, so localhost:8091 (Toolshop) and the
// OpenAI API are both reachable directly.

pipeline {
  agent any

  environment {
    API_BASE_URL   = 'http://localhost:8091'
    OPENAI_MODEL   = 'gpt-4o-mini'
    OPENAI_API_KEY = credentials('openai-api-key')   // Jenkins Secret text
    APP_DIR        = 'claude-test-agent'              // project subdir in the repo
  }

  options {
    timestamps()
    disableConcurrentBuilds()
  }

  stages {
    stage('Checkout') {
      steps { checkout scm }
    }

    stage('Setup') {
      // Create the venv once; reuse it on later builds (workspace persists).
      steps {
        dir(env.APP_DIR) {
          sh '''
            set -e
            [ -x .venv/bin/python ] || python3 -m venv .venv
            . .venv/bin/activate
            pip install -q --upgrade pip
            pip install -q -r requirements.txt
          '''
        }
      }
    }

    stage('Pre-flight: Toolshop reachable') {
      // Fail fast with a clear message if the system-under-test is down.
      steps {
        sh '''
          code=$(curl -s -o /dev/null -w "%{http_code}" -m 8 "$API_BASE_URL/status" || echo 000)
          echo "Toolshop $API_BASE_URL/status -> HTTP $code"
          [ "$code" = "200" ] || { echo "Toolshop not reachable — start sprint5-with-bugs"; exit 1; }
        '''
      }
    }

    stage('Build RAG index') {
      steps {
        dir(env.APP_DIR) {
          sh '. .venv/bin/activate && python -m rag.index'
        }
      }
    }

    stage('API smoke suite') {
      // Run the suite; never abort the pipeline on test failures — we WANT the
      // reds so the agent can triage them. JUnit marks the build UNSTABLE.
      steps {
        dir(env.APP_DIR) {
          sh '''
            . .venv/bin/activate
            pytest suite/test_smoke.py -p no:randomly \
              --junitxml=eval/failures/live.xml || true
          '''
        }
      }
      post {
        always { junit "${env.APP_DIR}/eval/failures/live.xml" }
      }
    }

    stage('Triage failures') {
      steps {
        dir(env.APP_DIR) {
          sh '''
            . .venv/bin/activate
            python cli.py eval/failures/live.xml --out triage-report.json
          '''
        }
      }
      post {
        always {
          archiveArtifacts artifacts: "${env.APP_DIR}/triage-report.json,${env.APP_DIR}/eval/failures/live.xml",
                           allowEmptyArchive: true
        }
      }
    }
  }

  post {
    always {
      echo 'Pipeline complete. Test trends in JUnit; triage-report.json in artifacts.'
    }
  }
}

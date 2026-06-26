#!/usr/bin/env bash
# Phase 0 preflight gate for CktClaw full-stack E2E tests.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="${ROOT}/tests/e2e_reports"
DATE_TAG="$(date +%Y%m%d)"
BASELINE="${REPORT_DIR}/${DATE_TAG}_baseline.md"
JSON_SUMMARY="${REPORT_DIR}/${DATE_TAG}_preflight.json"

mkdir -p "${REPORT_DIR}"

# shellcheck source=/dev/null
source "${ROOT}/activate.sh"

echo "==> cktclaw --doctor"
DOCTOR_OUT="$(mktemp)"
cktclaw --doctor 2>&1 | tee "${DOCTOR_OUT}" || true

echo "==> pytest preflight suite"
PYTEST_OUT="$(mktemp)"
python -m pytest \
  tests/test_task15_doctor.py \
  tests/test_full_chip_toolchain.py \
  tests/test_external_agent_bridges.py \
  tests/test_eda_agent_runner.py \
  tests/test_chip_system_e2e_smoke.py \
  -v --tb=short -q 2>&1 | tee "${PYTEST_OUT}"
PYTEST_RC=${PIPESTATUS[0]}

WHICH_CKTCLAW="$(which cktclaw 2>/dev/null || echo 'not found')"
CONDA_CKTCLAW="$(conda run -n cktclaw which cktclaw 2>/dev/null || echo 'not found')"
DEEPSEEK_SET="no"
if [[ -n "${DEEPSEEK_API_KEY:-}" ]]; then
  DEEPSEEK_SET="yes"
fi

python "${ROOT}/scripts/_e2e_preflight_report.py" \
  "${DOCTOR_OUT}" "${PYTEST_OUT}" "${DATE_TAG}" \
  "${WHICH_CKTCLAW}" "${CONDA_CKTCLAW}" "${DEEPSEEK_SET}" \
  "${REPORT_DIR}"

rm -f "${DOCTOR_OUT}" "${PYTEST_OUT}"

if [[ ${PYTEST_RC} -ne 0 ]]; then
  echo "pytest preflight FAILED (exit ${PYTEST_RC})" >&2
  exit ${PYTEST_RC}
fi

echo "Preflight OK → ${BASELINE}"

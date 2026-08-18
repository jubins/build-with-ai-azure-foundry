#!/usr/bin/env bash
# Deploy the five pre-launch alert rules to your Application Insights resource.
#
# Usage:
#   ./deploy_alerts.sh                     # uses .env values
#   ./deploy_alerts.sh --what-if           # preview without changing anything
set -e

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

: "${AZURE_SUBSCRIPTION_ID:?set AZURE_SUBSCRIPTION_ID in .env}"
: "${AZURE_RESOURCE_GROUP:?set AZURE_RESOURCE_GROUP in .env}"
: "${APPLICATION_INSIGHTS_NAME:?set APPLICATION_INSIGHTS_NAME in .env}"

# Optional: action group to notify. Without it the rules are created but
# nobody is paged — fine for a demo, not for production.
ACTION_GROUP_ID="${ACTION_GROUP_ID:-}"
DAILY_TOKEN_BUDGET="${DAILY_TOKEN_BUDGET:-1000000}"
LATENCY_THRESHOLD_SECONDS="${LATENCY_THRESHOLD_SECONDS:-10}"

MODE="deployment group create"
if [ "${1:-}" = "--what-if" ]; then
  MODE="deployment group what-if"
fi

echo "Deploying alert rules to ${APPLICATION_INSIGHTS_NAME} (rg: ${AZURE_RESOURCE_GROUP})"

if [ -z "$ACTION_GROUP_ID" ]; then
  echo "Note: ACTION_GROUP_ID is not set — rules will fire but notify nobody."
fi

# shellcheck disable=SC2086
az $MODE \
  --subscription "$AZURE_SUBSCRIPTION_ID" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --template-file infra/alerts.bicep \
  --parameters \
      appInsightsName="$APPLICATION_INSIGHTS_NAME" \
      actionGroupId="$ACTION_GROUP_ID" \
      dailyTokenBudget="$DAILY_TOKEN_BUDGET" \
      latencyThresholdSeconds="$LATENCY_THRESHOLD_SECONDS"

echo
echo "Done. Review them in: Azure portal → Monitor → Alerts → Alert rules"

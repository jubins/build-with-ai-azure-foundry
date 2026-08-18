// The five pre-launch alerts from Episode 10.
//
// All five are scheduledQueryRules (KQL) rather than metric alerts. Foundry
// agent telemetry lands in Application Insights as dependencies and
// customMetrics, and the thresholds we care about — error *rate*, block *rate*,
// P95 latency, tokens summed over a day — are ratios and aggregations that
// platform metric alerts can't express against agent semantics.
//
// The queries are a starting point, not gospel: span names and attributes vary
// with your instrumentation. Run each query in Logs against your own data and
// adjust the filters before trusting the alert. See the README.

@description('Name of the existing Application Insights resource to alert on')
param appInsightsName string

@description('Location for the alert rules')
param location string = resourceGroup().location

param tags object = {}

@description('Action group to notify. Leave empty to create rules with no action attached.')
param actionGroupId string = ''

@description('Daily token spend threshold — total tokens/day before alerting')
param dailyTokenBudget int = 1000000

@description('P95 latency threshold in seconds')
param latencyThresholdSeconds int = 10

resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: appInsightsName
}

var actions = empty(actionGroupId) ? [] : [
  {
    actionGroupId: actionGroupId
  }
]

// ── 1. Error rate — alert if more than 1% of agent runs fail ────────────────
resource errorRateAlert 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: 'agent-error-rate'
  location: location
  tags: tags
  properties: {
    displayName: 'Agent error rate > 1%'
    description: 'More than 1% of agent runs failed. Catches agent errors, tool failures, and content safety blocks before users report them.'
    severity: 1
    enabled: true
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    scopes: [appInsights.id]
    criteria: {
      allOf: [
        {
          query: '''
dependencies
| where timestamp > ago(15m)
| where type has "gen_ai" or name has "agent"
| summarize Total = count(), Failed = countif(success == false)
| extend ErrorRate = todouble(Failed) / todouble(Total) * 100
| project ErrorRate
'''
          timeAggregation: 'Maximum'
          metricMeasureColumn: 'ErrorRate'
          operator: 'GreaterThan'
          threshold: 1
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: empty(actionGroupId) ? [] : [actionGroupId]
    }
  }
}

// ── 2. P95 latency — alert if the 95th percentile exceeds the threshold ─────
resource latencyAlert 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: 'agent-p95-latency'
  location: location
  tags: tags
  properties: {
    displayName: 'Agent P95 latency > ${latencyThresholdSeconds}s'
    description: 'P95 response latency exceeded threshold. Catches context accumulation issues early.'
    severity: 2
    enabled: true
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    scopes: [appInsights.id]
    criteria: {
      allOf: [
        {
          query: '''
dependencies
| where timestamp > ago(15m)
| where type has "gen_ai" or name has "agent"
| summarize P95 = percentile(duration, 95) / 1000.0
| project P95
'''
          timeAggregation: 'Maximum'
          metricMeasureColumn: 'P95'
          operator: 'GreaterThan'
          threshold: latencyThresholdSeconds
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: empty(actionGroupId) ? [] : [actionGroupId]
    }
  }
}

// ── 3. Daily token spend — alert when the day's tokens exceed budget ────────
resource tokenSpendAlert 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: 'agent-daily-token-spend'
  location: location
  tags: tags
  properties: {
    displayName: 'Daily token spend over budget'
    description: 'Total tokens used today exceeded the configured budget. Catches cost spikes from runaway loops or unexpected traffic.'
    severity: 2
    enabled: true
    evaluationFrequency: 'PT1H'
    windowSize: 'PT24H'
    scopes: [appInsights.id]
    criteria: {
      allOf: [
        {
          query: '''
customMetrics
| where timestamp > ago(24h)
| where name in ("gen_ai.client.token.usage", "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens")
| summarize TotalTokens = sum(valueSum)
| project TotalTokens
'''
          timeAggregation: 'Maximum'
          metricMeasureColumn: 'TotalTokens'
          operator: 'GreaterThan'
          threshold: dailyTokenBudget
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: empty(actionGroupId) ? [] : [actionGroupId]
    }
  }
}

// ── 4. Content safety blocks — alert if block rate exceeds 0.5% ─────────────
resource contentSafetyAlert 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: 'agent-content-safety-blocks'
  location: location
  tags: tags
  properties: {
    displayName: 'Content safety block rate > 0.5%'
    description: 'A high block rate signals either a prompt injection attempt or a misconfigured safety threshold.'
    severity: 2
    enabled: true
    evaluationFrequency: 'PT15M'
    windowSize: 'PT1H'
    scopes: [appInsights.id]
    criteria: {
      allOf: [
        {
          query: '''
dependencies
| where timestamp > ago(1h)
| where type has "gen_ai" or name has "agent"
| summarize Total = count(),
            Blocked = countif(resultCode has_any ("content_filter", "ResponsibleAIPolicyViolation"))
| extend BlockRate = todouble(Blocked) / todouble(Total) * 100
| project BlockRate
'''
          timeAggregation: 'Maximum'
          metricMeasureColumn: 'BlockRate'
          operator: 'GreaterThan'
          threshold: json('0.5')
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: empty(actionGroupId) ? [] : [actionGroupId]
    }
  }
}

// ── 5. Tool call failure rate — alert if more than 2% of tool calls fail ────
resource toolFailureAlert 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: 'agent-tool-failure-rate'
  location: location
  tags: tags
  properties: {
    displayName: 'Tool call failure rate > 2%'
    description: 'Catches tool availability issues — web search timeout, file search returning empty, external API down.'
    severity: 2
    enabled: true
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    scopes: [appInsights.id]
    criteria: {
      allOf: [
        {
          query: '''
dependencies
| where timestamp > ago(15m)
| where name has "execute_tool" or type has "tool"
| summarize Total = count(), Failed = countif(success == false)
| extend FailureRate = todouble(Failed) / todouble(Total) * 100
| project FailureRate
'''
          timeAggregation: 'Maximum'
          metricMeasureColumn: 'FailureRate'
          operator: 'GreaterThan'
          threshold: 2
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: empty(actionGroupId) ? [] : [actionGroupId]
    }
  }
}

output alertNames array = [
  errorRateAlert.name
  latencyAlert.name
  tokenSpendAlert.name
  contentSafetyAlert.name
  toolFailureAlert.name
]

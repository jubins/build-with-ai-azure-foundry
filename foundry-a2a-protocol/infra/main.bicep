targetScope = 'subscription'

@minLength(1)
@maxLength(64)
param environmentName string

@minLength(1)
param location string

@description('Your Foundry project endpoint URL')
param foundryEndpoint string

@description('Agent name and version in name:version format — the Prompt Agent backing the specialist')
param agentId string = 'helpful-ai-agent:1'

var resourceGroupName = 'rg-${environmentName}'
var tags = { 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2022-09-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

module containerApps 'container-apps.bicep' = {
  name: 'container-apps'
  scope: rg
  params: {
    environmentName: environmentName
    location: location
    tags: tags
    foundryEndpoint: foundryEndpoint
    agentId: agentId
  }
}

output SERVICE_SPECIALIST_URI string = containerApps.outputs.specialistUri

// Feed this into SPECIALIST_A2A_URL when you register the coordinator's A2A tool
output SPECIALIST_A2A_URL string = containerApps.outputs.specialistUri
output SPECIALIST_AGENT_CARD_URL string = containerApps.outputs.agentCardUri

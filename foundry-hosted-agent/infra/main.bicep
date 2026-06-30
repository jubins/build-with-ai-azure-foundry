targetScope = 'subscription'

@minLength(1)
@maxLength(64)
param environmentName string

@minLength(1)
param location string

@description('Your Foundry project endpoint URL')
param foundryEndpoint string

@description('Agent name and version in name:version format')
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

output SERVICE_API_URI string = containerApps.outputs.apiUri

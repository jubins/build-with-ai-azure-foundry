param environmentName string
param location string
param tags object
param foundryEndpoint string
param agentId string

// Container Apps Environment (the shared hosting plane)
resource caEnvironment 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: 'cae-${environmentName}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'azure-monitor'
    }
  }
}

// Managed identity so the container can call Foundry without storing credentials
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${environmentName}'
  location: location
  tags: tags
}

// The Container App itself
resource containerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: 'ca-${environmentName}'
  location: location
  tags: union(tags, { 'azd-service-name': 'api' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: caEnvironment.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
      }
    }
    template: {
      containers: [
        {
          name: 'foundry-agent-api'
          // azd replaces this image reference after building the Dockerfile
          image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            {
              name: 'AZURE_EXISTING_AIPROJECT_ENDPOINT'
              value: foundryEndpoint
            }
            {
              name: 'AZURE_EXISTING_AGENT_ID'
              value: agentId
            }
            {
              name: 'AZURE_CLIENT_ID'
              value: identity.properties.clientId
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0   // scales to zero when idle — no cost
        maxReplicas: 3
      }
    }
  }
}

output apiUri string = 'https://${containerApp.properties.configuration.ingress.fqdn}'

# Python 3.13+ (newer requirement than the 3.10 in earlier episodes)
python3 --version

# Azure Developer CLI
curl -fsSL https://aka.ms/install-azd.sh | bash    # macOS/Linux
# winget install microsoft.azd                       # Windows

# Verify and add the Foundry extension
azd version
azd extension install microsoft.foundry
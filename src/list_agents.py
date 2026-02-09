# list_agents.py
# Run this in your project to see all agents that actually exist in your Azure AI Foundry project
# Requirements: same as your project (azure-ai-projects, azure-identity, python-dotenv)

import asyncio
import os
from dotenv import load_dotenv
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential

# Load environment variables from .env (same as your app)
load_dotenv()

async def list_all_agents():
    # Get your project endpoint from .env (should be the same as AZURE_EXISTING_AIPROJECT_ENDPOINT)
    project_endpoint = os.getenv("AZURE_EXISTING_AIPROJECT_ENDPOINT")
    
    if not project_endpoint:
        print("Error: AZURE_EXISTING_AIPROJECT_ENDPOINT not found in .env")
        return

    print(f"Using project endpoint: {project_endpoint}")
    print("Listing all agents in the project...\n")

    credential = DefaultAzureCredential()

    async with AIProjectClient(endpoint=project_endpoint, credential=credential) as client:
        try:
            # List all agents (this uses the agents.list() method)
            agents = client.agents.list()
            
            count = 0
            async for agent in agents:
                count += 1
                name = agent.name or "(no name)"
                agent_id = agent.id or "(no id)"
                print(f"Agent #{count}:")
                print(f"  Name: {name}")
                print(f"  ID:   {agent_id}")
                print(f"  Full object ID (if versioned): {agent.id}")
                print("-" * 60)
            
            if count == 0:
                print("No agents found in this project.")
            else:
                print(f"\nFound {count} agent(s) total.")

        except Exception as e:
            print("Error while listing agents:")
            print(f"  {type(e).__name__}: {str(e)}")
            print("\nPossible fixes:")
            print("  - Make sure you're logged in: az login")
            print("  - Check if the endpoint is correct")
            print("  - Verify you have access to this project")
            print("  - Make sure the azure-ai-projects package is up to date")

if __name__ == "__main__":
    asyncio.run(list_all_agents())
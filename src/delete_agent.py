import asyncio
import os
from dotenv import load_dotenv
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential
from logging_config import configure_logging
from util import get_env_file_path

# Load environment variables
env_file = get_env_file_path()
load_dotenv(env_file)
logger = configure_logging("delete_agent.log")

async def delete_agent():
    """Delete the InsightBot-SLIIT-v5 agent"""
    proj_endpoint = os.environ.get("AZURE_EXISTING_AIPROJECT_ENDPOINT")
    agent_name = os.environ["AZURE_AI_AGENT_NAME"]  # InsightBot-SLIIT-v5
    
    if not proj_endpoint:
        print("❌ Missing AZURE_EXISTING_AIPROJECT_ENDPOINT")
        return
    
    async with DefaultAzureCredential() as credential, AIProjectClient(endpoint=proj_endpoint, credential=credential) as project_client:
        try:
            logger.info(f"🔄 Deleting agent: {agent_name}")
            await project_client.agents.delete(agent_name=agent_name)
            print(f"✅ SUCCESS: Deleted agent '{agent_name}'")
            logger.info(f"Deleted agent: {agent_name}")
            
            # Clear env var
            if "AZURE_EXISTING_AGENT_ID" in os.environ:
                del os.environ["AZURE_EXISTING_AGENT_ID"]
                print("✅ Cleared AZURE_EXISTING_AGENT_ID")
            
        except Exception as e:
            print(f"ℹ️  No agent found or already deleted: {e}")
            logger.info(f"Agent not found or delete failed: {e}")

if __name__ == "__main__":
    print("🗑️  Azure AI Agent Deleter")
    print(f"Agent Name: {os.environ.get('AZURE_AI_AGENT_NAME', 'InsightBot-SLIIT-v5')}")
    print("---")
    asyncio.run(delete_agent())
    print("✅ Done! Run 'python gunicorn.conf.py' to recreate.")

import asyncio
import os
from dotenv import load_dotenv
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.models import ConnectionType

# Load .env
load_dotenv()

async def check_connections():
    """Check existing AI Search connections and print IDs"""
    
    proj_endpoint = os.getenv("AZURE_EXISTING_AIPROJECT_ENDPOINT")
    if not proj_endpoint:
        print("❌ Missing AZURE_EXISTING_AIPROJECT_ENDPOINT in .env")
        return
    
    print(f"🔍 Checking connections in project: {proj_endpoint}")
    
    async with DefaultAzureCredential() as credential:
        async with AIProjectClient(endpoint=proj_endpoint, credential=credential) as project_client:
            print("\n📋 ALL CONNECTIONS:")
            conn_count = 0
            
            # List ALL connections
            async for conn in project_client.connections.list():
                conn_count += 1
                print(f"  {conn_count}. ID: {conn.id}")
                print(f"     Type: {conn.connection_type}")
                print(f"     Name: {getattr(conn, 'name', 'N/A')}")
                print(f"     Target: {getattr(conn, 'target', 'N/A')[:50]}...")
                print()
            
            print(f"\n🔍 AI SEARCH CONNECTIONS ONLY:")
            search_count = 0
            
            # Filter for AI Search only
            async for conn in project_client.connections.list():
                if conn.connection_type == ConnectionType.AZURE_AI_SEARCH:
                    search_count += 1
                    print(f"  ✅ FOUND AI SEARCH #{search_count}:")
                    print(f"     CONNECTION_ID: {conn.id}")
                    print(f"     Target: {getattr(conn, 'target', 'N/A')}")
                    print()
            
            if search_count == 0:
                print("❌ NO AI SEARCH connections found!")
                print("\n💡 CREATE ONE:")
                print("1. Azure Portal → AI Foundry → Your Project → Connections")
                print("2. New → Azure AI Search")
                print("3. Endpoint:", os.getenv("AZURE_AI_SEARCH_ENDPOINT"))
                print("4. Admin Key:", os.getenv("AZURE_AI_SEARCH_KEY"))
                print("5. Copy CONNECTION_ID (conn_xxxx)")
            
            print(f"\n✅ Your .env vars:")
            print(f"   AZURE_AI_SEARCH_ENDPOINT: {os.getenv('AZURE_AI_SEARCH_ENDPOINT')[:30]}...")
            print(f"   AZURE_AI_SEARCH_INDEX_NAME: {os.getenv('AZURE_AI_SEARCH_INDEX_NAME')}")

if __name__ == "__main__":
    asyncio.run(check_connections())

# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license.
# See LICENSE file in the project root for full license information.
from typing import Dict, List, Optional

import asyncio
import multiprocessing
import os

from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import (
    ConnectionType,
    AgentVersionDetails,          # was AgentVersionObject
    PromptAgentDefinition,
    FileSearchTool,
    AzureAISearchTool,            # was AzureAISearchAgentTool
    AzureAISearchToolResource,
    AISearchIndexResource,
    Tool,
    CodeInterpreterTool,
    AutoCodeInterpreterToolParam, # was CodeInterpreterContainerAuto
    EvaluationRule,
    ContinuousEvaluationRuleAction,
    EvaluationRuleFilter,
    EvaluationRuleEventType,
    EvaluationRuleActionType
)
from azure.identity.aio import DefaultAzureCredential
from azure.core.credentials_async import AsyncTokenCredential
from azure.storage.blob.aio import BlobServiceClient

from openai import AsyncOpenAI
from dotenv import load_dotenv
from logging_config import configure_logging
from util import get_env_file_path

env_file = get_env_file_path()
load_dotenv(env_file)

logger = configure_logging(os.getenv("APP_LOG_FILE", ""))
if env_file:
    logger.info(f"Loaded environment variables from {env_file}")
else:
    logger.info("Loaded environment variables from default location")


def list_files_in_files_directory() -> List[str]:
    files_directory = os.path.abspath(os.path.join(os.path.dirname(__file__), 'files'))
    files = [f for f in os.listdir(files_directory) if os.path.isfile(os.path.join(files_directory, f))]
    return files

FILES_NAMES = list_files_in_files_directory()


async def execute_step(
    step_name: str,
    step_func,
    resources: Dict,
    steps_order: List[str]
) -> None:
    from api.search_index_manager import ResourceStatus
    step_index = steps_order.index(step_name)
    if step_index > 0:
        prior_step = steps_order[step_index - 1]
        prior_status = resources.get(prior_step)
        if prior_status == ResourceStatus.FAILED:
            logger.error(f"Skipping step '{step_name}' because prior step '{prior_step}' failed.")
            resources[step_name] = ResourceStatus.FAILED
            return
    try:
        status = await step_func()
        resources[step_name] = status
    except Exception as e:
        logger.error(f"Step '{step_name}' raised exception: {e}")
        resources[step_name] = ResourceStatus.FAILED


def _print_summary(resources: Dict, steps_order: List[str]) -> None:
    logger.info("=" * 80)
    logger.info("Azure AI Search Setup Summary")
    logger.info("=" * 80)
    for i, step_name in enumerate(steps_order, 1):
        status = resources.get(step_name)
        if status:
            status_symbol = "✓" if status.value == "created" else "i" if status.value == "existing" else "x"
            logger.info(f"{i}. {step_name}: {status_symbol} {status.value}")
        else:
            logger.info(f"{i}. {step_name}: x failed")
    logger.info("=" * 80)


def _get_file_path(file_name: str) -> str:
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), 'files', file_name))


async def get_available_tool(
        project_client: AIProjectClient,
        openai_client: AsyncOpenAI,
        creds: AsyncTokenCredential) -> Optional[Tool]:
    use_ai_search = os.environ.get('USE_AZURE_AI_SEARCH_SERVICE', 'false').lower() == 'true'
    conn_id = os.environ.get('SEARCH_CONNECTION_ID')
    search_index_name = os.environ.get('AZURE_AI_SEARCH_INDEX_NAME')

    if use_ai_search:
        logger.info("Using EXISTING AI Search tool...")
        ai_search_tool = AzureAISearchTool(         # ✅ was AzureAISearchAgentTool
            azure_ai_search=AzureAISearchToolResource(
                indexes=[AISearchIndexResource(
                    project_connection_id=conn_id,
                    index_name=search_index_name,
                    query_type="semantic"
                )]
            )
        )
        logger.info(f"AI Search tool configured: {search_index_name}")
        return ai_search_tool
    else:
        logger.warning("AI Search not enabled. Creating agent without search tool.")
        return None


async def create_agent(ai_project: AIProjectClient,
                       openai_client: AsyncOpenAI,
                       creds: AsyncTokenCredential) -> AgentVersionDetails:
    logger.info("Creating agent with code interpreter + search")

    file_ids = []
    code_file_path = os.path.join(os.path.dirname(__file__), "Code_inter.py")

    if os.path.exists(code_file_path):
        try:
            with open(code_file_path, "rb") as file_data:
                uploaded_file = await openai_client.files.create(
                    file=file_data,
                    purpose="assistants"
                )
            logger.info(f"Uploaded Code_inter.py, file ID: {uploaded_file.id}")

            timeout_start = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - timeout_start < 200:
                file_status = await openai_client.files.retrieve(uploaded_file.id)
                logger.info(f"File status: {file_status.status}")  # ← add this
                if file_status.status in ('completed', 'processed'):
                    logger.info("File processing completed")
                    file_ids = [uploaded_file.id]
                    break
                await asyncio.sleep(1)
            else:
                logger.warning("File processing timeout - creating without reference file")

        except Exception as e:
            logger.warning(f"File upload failed: {e}, using code interpreter without file")
    else:
        logger.warning("Code_inter.py not found")

    # ✅ Correct initialization using AutoCodeInterpreterToolParam
    code_interpreter = CodeInterpreterTool(
        container=AutoCodeInterpreterToolParam(file_ids=[])
    )

    tool = await get_available_tool(ai_project, openai_client, creds)

    tools: List[Tool] = [code_interpreter]
    if tool:
        tools.append(tool)
        instructions = """You are InsightBot, SLIIT's academic document assistant. Answer queries using the AI Search index as your sole source of truth.
                BEHAVIOR:
                1. Always search before responding. Never hallucinate facts.
                2. If multiple documents are relevant, synthesize — note conflicts explicitly.
                3. For meeting minutes: follow Meeting->Topic->Discussion->Sources->Notes structure.
                4. If query is ambiguous: ask one clarifying question only.
                5. If nothing found: "No relevant information found in the indexed documents."
                RESPONSE FORMAT (adapt to query type):
                - Factual/stats -> bullet points with source citation
                - Meeting queries -> structured: Meeting | Topic | Discussion | Sources | Notes
                - Comparisons -> table
                - Unknown -> clarifying question
                USE CODE INTERPRETER ONLY when the user explicitly requests:
                - Calculations, data analysis, chart/graph generation, or file processing.
                - Never invoke it for document lookups or factual retrieval — use AI Search instead.
                CODE INTERPRETER FILE NOTE:
                - The attached file (Code_inter.py) is a CODE TEMPLATE only — it is NOT a data source.
                - NEVER read or analyze Code_inter.py for data or statistics.
                - NEVER treat Code_inter.py as a knowledge source.
                - It exists ONLY to show you the correct coding pattern to follow when generating charts.
                IMPORTANT — When generating charts or visualizations:
                - Always add: import matplotlib; matplotlib.use("Agg") before importing pyplot
                - Always save using: plt.savefig("chart.png", bbox_inches="tight")
                - Always call: plt.close() after saving
                - NEVER use plt.show() — it will silently fail in this environment
                - The saved file will automatically be provided to the user as a downloadable image
                TONE: Professional, precise, neutral."""
    else:
        instructions = """You are InsightBot, SLIIT's academic document assistant.
                BEHAVIOR:
                1. Answer only from your available context. Never hallucinate facts.
                2. If nothing found: "No relevant information found in the indexed documents."
                3. If query is ambiguous: ask one clarifying question only.
                USE CODE INTERPRETER when the user explicitly requests calculations, data analysis, or chart generation.
                IMPORTANT — When generating charts or visualizations:
                - Always add: import matplotlib; matplotlib.use("Agg") before importing pyplot
                - Always save using: plt.savefig("chart.png", bbox_inches="tight")
                - Always call: plt.close() after saving
                - NEVER use plt.show() — it will silently fail in this environment
                - The saved file will automatically be provided to the user as a downloadable image
                TONE: Professional, precise, neutral."""

    agent = await ai_project.agents.create_version(
        agent_name=os.environ["AZURE_AI_AGENT_NAME"],
        definition=PromptAgentDefinition(
            model=os.environ["AZURE_AI_AGENT_DEPLOYMENT_NAME"],
            instructions=instructions,
            tools=tools,
        ),
    )
    logger.info(f"Agent created: {agent.id}")
    return agent


async def initialize_eval(
        project_client: AIProjectClient,
        openai_client: AsyncOpenAI,
        agent_obj: AgentVersionDetails,
        credential: AsyncTokenCredential):
    eval_rule_id = f"eval-rule-for-{agent_obj.name}"
    try:
        eval_rules = project_client.evaluation_rules.list(
            action_type=EvaluationRuleActionType.CONTINUOUS_EVALUATION,
            agent_name=agent_obj.name)
        rules_list = [rule async for rule in eval_rules]

        if len(rules_list) >= 1:
            logger.info(f"Continuous Evaluation Rule for agent {agent_obj.name} already exists")
        else:
            data_source_config = {"type": "azure_ai_source", "scenario": "responses"}
            testing_criteria = [
                {
                    "type": "azure_ai_evaluator",
                    "name": "violence",
                    "evaluator_name": "builtin.violence",
                    "initialization_parameters": {"deployment_name": os.environ["AZURE_AI_AGENT_DEPLOYMENT_NAME"]},
                }
            ]
            eval_object = await openai_client.evals.create(
                name=f"{agent_obj.name} Continuous Evaluation",
                data_source_config=data_source_config,   # type: ignore
                testing_criteria=testing_criteria,        # type: ignore
            )
            logger.info(f"Evaluation created (id: {eval_object.id}, name: {eval_object.name})")

            continuous_eval_rule = await project_client.evaluation_rules.create_or_update(
                id=eval_rule_id,
                evaluation_rule=EvaluationRule(
                    display_name=f"{agent_obj.name} Continuous Eval Rule",
                    description="An eval rule that runs on agent response completions",
                    action=ContinuousEvaluationRuleAction(
                        eval_id=eval_object.id,
                        max_hourly_runs=5),
                    event_type=EvaluationRuleEventType.RESPONSE_COMPLETED,
                    filter=EvaluationRuleFilter(agent_name=agent_obj.name),
                    enabled=True,
                ),
            )
            logger.info(
                f"Continuous Evaluation Rule created (id: {continuous_eval_rule.id}, "
                f"name: {continuous_eval_rule.display_name})"
            )
    except Exception as e:
        logger.error(f"Error creating Continuous Evaluation Rule: {e}", exc_info=True)


async def initialize_resources():
    proj_endpoint = os.environ.get("AZURE_EXISTING_AIPROJECT_ENDPOINT")
    try:
        async with (
            DefaultAzureCredential() as credential,
            AIProjectClient(endpoint=proj_endpoint, credential=credential) as project_client,
            project_client.get_openai_client() as openai_client,
        ):
            agent_obj: Optional[AgentVersionDetails] = None   # ✅ was AgentVersionObject

            agentID = os.environ.get("AZURE_EXISTING_AGENT_ID")

            if agentID:
                try:
                    logger.info(f"Looking up existing agent by ID/name: '{agentID}'")
                    agents_result = await project_client.agents.get(agentID)
                    agent_obj = agents_result.versions.latest
                    logger.info(f"Found existing agent '{agentID}' (version obj id: {agent_obj.id})")
                except Exception as e:
                    logger.warning(
                        f"Could not retrieve agent by AZURE_EXISTING_AGENT_ID='{agentID}': {e}. "
                        "Will try by AZURE_AI_AGENT_NAME or create a new agent."
                    )
            else:
                logger.info("AZURE_EXISTING_AGENT_ID not set.")

            if not agent_obj:
                try:
                    agent_name = os.environ["AZURE_AI_AGENT_NAME"]
                    logger.info(f"Retrieving agent by name: {agent_name}")
                    agents = await project_client.agents.get(agent_name)
                    agent_obj = agents.versions.latest
                    logger.info(f"Agent with agent id, {agent_obj.id} retrieved.")
                except Exception as e:
                    logger.info(f"Agent name, {agent_name} not found.")

            if not agent_obj:
                agent_obj = await create_agent(project_client, openai_client, credential)
                logger.info(f"Created agent, agent ID: {agent_obj.id}")

            os.environ["AZURE_EXISTING_AGENT_ID"] = agent_obj.id
            logger.info(f"AZURE_EXISTING_AGENT_ID set to: {agent_obj.id}")

            await initialize_eval(project_client, openai_client, agent_obj, credential)
    except Exception as e:
        logger.info(f"Error creating agent: {e}", exc_info=True)
        raise RuntimeError(f"Failed to create the agent: {e}")


def on_starting(server):
    asyncio.get_event_loop().run_until_complete(initialize_resources())


max_requests = 1000
max_requests_jitter = 50
log_file = "-"
bind = "0.0.0.0:50505"

if not os.getenv("RUNNING_IN_PRODUCTION"):
    reload = True

preload_app = True
import multiprocessing
num_cpus = multiprocessing.cpu_count()
workers = (num_cpus * 2) + 1
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 120

if __name__ == "__main__":
    logger.info("Running initialize_resources directly...")
    asyncio.run(initialize_resources())
    logger.info("initialize_resources finished.")
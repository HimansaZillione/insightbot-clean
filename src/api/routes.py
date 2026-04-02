# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE.md file in the project root for full license information.

import asyncio
import json
import os
import base64
from datetime import datetime, timezone, timedelta
from typing import AsyncGenerator, Mapping, Optional, Dict

import fastapi
from fastapi import Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import logging
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from azure.ai.projects.models import AgentVersionObject, AgentReference
from openai.types.conversations.message import Message
from openai.types.responses import ResponseOutputMessage
from openai.types.conversations import Conversation

from azure.storage.blob.aio import BlobServiceClient
from azure.storage.blob import generate_blob_sas, BlobSasPermissions
from azure.identity.aio import DefaultAzureCredential

from azure.ai.projects.aio import AIProjectClient

from util import encode_project_resource_id

from urllib.parse import quote 

from openai import AsyncOpenAI

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets

# Create a logger for this module
logger = logging.getLogger("azureaiapp")

# Set the log level for the azure HTTP logging policy to WARNING (or ERROR)
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)

from opentelemetry import trace

tracer = trace.get_tracer(__name__)

# Define the directory for your templates.
directory = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=directory)

# Create a new FastAPI router
router = fastapi.APIRouter()

# ── Auth setup ────────────────────────────────────────────────────────────────

security = HTTPBasic()

username = os.getenv("WEB_APP_USERNAME")
password = os.getenv("WEB_APP_PASSWORD")
basic_auth = username and password


def authenticate(credentials: Optional[HTTPBasicCredentials] = Depends(security)) -> None:
    if not basic_auth:
        logger.info("Skipping authentication: WEB_APP_USERNAME or WEB_APP_PASSWORD not set.")
        return

    correct_username = secrets.compare_digest(credentials.username, username)
    correct_password = secrets.compare_digest(credentials.password, password)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return


# auth_dependency MUST be defined before any route references it
auth_dependency = Depends(authenticate) if basic_auth else None

# ── Helpers ───────────────────────────────────────────────────────────────────

def cleanup_created_at_metadata(metadata: Mapping[str, str]) -> None:
    """Remove oldest created_at timestamp entries to keep metadata under 16 items limit."""
    if not metadata:
        return
    while len(metadata) > 16:
        created_at_keys = [k for k in metadata if k.endswith("_created_at")]
        if not created_at_keys:
            break
        min_key = min(created_at_keys, key=metadata.get)
        del metadata[min_key]


def get_project_client(request: Request) -> AIProjectClient:
    return request.app.state.ai_project


def get_agent_version_obj(request: Request) -> AgentVersionObject:
    return request.app.state.agent_version_obj


def get_openai_client(request: Request) -> AsyncOpenAI:
    return get_project_client(request).get_openai_client()


def get_created_at_label(message_id: str) -> str:
    return f"{message_id}_created_at"


def serialize_sse_event(data: Dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


async def get_or_create_conversation(
    openai_client: AsyncOpenAI,
    conversation_id: Optional[str],
    agent_id: Optional[str],
    current_agent_id: str
) -> Conversation:
    """Get an existing conversation or create a new one."""
    conversation: Optional[Conversation] = None

    if conversation_id and agent_id == current_agent_id:
        try:
            logger.info(f"Using existing conversation with ID {conversation_id}")
            conversation = await openai_client.conversations.retrieve(conversation_id=conversation_id)
            logger.info(f"Retrieved conversation: {conversation.id}")
        except Exception as e:
            logger.error(f"Error retrieving conversation: {e}")

    if not conversation:
        try:
            logger.info("Creating a new conversation")
            conversation = await openai_client.conversations.create()
            logger.info(f"Generated new conversation ID: {conversation.id}")
        except Exception as e:
            logger.error(f"Error creating conversation: {e}")
            raise HTTPException(status_code=400, detail=f"Error handling conversation: {e}")

    return conversation


async def get_container_file_as_base64(
    openai_client: AsyncOpenAI,
    file_id: str,
    container_id: str
) -> Optional[str]:
    """
    Download a file from a Code Interpreter container and convert to base64.
    This is the CORRECT method for Microsoft Foundry Code Interpreter files.
    """
    try:
        logger.info(f"📥 Downloading container file: {file_id} from container: {container_id}")

        file_content = await openai_client.containers.files.content.retrieve(
            file_id=file_id,
            container_id=container_id
        )

        file_bytes = file_content.read()
        base64_encoded = base64.b64encode(file_bytes).decode('utf-8')
        logger.info(f"✅ Successfully converted file {file_id} to base64 ({len(file_bytes)/1024:.1f} KB)")
        return base64_encoded
    except Exception as e:
        logger.error(f"❌ Error downloading container file {file_id}: {e}", exc_info=True)
        return None


async def get_message_and_annotations(
    event: Message | ResponseOutputMessage,
    openai_client: AsyncOpenAI = None
) -> Dict:
    """
    Extract message content, annotations, and images from a message event.
    Each annotation type is handled independently to avoid attribute errors.
    """
    annotations = []
    images = []
    text = ""

    content = event.content[0] if event.content else None
    if not content:
        return {'content': '', 'annotations': [], 'images': []}

    if content.type in ("output_text", "input_text"):
        text = content.text

    if content.type == "output_text":
        for annotation in content.annotations:

            if annotation.type == "file_citation":
                # file_citation has: filename, index
                label = getattr(annotation, 'filename', '') or ""
                ann = {
                    'label': label,
                    'index': annotation.index,
                    'type': 'file_citation',
                    'url': f"/api/document/{quote(label)}" if label else None,
                }
                annotations.append(ann)

            elif annotation.type == "url_citation":
                # annotation.url is always the AI Search endpoint — not the blob URL
                # Use title (filename) and let get_document resolve the full blob path
                label = getattr(annotation, 'title', '') or ""
                proxy_url = f"/api/document/{quote(label)}" if label else None
                logger.info(f"Citation: '{label}' → {proxy_url}")

                ann = {
                    'label': label,
                    'index': getattr(annotation, 'start_index', None),
                    'type': 'url_citation',
                    'url': proxy_url,
                }
                annotations.append(ann)

            elif annotation.type == "container_file_citation":
                # container_file_citation: file_id, container_id, filename
                logger.info(f"🎯 Found Code Interpreter output: {annotation.filename}")
                file_id = annotation.file_id
                container_id = annotation.container_id
                filename = annotation.filename

                ann = {
                    'label': filename,
                    'file_id': file_id,
                    'container_id': container_id,
                    'type': 'container_file_citation',
                }
                annotations.append(ann)

                # Download images generated by Code Interpreter
                if openai_client and filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                    base64_image = await get_container_file_as_base64(
                        openai_client, file_id, container_id
                    )
                    if base64_image:
                        images.append({
                            'file_id': file_id,
                            'container_id': container_id,
                            'filename': filename,
                            'data': base64_image,
                            'mime_type': 'image/png'
                        })
                        logger.info(f"✅ Added Code Interpreter image: {filename}")

            else:
                logger.warning(f"Unknown annotation type '{annotation.type}' — skipping")

    return {
        'content': text,
        'annotations': annotations,
        'images': images,
    }


async def save_user_message_created_at(
    openai_client: AsyncOpenAI,
    conversation: Conversation,
    input_created_at: float
):
    conversation.metadata = conversation.metadata or {}
    try:
        logger.info("Saving created_at.")
        messages = await openai_client.conversations.items.list(
            conversation_id=conversation.id, order="desc"
        )
        last_input_message = None
        async for message in messages:
            if isinstance(message, Message) and message.role == "user":
                last_input_message = message
                break
        if last_input_message:
            conversation.metadata[get_created_at_label(last_input_message.id)] = str(input_created_at)
        cleanup_created_at_metadata(conversation.metadata)
        await openai_client.conversations.update(conversation.id, metadata=conversation.metadata)
        logger.info("Successfully saved created_at for user message")
    except Exception as e:
        logger.error(f"Error updating message created_at: {e}")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def index(request: Request, _ = auth_dependency):
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/api/document/{filename:path}")
async def get_document(filename: str, request: Request, _=auth_dependency):
    account_url = os.environ.get("AZURE_STORAGE_ACCOUNT_URL")
    container_name = os.environ.get("AZURE_STORAGE_CONTAINER_NAME")
    account_name = os.environ.get("AZURE_STORAGE_ACCOUNT_NAME")

    if not all([account_url, container_name, account_name]):
        raise HTTPException(status_code=500, detail="Blob storage env vars not configured")

    try:
        async with DefaultAzureCredential() as credential:
            async with BlobServiceClient(account_url=account_url.rstrip('/'), credential=credential) as svc:
                container_client = svc.get_container_client(container_name)

                # filename may be just "Minutes of the 28th...doc" without subfolder
                # Search all blobs for an exact name match
                actual_blob_name = None
                async for blob in container_client.list_blobs():
                    if blob.name == filename or blob.name.endswith(f"/{filename}"):
                        actual_blob_name = blob.name
                        break

                if not actual_blob_name:
                    logger.warning(f"Blob not found: '{filename}'")
                    raise HTTPException(status_code=404, detail=f"Document not found: {filename}")

                logger.info(f"Resolved '{filename}' → '{actual_blob_name}'")

                now = datetime.now(timezone.utc)
                delegation_key = await svc.get_user_delegation_key(
                    key_start_time=now,
                    key_expiry_time=now + timedelta(hours=1),
                )
                sas_token = generate_blob_sas(
                    account_name=account_name,
                    container_name=container_name,
                    blob_name=actual_blob_name,
                    user_delegation_key=delegation_key,
                    permission=BlobSasPermissions(read=True),
                    expiry=now + timedelta(minutes=15),
                )
                blob_url = f"{account_url.rstrip('/')}/{container_name}/{quote(actual_blob_name)}?{sas_token}"
                logger.info(f"SAS redirect: {actual_blob_name}")
                return RedirectResponse(url=blob_url, status_code=302)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate SAS for '{filename}': {e}", exc_info=True)
        raise HTTPException(status_code=404, detail="Document not found")


@router.get("/chat/history")
async def history(
    request: Request,
    agent: AgentVersionObject = Depends(get_agent_version_obj),
    openai_client: AsyncOpenAI = Depends(get_openai_client),
    _ = auth_dependency,
):
    with tracer.start_as_current_span("chat_history"):
        async with openai_client:
            conversation_id = request.cookies.get('conversation_id')
            agent_id = request.cookies.get('agent_id')

            conversation = await get_or_create_conversation(
                openai_client, conversation_id, agent_id, agent.id
            )
            agent_id = agent.id

            try:
                content = []
                items = await openai_client.conversations.items.list(
                    conversation_id=conversation.id, order="desc", limit=16
                )
                async for item in items:
                    if item.type == "message":
                        formatted_message = await get_message_and_annotations(item, openai_client)
                        formatted_message['role'] = item.role
                        formatted_message['created_at'] = conversation.metadata.get(
                            get_created_at_label(item.id), ""
                        )
                        content.append(formatted_message)

                logger.info(f"List message, conversation ID: {conversation_id}")
                response = JSONResponse(content=content)
                response.set_cookie("conversation_id", conversation_id)
                response.set_cookie("agent_id", agent_id)
                return response
            except Exception as e:
                logger.error(f"Error listing message: {e}")
                raise HTTPException(status_code=500, detail=f"Error list message: {e}")


@router.get("/agent")
async def get_chat_agent(
    agent: AgentVersionObject = Depends(get_agent_version_obj),
):
    wsid = os.environ.get("AZURE_EXISTING_AIPROJECT_RESOURCE_ID")
    agent_id = os.environ.get("AZURE_EXISTING_AGENT_ID")

    if not wsid or not agent_id:
        return JSONResponse(content={
            "name": agent.name,
            "metadata": agent.metadata,
            "agentPlaygroundUrl": None
        })

    try:
        agent_name = agent_id.split(":")[0]
        agent_version = agent_id.split(":")[1]
        agent_playground_url = (
            f"https://ai.azure.com/nextgen/r/{encode_project_resource_id(wsid)}"
            f"/build/agents/{quote(agent_name)}/build?version={agent_version}"
        )
        return JSONResponse(content={
            "name": agent.name,
            "metadata": agent.metadata,
            "agentPlaygroundUrl": agent_playground_url
        })
    except Exception as e:
        logger.error(f"Error generating agent playground URL: {e}")
        return JSONResponse(content={
            "name": agent.name,
            "metadata": agent.metadata,
            "agentPlaygroundUrl": None
        })


@router.post("/chat")
async def chat(
    request: Request,
    project_client: AIProjectClient = Depends(get_project_client),
    agent: AgentVersionObject = Depends(get_agent_version_obj),
    _ = auth_dependency,
):
    conversation_id = request.cookies.get('conversation_id')
    agent_id = request.cookies.get('agent_id')

    carrier = {}
    TraceContextTextMapPropagator().inject(carrier)

    with tracer.start_as_current_span("chat_request"):
        async with project_client.get_openai_client() as openai_client:
            conversation = await get_or_create_conversation(
                openai_client, conversation_id, agent_id, agent.id
            )
            conversation_id = conversation.id
            agent_id = agent.id

    try:
        user_message = await request.json()
    except Exception as e:
        logger.error(f"Invalid JSON in request: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON in request: {e}")

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Content-Type": "text/event-stream"
    }
    logger.info(f"Starting streaming response for conversation ID {conversation_id}")

    response = StreamingResponse(
        get_result(agent, conversation, user_message.get('message', ''), project_client, carrier),
        headers=headers
    )
    response.set_cookie("conversation_id", conversation_id)
    response.set_cookie("agent_id", agent_id)
    return response


async def get_result(
    agent: AgentVersionObject,
    conversation: Conversation,
    user_message: str,
    project_client: AIProjectClient,
    carrier: Dict[str, str]
) -> AsyncGenerator[str, None]:
    ctx = TraceContextTextMapPropagator().extract(carrier=carrier)
    with tracer.start_as_current_span('get_result', context=ctx):
        async with project_client.get_openai_client() as openai_client:
            logger.info(f"get_result invoked for conversation={conversation.id}")
            input_created_at = datetime.now(timezone.utc).timestamp()
            try:
                response = await openai_client.responses.create(
                    conversation=conversation.id,
                    input=user_message,
                    extra_body={"agent": AgentReference(name=agent.name, version=agent.version).as_dict()},
                    stream=True
                )
                logger.info("Successfully created stream; starting to process events")

                async for event in response:
                    if event.type == "response.created":
                        logger.info(f"Stream response created with ID: {event.response.id}")

                    elif event.type == "response.output_text.delta":
                        logger.info(f"Delta: {event.delta}")
                        stream_data = {'content': event.delta, 'type': "message"}
                        yield serialize_sse_event(stream_data)

                    elif event.type == "response.output_item.done" and event.item.type == "message":
                        stream_data = await get_message_and_annotations(event.item, openai_client)
                        stream_data['type'] = "completed_message"
                        yield serialize_sse_event(stream_data)

                    elif event.type == "response.completed":
                        logger.info(f"Response completed with full message: {event.response.output_text}")

                    elif event.type == "response.code_interpreter.logs":
                        logger.info(f"Code Interpreter logs: {event.logs}")
                        stream_data = {
                            'content': f"[Code Execution Logs]\n{event.logs}",
                            'type': "code_logs"
                        }
                        yield serialize_sse_event(stream_data)

            except Exception as e:
                logger.exception(f"Exception in get_result: {e}")
                error_data = {
                    'content': str(e),
                    'annotations': [],
                    'images': [],
                    'type': "completed_message"
                }
                yield serialize_sse_event(error_data)
            finally:
                stream_data = {'type': "stream_end"}
                await save_user_message_created_at(openai_client, conversation, input_created_at)
                yield serialize_sse_event(stream_data)
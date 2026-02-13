# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE.md file in the project root for full license information.

import asyncio
import json
import os
import base64
from datetime import datetime, timezone
from typing import AsyncGenerator, Mapping, Optional, Dict


import fastapi
from fastapi import Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse

import logging
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from azure.ai.projects.models import AgentVersionObject, AgentReference
from openai.types.conversations.message import Message
from openai.types.responses import ResponseOutputMessage
from openai.types.conversations import Conversation

from azure.ai.projects.aio import AIProjectClient

from util import encode_project_resource_id

from urllib.parse import quote


from openai import AsyncOpenAI

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

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from typing import Optional
import secrets

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

auth_dependency = Depends(authenticate) if basic_auth else None

def cleanup_created_at_metadata(metadata: Mapping[str, str]) -> None:
    """Remove oldest created_at timestamp entries to keep metadata under 16 items limit."""
    if not metadata:
        return

    # metadata go to be up to 16 items.  If there is more than that, remove the one ended with _created_at key with smallest value
    while len(metadata) > 16:
        created_at_keys = [k for k in metadata if k.endswith("_created_at")]
        if not created_at_keys:
            break  # No more _created_at keys to remove
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
    """
    Get an existing conversation or create a new one.
    Returns the conversation_id.
    """
    conversation: Optional[Conversation] = None
    
    # Attempt to get an existing conversation if we have matching agent and conversation IDs
    if conversation_id and agent_id == current_agent_id:
        try:
            logger.info(f"Using existing conversation with ID {conversation_id}")
            conversation = await openai_client.conversations.retrieve(conversation_id=conversation_id)
            logger.info(f"Retrieved conversation: {conversation.id}")
        except Exception as e:
            logger.error(f"Error retrieving conversation: {e}")

    # Create a new conversation if we don't have one
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
        
        # Use the containers API endpoint (Microsoft Foundry specific)
        file_content = await openai_client.containers.files.content.retrieve(
            file_id=file_id,
            container_id=container_id
        )
        
        # Read the content as bytes
        file_bytes = file_content.read()
        
        # Encode to base64
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
    Specifically handles container_file_citation from Code Interpreter.
    """
    annotations = []
    images = []
    text = ""
    
    # Get the first content block (usually text)
    content = event.content[0] if event.content else None
    if not content:
        return {'content': '', 'annotations': [], 'images': []}
    
    # Extract text content
    if content.type == "output_text" or content.type == "input_text":
        text = content.text
        
    # Process annotations (including Code Interpreter file citations)
    if content.type == "output_text":
        for annotation in content.annotations:
            # Handle regular file citations (from file search)
            if annotation.type == "file_citation":
                ann = {
                    'label': annotation.filename,
                    "index": annotation.index,
                    "type": "file_citation"
                }
                annotations.append(ann)
            
            # Handle URL citations
            elif annotation.type == "url_citation":
                ann = {
                    'label': annotation.title,
                    "index": annotation.start_index,
                    "type": "url_citation"
                }
                annotations.append(ann)
            
            # Handle Code Interpreter container file citations (THIS IS THE KEY!)
            elif annotation.type == "container_file_citation":
                logger.info(f"🎯 Found Code Interpreter output: {annotation.filename}")
                
                file_id = annotation.file_id
                container_id = annotation.container_id
                filename = annotation.filename
                
                # Add to annotations
                ann = {
                    'label': filename,
                    'file_id': file_id,
                    'container_id': container_id,
                    "type": "container_file_citation"
                }
                annotations.append(ann)
                
                # Download and convert to base64 if it's an image
                if openai_client and filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                    base64_image = await get_container_file_as_base64(
                        openai_client, 
                        file_id, 
                        container_id
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
            
    return {
        'content': text,
        'annotations': annotations,
        'images': images
    }


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, _ = auth_dependency):
    return templates.TemplateResponse(
        "index.html", 
        {
            "request": request,
        }
    )

async def save_user_message_created_at(openai_client: AsyncOpenAI, conversation: Conversation,  input_created_at: float):
    conversation.metadata = conversation.metadata  or {}
    try:
        logger.info(f"Saving created_at.")
        messages = await openai_client.conversations.items.list(conversation_id=conversation.id, order="desc")
        last_input_message = None
        async for message in messages:
            if isinstance(message, Message) and message.role == "user":
                last_input_message = message
                break
        if last_input_message:
            conversation.metadata[get_created_at_label(last_input_message.id)] = str(input_created_at)
        cleanup_created_at_metadata(conversation.metadata)

        await openai_client.conversations.update(conversation.id, metadata=conversation.metadata)
        
        logger.info(f"Successfully saved created_at for user message")
        return  # Success, exit the retry loop

    except Exception as e:
        logger.error(f"Error updating message created_at.")
        


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
                        # Process the completed message (includes Code Interpreter images)
                        stream_data = await get_message_and_annotations(event.item, openai_client)
                        stream_data['type'] = "completed_message"
                        yield serialize_sse_event(stream_data)
                        
                    elif event.type == "response.completed":
                        logger.info(f"Response completed with full message: {event.response.output_text}")
                        
                    # Handle code interpreter logs (optional)
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



@router.get("/chat/history")
async def history(
    request: Request,
    agent: AgentVersionObject = Depends(get_agent_version_obj),
    openai_client : AsyncOpenAI = Depends(get_openai_client),
	_ = auth_dependency
):
    with tracer.start_as_current_span("chat_history"):
        async with openai_client:
            conversation_id = request.cookies.get('conversation_id')
            agent_id = request.cookies.get('agent_id')

            # Get or create conversation using the reusable function
            conversation = await get_or_create_conversation(
                openai_client, conversation_id, agent_id, agent.id
            )
            agent_id = agent.id
            # Create a new message from the user's input.
            try:
                content = []
                items = await openai_client.conversations.items.list(conversation_id=conversation.id, order="desc", limit=16)
                async for item in items:
                    if item.type == "message":
                        # Include openai_client to handle images in history
                        formatteded_message = await get_message_and_annotations(item, openai_client)
                        formatteded_message['role'] = item.role
                        formatteded_message['created_at'] = conversation.metadata.get(get_created_at_label(item.id), "")
                        content.append(formatteded_message)


                logger.info(f"List message, conversation ID: {conversation_id}")
                response = JSONResponse(content=content)
            
                # Update cookies to persist the conversation IDs.
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
    
    # Add error handling for missing wsid
    if not wsid or not agent_id:
        return JSONResponse(content={
            "name": agent.name, 
            "metadata": agent.metadata,
            "agentPlaygroundUrl": None
        })
    
    try:
        agent_name = agent_id.split(":")[0]
        agent_version = agent_id.split(":")[1]
        agent_playground_url = f"https://ai.azure.com/nextgen/r/{encode_project_resource_id(wsid)}/build/agents/{quote(agent_name)}/build?version={agent_version}"
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
    
	_ = auth_dependency
):
    # Retrieve the conversation ID from the cookies (if available).
    conversation_id = request.cookies.get('conversation_id')
    agent_id = request.cookies.get('agent_id')    

    carrier = {}        
    TraceContextTextMapPropagator().inject(carrier)

    with tracer.start_as_current_span("chat_request"):
        async with project_client.get_openai_client() as openai_client:
            # if the connection no longer exist or agent is changed, create a new one
            conversation = await get_or_create_conversation(
                openai_client, conversation_id, agent_id, agent.id
            )
            conversation_id = conversation.id
            agent_id = agent.id
        
    # Parse the JSON from the request.
    try:
        user_message = await request.json()
    except Exception as e:
        logger.error(f"Invalid JSON in request: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON in request: {e}")
    # Create a new message from the user's input.

    # Set the Server-Sent Events (SSE) response headers.
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Content-Type": "text/event-stream"
    }
    logger.info(f"Starting streaming response for conversation ID {conversation_id}")

    # Create the streaming response using the generator.
    response = StreamingResponse(get_result(agent, conversation, user_message.get('message', ''), project_client, carrier), headers=headers)

    # Update cookies to persist the conversation and agent IDs.
    response.set_cookie("conversation_id", conversation_id)
    response.set_cookie("agent_id", agent_id)
    return response
import json
import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.websockets import WebSocketState
# from llm import LlmClient
from llm_with_func_calling import LlmClient
from twilio_server import TwilioClient
from retellclient.models import operations
from twilio.twiml.voice_response import VoiceResponse
import asyncio
import retellclient
from retellclient.models import operations
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

class Item(BaseModel):
    agent_id: str

load_dotenv(override=True)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins="*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# twilio_client = TwilioClient()

# twilio_client.create_phone_number(213, os.environ['RETELL_AGENT_ID'])
# twilio_client.delete_phone_number("+12133548310")
# twilio_client.register_phone_agent("+12138166806", os.environ['RETELL_AGENT_ID'])
# twilio_client.create_phone_call("+12138166806", "+919081382087", os.environ['RETELL_AGENT_ID'])

# @app.post("/twilio-voice-webhook/{agent_id_path}")
# async def handle_twilio_voice_webhook(request: Request, agent_id_path: str):
#     print("twilio-voice-webhook called.")
#     try:
#         # Check if it is machine
#         post_data = await request.form()
#         print(f"Post data: {post_data}")
#         if 'AnsweredBy' in post_data and post_data['AnsweredBy'] == "machine_start":
#             print("in 111")
#             twilio_client.end_call(post_data['CallSid'])
#             return PlainTextResponse("")
#         elif 'AnsweredBy' in post_data:
#             print("in 222")
#             return PlainTextResponse("") 

#         call_response = twilio_client.retell.register_call(operations.RegisterCallRequestBody(
#             agent_id=agent_id_path, 
#             audio_websocket_protocol="twilio", 
#             audio_encoding="mulaw", 
#             sample_rate=8000,
#             end_call_after_silence_ms=10000
#         ))
#         print(f"Call response: {call_response}")
#         if call_response.call_detail:
#             response = VoiceResponse()
#             print(f"Call response: {response}")
#             start = response.connect()
#             start.stream(url=f"wss://api.retellai.com/audio-websocket/{call_response.call_detail.call_id}")
#             return PlainTextResponse(str(response), media_type='text/xml')
#     except Exception as err:
#         print(f"Error in twilio voice webhook: {err}")
#         return JSONResponse(status_code=500, content={"message": "Internal Server Error"})

@app.websocket("/llm-websocket/{call_id}")
async def websocket_handler(websocket: WebSocket, call_id: str):
    await websocket.accept()
    print(f"Handle llm ws for: {call_id}")

    llm_client = LlmClient()

    # send first message to signal ready of server
    response_id = 0
    first_event = llm_client.draft_begin_messsage()
    print(f"First event: {first_event}")
    await websocket.send_text(json.dumps(first_event))

    async def stream_response(request):
        nonlocal response_id
        for event in llm_client.draft_response(request):
            await websocket.send_text(json.dumps(event))
            if request['response_id'] < response_id:
                return # new response needed, abondon this one
    try:
        while True:
            message = await websocket.receive_text()
            request = json.loads(message)
            # print out transcript
            os.system('cls' if os.name == 'nt' else 'clear')
            print(json.dumps(request, indent=4))
            
            if 'response_id' not in request:
                continue # no response needed, process live transcript update if needed
            response_id = request['response_id']
            asyncio.create_task(stream_response(request))
    except WebSocketDisconnect:
        print(f"LLM WebSocket disconnected for {call_id}")
    except Exception as e:
        print(f'LLM WebSocket error for {call_id}: {e}')
    finally:
        print(f"LLM WebSocket connection closed for {call_id}")
        
@app.post("/register_call")
async def register_call(Item: Item):
    try:
        retell = retellclient.RetellClient(api_key=os.environ['RETELL_API_KEY'])
        register_call_response = retell.register_call(operations.RegisterCallRequestBody(agent_id=Item.agent_id,audio_websocket_protocol='web',audio_encoding='s16le',sample_rate=44000))
        serialized_response = {
            "content_type": register_call_response.content_type,
            "status_code": register_call_response.status_code,
            "call_detail": {
                "agent_id": register_call_response.call_detail.agent_id,
                "audio_encoding": register_call_response.call_detail.audio_encoding.value,
                "audio_websocket_protocol": register_call_response.call_detail.audio_websocket_protocol.value,
                "call_id": register_call_response.call_detail.call_id,
                "call_status": register_call_response.call_detail.call_status.value,
                "sample_rate": register_call_response.call_detail.sample_rate,
                "start_timestamp": register_call_response.call_detail.start_timestamp,
                "end_timestamp": register_call_response.call_detail.end_timestamp,
                "recording_url": register_call_response.call_detail.recording_url,
                "transcript": register_call_response.call_detail.transcript,
                "end_call_after_silence_ms": register_call_response.call_detail.end_call_after_silence_ms
            }
        }
        return JSONResponse(status_code=200, content=serialized_response)
    except Exception as err:
        print(f"Error in register_call: {err}")
        return JSONResponse(status_code=500, content={"message": "Internal Server Error"})
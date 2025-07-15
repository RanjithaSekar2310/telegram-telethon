import os
import json
import asyncio
import datetime
import streamlit as st
from typing import List, Dict, Any, Callable, Set
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest
from azure.identity import DefaultAzureCredential
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import FunctionTool, ToolSet, MessageRole

# ------------------- Load environment -------------------
load_dotenv()
TELEGRAM_API_ID = 27339628
TELEGRAM_API_HASH = '6b1f8122babc7ebfeedb7b62f2c9970d'
project_endpoint = "https://hub-totalenergies-002.services.ai.azure.com/api/projects/total-energies-tele-test"
model_deployment = "gpt-4.1"

api_id = int(TELEGRAM_API_ID)
api_hash = TELEGRAM_API_HASH
TELEGRAM_CHANNELS = [
    'SabrenNews22', 'alsumariatviraq', 'maymun5',
    'basrah_net', 'IraqiPmo', 'basrah_oil', 'ElamAlmoqawama'
]

# ------------------- Telegram Agent Function -------------------
async def _fetch_messages_async(keywords: List[str], message_limit: int = 120) -> Dict[str, Any]:
    all_messages, filtered_messages = [], []
    mentioned_channels = [ch for ch in TELEGRAM_CHANNELS if any(ch.lower() in kw.lower() for kw in keywords)]

    async with TelegramClient('anon', api_id, api_hash) as client:
        for username in TELEGRAM_CHANNELS:
            try:
                channel = await client.get_entity(username)
                history = await client(GetHistoryRequest(
                    peer=channel,
                    limit=message_limit,
                    offset_date=None,
                    offset_id=0,
                    max_id=0,
                    min_id=0,
                    add_offset=0,
                    hash=0
                ))
                for message in history.messages:
                    if message.message:
                        msg = {
                            "channel": username,
                            "date": str(message.date),
                            "message": message.message,
                            "url": f"https://t.me/s/{channel.username}/{message.id}" if hasattr(channel, 'username') else None
                        }
                        all_messages.append(msg)
                        if username in mentioned_channels or any(kw.lower() in msg["message"].lower() for kw in keywords):
                            filtered_messages.append(msg)
            except Exception as e:
                all_messages.append({"channel": username, "error": str(e)})

    return {"keywords_used": keywords, "matched_messages": filtered_messages}

def fetch_telegram_channel_messages(keywords: List[str], message_limit: int = 120) -> Dict[str, Any]:
    return asyncio.run(_fetch_messages_async(keywords, message_limit))

# ------------------- Azure Agent Setup -------------------
user_functions: Set[Callable[..., Any]] = {fetch_telegram_channel_messages}
functions = FunctionTool(user_functions)
toolset = ToolSet()
toolset.add(functions)

@st.cache_resource
def init_agent():
    agent_client = AgentsClient(
        endpoint=project_endpoint,
        credential=DefaultAzureCredential(
            exclude_environment_credential=True,
            exclude_managed_identity_credential=True
        )
    )
    agent_client.enable_auto_function_calls(toolset)
    agent = agent_client.create_agent(
        model=model_deployment,
        name="telegram-fetch-agent",
        instructions = """
                            You are a Telegram Intelligence Agent monitoring and analyzing posts from specific Telegram channels.

                            Your Tasks:
                            1. Accept user input in **Arabic**, **Persian**, **French**, or **English**.
                            2. Internally **translate the input to English** to fully understand the intent.
                            3. Extract **key topics, keywords, and named entities** (e.g., "oil smuggling", "Basra", "Ali al-Sistani").
                            4. If any **Telegram channel names** are mentioned (e.g., SabreenNews22), extract them.

                            Keyword Handling:
                            - For each extracted keyword:
                                • Normalize plural and singular forms (e.g., "protests" ↔ "protest").
                                • Expand to **synonyms**, **related phrases**, and **semantically similar terms** (e.g., “fuel smuggling”, “illegal oil trade”).
                                • Include **alternate spellings** and **transliterations** (e.g., "Irak" ↔ "Iraq").
                                • Translate all keywords (original + expanded) into **Arabic**, **Persian**, and **French**.
                            - Combine all keyword variants into a single list called `final_keywords`.

                            Search Instructions:
                            - Use the function:
                                `fetch_telegram_channel_messages(final_keywords)`
                            - The function must:
                                • Use all generated keywords for filtering.
                                • Match messages where **any keyword appears**, even partially.
                                • Allow **fuzzy matching** and **semantic similarity** — do NOT limit to exact phrases.
                                • Return only the **most recent N messages** (e.g., 10–20), sorted by newest first.
                                • Retain messages in their **original language**.

                            Response Responsibilities:
                            - Read all retrieved messages and **summarize their meaning in English**, regardless of original language.
                            - Extract and highlight the **5 most important insights** or facts as bullet points.
                            - Include a list of **Telegram source links**, with optional message summary or date.

                            Response Format:
                            **User Question (Translated to English):** <translated_query>  
                            **Answer (in English):**
                            - Bullet point 1  
                            - Bullet point 2  
                            - Bullet point 3  
                            - Bullet point 4  
                            - Bullet point 5  

                            **Telegram Source(s):**
                            [ChannelName1](URL1) – summary or message date  
                            [ChannelName2](URL2) – summary or message date  

                            Supported Query Types:
                            - **Location-based**: “What’s happening in Basra?”
                            - **Event-based**: “Explosion in Baghdad refinery yesterday?”
                            - **Topic-based**: “Fuel smuggling”, “AI policy”, “Election protests”
                            - **People/org-based**: “Statements by Muqtada al-Sadr”, “Updates from TotalEnergies”
                            - **Temporal-based**: “What happened in Iraq last night?”

                            Critical Rules:
                            - **Plural and singular forms must be treated equally**.
                            - **Always prioritize semantic similarity over literal matching**.
                            - **Be tolerant to typos, variants, and non-English spellings**.
                            - **Summarize clearly in English** even if the content is in Arabic, Persian, or French.
                            """
,
        toolset=toolset
    )
    thread = agent_client.threads.create()
    return agent_client, agent, thread

# ------------------- Formatting Helper -------------------
def format_reply(raw_text: str) -> str:
    return raw_text.replace("\\n", "\n")

# ------------------- Streamlit UI -------------------
st.set_page_config(page_title="Telegram Intelligence Agent", layout="wide")
st.markdown('<h2>📡 Telegram Intelligence Agent</h2>', unsafe_allow_html=True)
st.markdown("Monitor and summarize Telegram updates using Azure AI Agents.")


# First-time setup
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "agent_data" not in st.session_state:
    st.session_state.agent_data = init_agent()

agent_client, agent, thread = st.session_state.agent_data

# Show chat history
for msg in st.session_state.chat_history:
    st.markdown(f'<div style="background:#e6f7ff;padding:10px;border-radius:5px"><b>User:</b><br>{msg["user"]}</div>', unsafe_allow_html=True)
    # st.markdown(f'<div style="background:#f9f9f9;padding:10px;border-radius:5px"><b>Agent:</b><br>{msg["bot"]}</div>', unsafe_allow_html=True)
    st.markdown(
    f'''
    <div style="background:#f9f9f9; padding:10px; border-radius:5px; color:#000000">
        <b>Agent:</b><br>{msg["bot"]}
    </div>
    ''', 
    unsafe_allow_html=True
)

# New input
user_input = st.chat_input("Type your message and press Enter…")

if user_input:
    agent_client.messages.create(thread_id=thread.id, role="user", content=user_input)
    agent_client.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)

    messages = list(agent_client.messages.list(thread_id=thread.id))
    agent_messages = [
        m for m in messages if m.role == MessageRole.AGENT and m.content and m.content[0].text
    ]
    agent_messages.sort(key=lambda m: m.created_at, reverse=True)
    last_msg = agent_messages[0] if agent_messages else None

    if last_msg:
        reply = format_reply(last_msg.content[0].text["value"])
    else:
        reply = " Sorry, I didn't understand that."

    st.session_state.chat_history.append({"user": user_input, "bot": reply})
    st.rerun()
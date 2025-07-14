import os
import json
from typing import List, Dict, Any, Set, Callable
from dotenv import load_dotenv
from telethon.sync import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest

from azure.identity import DefaultAzureCredential
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import FunctionTool, ToolSet, ListSortOrder, MessageRole

# Load environment variables
load_dotenv()

api_id = 27339628
api_hash = '6b1f8122babc7ebfeedb7b62f2c9970d'

# Predefined Telegram channels
TELEGRAM_CHANNELS = [
    'SabrenNews22',
    'alsumariatviraq',
    'maymun5',
    'basrah_net',
    'IraqiPmo',
    'basrah_oil',
    'ElamAlmoqawama'
]

def fetch_telegram_channel_messages(keywords: List[str], message_limit: int = 120) -> Dict[str, Any]:
    print("🔍 [DEBUG] Filtering with keywords:", keywords)
    all_messages = []
    filtered_messages = []

    # Determine if any specific channels are mentioned
    mentioned_channels = [
        ch for ch in TELEGRAM_CHANNELS if any(ch.lower() in kw.lower() for kw in keywords)
    ]

    with TelegramClient('anon', api_id, api_hash) as client:
        for username in TELEGRAM_CHANNELS:
            try:
                channel = client.get_entity(username)
                history = client(GetHistoryRequest(
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

                        # If user asked for this channel's news, keep all messages
                        if username in mentioned_channels:
                            filtered_messages.append(msg)
                        else:
                            # Filter by keyword content
                            if any(kw.lower() in msg["message"].lower() for kw in keywords):
                                filtered_messages.append(msg)

            except Exception as e:
                all_messages.append({
                    "channel": username,
                    "error": str(e)
                })

    print(f"✅ [DEBUG] Filtered {len(filtered_messages)} messages out of {len(all_messages)} total.")

    # Save logs
    with open("all_messages.json", "w", encoding="utf-8") as f:
        json.dump(all_messages, f, indent=2, ensure_ascii=False)

    with open("filtered_messages.json", "w", encoding="utf-8") as f:
        json.dump(filtered_messages, f, indent=2, ensure_ascii=False)

    return {
        "keywords_used": keywords,
        "matched_messages": filtered_messages
    }

# Register function with the Agent
user_functions: Set[Callable[..., Any]] = {fetch_telegram_channel_messages}

def main():
    os.system('cls' if os.name == 'nt' else 'clear')

    project_endpoint = "https://hub-totalenergies-002.services.ai.azure.com/api/projects/total-energies-tele-test"
    model_deployment = "gpt-4.1"

    agent_client = AgentsClient(
        endpoint=project_endpoint,
        credential=DefaultAzureCredential(
            exclude_environment_credential=True,
            exclude_managed_identity_credential=True
        )
    )

    with agent_client:
        functions = FunctionTool(user_functions)
        toolset = ToolSet()
        toolset.add(functions)
        agent_client.enable_auto_function_calls(toolset)
        print("✅ Registered toolset")

        agent = agent_client.create_agent(
            model=model_deployment,
            name="telegram-fetch-agent1",
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

        print(f"🤖 Created agent: {agent.name} ({agent.id})")

        thread = agent_client.threads.create()
        print("💬 Conversation started.")

        while True:
            user_input = input("Enter a prompt (or type 'quit' to exit): ").strip()
            if user_input.lower() == "quit":
                break
            if not user_input:
                print("❗ Please enter a prompt.")
                continue

            agent_client.messages.create(
                thread_id=thread.id,
                role="user",
                content=user_input
            )

            run = agent_client.runs.create_and_process(
                thread_id=thread.id,
                agent_id=agent.id
            )

            if run.status == "failed":
                print(f"❌ Run failed: {run.last_error}")
                continue

            last_msg = agent_client.messages.get_last_message_text_by_role(
                thread_id=thread.id,
                role=MessageRole.AGENT
            )

            if last_msg:
                print(f"\n🧠 Agent: {last_msg.text.value}\n")
            else:
                print("⚠️ No response from the agent.")

        # Optional: print chat log
        print("\n📜 Conversation Log:\n")
        messages = agent_client.messages.list(thread_id=thread.id, order=ListSortOrder.ASCENDING)
        for msg in messages:
            if msg.text_messages:
                print(f"{msg.role}: {msg.text_messages[-1].text.value}\n")

        agent_client.delete_agent(agent.id)
        print("🗑️ Agent deleted.")

if __name__ == '__main__':
    main()

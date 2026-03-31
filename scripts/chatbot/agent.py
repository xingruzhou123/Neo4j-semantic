"""
Agent setup for the chatbot.
Uses LangChain ReAct agent with tools for Neo4j queries.
Simplified version without APOC dependency.
Includes Safety Shield for hallucination detection and RAG faithfulness.
"""

from llm import llm
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.tools import Tool
from langchain_classic.agents import AgentExecutor, create_react_agent
from langchain_classic.memory import ConversationBufferMemory

from tools.cypher import cypher_qa, SCHEMA_DESCRIPTION
from tools.vector import search_reports
from connect_safeshield import SafetyShield

# Initialize Safety Shield
print("\n[Agent] Initializing Safety Shield...")
safety_shield = SafetyShield(
    llm,
    enable_self_consistency=True,
    enable_rag_faithfulness=True
)

# Chat prompt for general conversation
chat_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "You are an expert research assistant providing information about research projects, datasets, and human-robot interaction studies from a research database."),
        ("human", "{input}"),
    ]
)

general_chat = chat_prompt | llm | StrOutputParser()

# Define tools available to the agent
tools = [
    Tool(
        name="General Chat",
        description="For general discussion about research topics not covered by other tools",
        func=general_chat.invoke,
    ),
    Tool(
        name="Research Database Query",
        description="Use this tool to query the research database for information about research projects, datasets, team members, research methods, human subjects, experiment settings, and sessions. Use Cypher queries to find specific information.",
        func=cypher_qa,
    ),
    Tool(
        name="Report Search",
        description="Search the text content of ingested research reports and papers (PDFs) for detailed methodology, findings, experiment design, data collection procedures, or results. Use this when the user asks about the content of a research paper or report, not for structured database queries.",
        func=search_reports,
    ),
]

# Use simple in-memory conversation buffer
memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

# Agent prompt template
agent_prompt = PromptTemplate.from_template("""
You are an expert research assistant providing information about research projects and datasets.
Be as helpful as possible and return as much information as possible.

The Neo4j database contains the following schema:
""" + SCHEMA_DESCRIPTION + """
Use this schema knowledge to decide which tool to use and how to phrase your queries.
For structured data (project metadata, methods, datasets, robots, subjects), use the Research Database Query tool.
For detailed content from research papers/reports, use the Report Search tool.

Do not answer any questions using your pre-trained knowledge about specific research projects, only use the information provided by the tools.

TOOLS:
------

You have access to the following tools:

{tools}

To use a tool, please use the following format:

```
Thought: Do I need to use a tool? Yes
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
```

When you have a response to say to the Human, or if you do not need to use a tool, you MUST use the format:

```
Thought: Do I need to use a tool? No
Final Answer: [your response here]
```

Begin!

Previous conversation history:
{chat_history}

New input: {input}
{agent_scratchpad}
""")

# Create the ReAct agent
agent = create_react_agent(llm, tools, agent_prompt)

# Create the agent executor
agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    memory=memory,
    verbose=True,
    handle_parsing_errors=True,
)


def generate_response(user_input):
    """
    Generate a response to the user input using the conversational agent.
    Applies Safety Shield checks before returning the final answer.
    Returns a response to be rendered in the UI.
    """
    # Get initial response from agent
    response = agent_executor.invoke({"input": user_input})
    original_answer = response['output']

    # Extract any intermediate steps for evidence (if available)
    intermediate_steps = response.get('intermediate_steps', [])
    evidence_list = []

    # Try to extract cypher query results as evidence
    for step in intermediate_steps:
        if hasattr(step, '__iter__') and len(step) >= 2:
            action, observation = step[0], step[1]
            if observation and isinstance(observation, str):
                evidence_list.append(observation)

    # Apply Safety Shield
    print("\n[Agent] Applying Safety Shield to response...")
    context = {
        "retrieved_docs": evidence_list,
        "intermediate_steps": intermediate_steps
    }

    final_action, safe_answer, details = safety_shield.check(
        answer=original_answer,
        question=user_input,
        evidence_list=evidence_list if evidence_list else None,
        context=context
    )

    print(f"[Agent] Safety Shield final action: {final_action}")

    return safe_answer

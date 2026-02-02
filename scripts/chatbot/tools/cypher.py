"""
Cypher query tool for Neo4j graph database.
Translates natural language questions into Cypher queries.
Works without APOC plugin.
"""

import sys
sys.path.append('..')

from llm import llm
from graph import driver
from langchain_core.prompts import ChatPromptTemplate
from langchain.schema import StrOutputParser

# Schema description for the LLM (manually defined since APOC is not available)
SCHEMA_DESCRIPTION = """
Node Labels and Properties:
- ResearchProject: rp_id, research_project_title, contact_person_and_email, data_description,
  data_gathering_begin_date, data_gathering_end_date, data_gathering_site, human_subjects,
  instruments, keywords, research_problem_question, study_area, team_members, will_this_data_be_published
- ResearchMethod: rm_id, name, method_details, type_s
- ExperimentInstrument: ei_id, Survey, Code_book
- HumanSubject: hs_id, Age, Gender, Ethnicity, How_many_participants_are_included,
  Regional_Distribution, Recruitment_mode, IRB_Number_and_resolution, Protected_Data
- ExperimentSetting: es_id, Format, Geographical_location, Environment_description, Conditions, Tasks
- Sessions: s_id, Sessions, Number_of_sessions, Trials_per_session, Duration_of_trials, Subjects_per_session
- Dataset: d_id, name, url
- HumanData: hd_id
- HumanData_session: hds_id, session[x]_data_file_path
- Robot: r_id, Robot_type, Model, Robot_Model_URL, Hardware_instrumentation, Software_instrumentation,
  Indicate_if_adaptations_were_made, Implementation, Size, Motion_replay
- RobotData: rd_id
- RobotData_session: rds_id, session[x]_data_file_path

Relationships:
- (ResearchProject)-[:HAS_METHOD]->(ResearchMethod)
- (ResearchProject)-[:HAS_DATASET]->(Dataset)
- (ResearchProject)-[:USES_ROBOT]->(Robot)
- (ResearchMethod)-[:Has_questionnaires]->(ExperimentInstrument)
- (ResearchMethod)-[:Session_HumanSubject]->(HumanSubject)
- (ResearchMethod)-[:Has_Settings]->(ExperimentSetting)
- (ResearchMethod)-[:Has_Sessions]->(Sessions)
- (Dataset)-[:Has_HumanData]->(HumanData)
- (Dataset)-[:Has_RobotData]->(RobotData)
- (HumanData)-[:Has_Session_Data]->(HumanData_session)
- (RobotData)-[:Has_Session_Data]->(RobotData_session)
- (HumanData_session)-[:Aligned_Session]->(RobotData_session)
"""

# Prompt for generating Cypher queries
cypher_generation_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are an expert Neo4j Cypher developer. Convert the user's question into a valid Cypher query.

Use only the provided relationship types and properties in the schema.
Do not use any other relationship types or properties that are not provided.
Always return specific properties, not entire nodes.
Use case-insensitive matching with toLower() and CONTAINS for text searches.

Schema:
{schema}

Return ONLY the Cypher query, no explanations."""),
    ("human", "{question}")
])

# Prompt for generating natural language response from query results
response_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a helpful research assistant. Based on the Cypher query results,
provide a clear and informative answer to the user's question.
If the results are empty, say that no matching information was found.
Format the response nicely with bullet points if there are multiple items."""),
    ("human", "Question: {question}\n\nCypher Query: {cypher}\n\nQuery Results: {results}\n\nPlease provide a helpful answer:")
])

cypher_chain = cypher_generation_prompt | llm | StrOutputParser()
response_chain = response_prompt | llm | StrOutputParser()


def execute_cypher(query: str):
    """Execute a Cypher query and return results."""
    try:
        with driver.session() as session:
            result = session.run(query)
            records = [record.data() for record in result]
            return records
    except Exception as e:
        return f"Error executing query: {str(e)}"


def cypher_qa(question: str) -> str:
    """
    Convert a natural language question to Cypher, execute it, and return a natural language response.
    """
    try:
        # Generate Cypher query
        cypher_query = cypher_chain.invoke({
            "schema": SCHEMA_DESCRIPTION,
            "question": question
        })

        # Clean up the query (remove markdown code blocks if present)
        cypher_query = cypher_query.strip()
        if cypher_query.startswith("```"):
            cypher_query = cypher_query.split("```")[1]
            if cypher_query.startswith("cypher"):
                cypher_query = cypher_query[6:]
        cypher_query = cypher_query.strip()

        print(f"Generated Cypher: {cypher_query}")

        # Execute the query
        results = execute_cypher(cypher_query)

        if isinstance(results, str) and results.startswith("Error"):
            return f"I encountered an error while querying the database: {results}"

        # Generate natural language response
        response = response_chain.invoke({
            "question": question,
            "cypher": cypher_query,
            "results": str(results)
        })

        return response

    except Exception as e:
        return f"I encountered an error: {str(e)}"

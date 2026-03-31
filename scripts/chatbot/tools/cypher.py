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
from langchain_core.output_parsers import StrOutputParser

# Schema description for the LLM (manually defined since APOC is not available)
SCHEMA_DESCRIPTION = """
Node Labels and Properties:
- ResearchProject: rp_id (may be None), research_project_title, contact_person_and_email,
  data_description, data_gathering_begin_date, data_gathering_end_date, data_gathering_site,
  human_subjects, instruments, keywords, research_problem_question, study_area, team_members,
  will_this_data_be_published, associated_publication_title, data_availability_for_internal_sharing,
  data_organization_description_for_accessibility, date_of_publication,
  location_of_data_when_available_for_internal_sharing, publisher_or_event
- ResearchMethod: rm_id, name, method_details, type_s
- ExperimentInstrument: ei_id, Survey, Code_book
- HumanSubject (also labeled HumanSubjects in some projects): hs_id, Age, Gender, Ethnicity,
  How_many_participants_are_included, Regional_Distribution, Recruitment_mode,
  IRB_Number_and_resolution, Protected_Data
- ExperimentSetting: es_id, Format, Geographical_location, Environment_description, Conditions, Tasks
- Sessions (also labeled Session in some projects): s_id, Sessions, Number_of_sessions,
  Trials_per_session, Duration_of_trials, Subjects_per_session
- Dataset: d_id, name, url
- HumanData (also labeled HumanDataset, Human_Dataset in some projects): hd_id
- Robot (also labeled Robots in some projects): r_id, Robot_type, Model, Robot_Model_URL,
  Hardware_instrumentation, Software_instrumentation, Indicate_if_adaptations_were_made,
  Implementation, Size, Motion_replay
- RobotData (also labeled RobotDataset, Robot_Dataset, robotdata in some projects): rd_id
- DocumentChunk: text, embedding, source_file, chunk_index (RAG report chunks)
- ProjectReports: source_file (groups DocumentChunks per project)
- Problem: (GCR-specific qualitative research problems/themes)
- Analysis: (GCR-specific analysis node)
- Other project-specific nodes: AnnotationData, AnnotationFile, Video, videos, images, masks,
  SensorData, RosBag, IMU, FrontCamera2D, Lidar3D, RoomGeometry, Location, ObjectClass,
  Questionnaire, ComfortQuestionnaire, InterviewSchedule, Trial, Quote, InductiveTheme,
  DeductiveLabel, AnalysisResult, Conditions

Relationships:
IMPORTANT: Relationship names are INCONSISTENT across projects. When writing Cypher queries,
use UNION or multiple OPTIONAL MATCH clauses to try ALL variants for a given relationship.

ResearchProject → ResearchMethod:
  - [:HAS_METHOD] (canonical, used by newer projects like EgoNRG, CODa Re-ID)
  - [:Has_ResearchMethod] (used by most older projects)
  - [:Type] (used by GCR projects)
  Always try all three when querying research methods.

ResearchProject → Dataset:
  - [:HAS_DATASET] (canonical, newer projects)
  - [:Generates] (most older projects)
  Always try both when querying datasets.

ResearchProject → Robot:
  - [:USES_ROBOT] (canonical, newer projects)
  - [:Experiment_Robots] (older projects, may point to Robot or Robots label)
  Always try both when querying robots.

ResearchProject → Reports (RAG):
  - (ResearchProject)-[:HAS_REPORTS]->(ProjectReports)-[:CONTAINS_CHUNK]->(DocumentChunk)

ResearchProject → Qualitative (GCR-specific):
  - [:Has_Problem] or [:Has] → (Problem)
  - [:Type] → (Analysis)

ResearchMethod relationships:
  - [:Has_questionnaires] → (ExperimentInstrument)
  - [:Session_HumanSubject] or [:Session_HumanSubjects] → (HumanSubject or HumanSubjects)
  - [:Has_Settings] → (ExperimentSetting)
  - [:Has_Sessions] → (Sessions or Session)

Dataset relationships:
  - [:Has_HumanData] or [:Dataset_Human] or [:Dataset_HumanDataset] → (HumanData or HumanDataset)
  - [:Has_RobotData] or [:Dataset_Robot] or [:Dataset_RobotDataset] → (RobotData or RobotDataset)
  - [:Dataset_RosBag] → (RosBag)
  - [:Dataset_IMU] → (IMU)
  - [:Dataset_video] or [:Dataset_Video] or [:Has_Video] → (video or Video or videos)
  - [:Dataset_FrontCamera] → (FrontCamera2D)
  - [:Dataset_Lidar3D] → (Lidar3D)
  - [:Contains] → (various sensor/data nodes)

QUERY TIPS:
- Always use toLower() and CONTAINS for text matching (property names and values have inconsistent casing).
- When searching for a project by title, use: WHERE toLower(rp.research_project_title) CONTAINS toLower("search term")
- For broad queries, use OPTIONAL MATCH with multiple relationship variants to capture all data.
- Return specific properties, not entire nodes.
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

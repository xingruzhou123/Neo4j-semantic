"""
Script to create a Neo4j graph structure from paper JSON data.
Creates a family-tree style graph with ResearchProject as the main node
and child nodes for ResearchMethod, Robot (if applicable), and Dataset.
ResearchMethod has additional child nodes: ExperimentInstrument, HumanSubject,
ExperimentSetting, and Sessions.
"""

import json
import re
from neo4j import GraphDatabase

# Neo4j connection settings
URI = "bolt://localhost:7687"
USERNAME = "neo4j"
PASSWORD = "12345678"


def clean_text(text: str) -> str:
    """Remove HTML tags and clean up text."""
    if not text:
        return ""
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    # Strip leading/trailing whitespace
    text = text.strip()
    return text


def clean_list_to_string(items: list) -> str:
    """Convert a list to a clean comma-separated string."""
    if not items:
        return ""
    cleaned = [clean_text(str(item)) for item in items]
    return ", ".join(cleaned)


def load_json_file(file_path: str) -> dict:
    """Load and parse the JSON file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def extract_field_value(fields: list, type_name: str):
    """Extract a field value from the metadata fields list."""
    for field in fields:
        if field.get('typeName') == type_name:
            return field.get('value')
    return None


def get_next_id(session, label: str, id_field: str) -> int:
    """Get the next sequential ID for a given label by finding max existing ID."""
    result = session.run(f"""
        MATCH (n:{label})
        RETURN COALESCE(MAX(n.{id_field}), 0) AS max_id
    """)
    record = result.single()
    return record["max_id"] + 1


def extract_research_project_data(data: dict) -> dict:
    """Extract data for the ResearchProject node from JSON."""
    metadata_blocks = data.get('datasetVersion', {}).get('metadataBlocks', {})
    citation_fields = metadata_blocks.get('citation', {}).get('fields', [])
    social_science_fields = metadata_blocks.get('socialscience', {}).get('fields', [])

    # Extract contact person and email
    contacts = extract_field_value(citation_fields, 'datasetContact')
    contact_info = ""
    if contacts and len(contacts) > 0:
        contact = contacts[0]
        name = contact.get('datasetContactName', {}).get('value', '')
        email = contact.get('datasetContactEmail', {}).get('value', '')
        contact_info = f"{name} ({email})" if name and email else name or email

    # Extract description
    descriptions = extract_field_value(citation_fields, 'dsDescription')
    description = ""
    if descriptions and len(descriptions) > 0:
        description = descriptions[0].get('dsDescriptionValue', {}).get('value', '')

    # Extract date of collection
    date_collection = extract_field_value(citation_fields, 'dateOfCollection')
    begin_date = ""
    end_date = ""
    if date_collection and len(date_collection) > 0:
        begin_date = date_collection[0].get('dateOfCollectionStart', {}).get('value', '')
        end_date = date_collection[0].get('dateOfCollectionEnd', {}).get('value', '')

    # Extract production place (data gathering site)
    production_place = extract_field_value(citation_fields, 'productionPlace')
    site = production_place[0] if production_place else ""

    # Extract keywords
    keywords_data = extract_field_value(citation_fields, 'keyword')
    keywords = []
    if keywords_data:
        for kw in keywords_data:
            kw_value = kw.get('keywordValue', {}).get('value', '')
            if kw_value:
                keywords.append(kw_value)

    # Extract title
    title = extract_field_value(citation_fields, 'title') or ""

    # Extract subject/study area
    subjects = extract_field_value(citation_fields, 'subject')
    study_area = subjects[0] if subjects else ""

    # Extract authors (team members)
    authors_data = extract_field_value(citation_fields, 'author')
    team_members = []
    if authors_data:
        for author in authors_data:
            name = author.get('authorName', {}).get('value', '')
            affiliation = author.get('authorAffiliation', {}).get('value', '')
            if name:
                team_members.append(f"{name} ({affiliation})" if affiliation else name)

    # Extract research instrument
    instruments = extract_field_value(social_science_fields, 'researchInstrument') or ""

    # Extract universe (human subjects info)
    universe = extract_field_value(social_science_fields, 'universe')
    human_subjects = universe[0] if universe else ""

    # Check if data is published
    publication_date = data.get('publicationDate', '')
    will_be_published = "Yes" if publication_date else "No"

    # Extract research problem/question from description
    research_problem = ""
    if description:
        if "Interview" in description or "interview" in description:
            research_problem = "Understanding human expectations and reactions to robots in public spaces through discursive accounts of imagined encounters."

    return {
        'rp_id': None,  # Will be set by get_next_id
        'research_project_title': clean_text(title) or "N/A",
        'contact_person_and_email': clean_text(contact_info) or "N/A",
        'data_description': clean_text(description) or "N/A",
        'data_gathering_begin_date': clean_text(begin_date) or "N/A",
        'data_gathering_end_date': clean_text(end_date) or "N/A",
        'data_gathering_site': clean_text(site) or "N/A",
        'human_subjects': clean_text(human_subjects) or "N/A",
        'instruments': clean_text(instruments) or "N/A",
        'keywords': clean_list_to_string(keywords) or "N/A",
        'research_problem_question': clean_text(research_problem) or "N/A",
        'study_area': clean_text(study_area) or "N/A",
        'team_members': clean_list_to_string(team_members) or "N/A",
        'will_this_data_be_published': clean_text(will_be_published) or "N/A"
    }


def extract_research_method(data: dict) -> dict:
    """Extract research method information from JSON."""
    metadata_blocks = data.get('datasetVersion', {}).get('metadataBlocks', {})
    citation_fields = metadata_blocks.get('citation', {}).get('fields', [])

    # Get description to find research method
    descriptions = extract_field_value(citation_fields, 'dsDescription')
    method_name = "ResearchMethod"
    method_details = ""
    type_s = ""

    if descriptions and len(descriptions) > 0:
        desc = descriptions[0].get('dsDescriptionValue', {}).get('value', '')
        # Look for research method mentions
        if "Grounded Theory" in desc:
            method_details = "Constructivist Grounded Theory / Socio-technical Grounded Theory"
        # Extract type_s if explicitly stated (e.g., qualitative, quantitative, mixed)
        desc_lower = desc.lower()
        if "qualitative" in desc_lower:
            type_s = "Qualitative"
        elif "quantitative" in desc_lower:
            type_s = "Quantitative"
        elif "mixed" in desc_lower:
            type_s = "Mixed Methods"

    return {
        'rm_id': None,  # Will be set by get_next_id
        'name': method_name,
        'method_details': method_details or "N/A",
        'type_s': type_s or "N/A"
    }


def extract_experiment_instrument(data: dict) -> dict:
    """Extract experiment instrument information from JSON."""
    metadata_blocks = data.get('datasetVersion', {}).get('metadataBlocks', {})
    social_science_fields = metadata_blocks.get('socialscience', {}).get('fields', [])

    # Extract research instrument for Survey
    research_instrument = extract_field_value(social_science_fields, 'researchInstrument') or ""

    # Look for questionnaire/survey in files
    files = data.get('datasetVersion', {}).get('files', [])
    survey = ""
    code_book = ""
    for f in files:
        desc = f.get('description', '').lower()
        filename = f.get('label', '').lower()
        if 'questionnaire' in desc or 'questionnaire' in filename or 'protocol' in filename:
            survey = f.get('label', '')
        if 'codebook' in desc or 'code_book' in filename or 'codebook' in filename:
            code_book = f.get('label', '')

    # If no specific survey file found, use research instrument
    if not survey and research_instrument:
        survey = research_instrument

    return {
        'ei_id': None,  # Will be set by get_next_id
        'Survey': clean_text(survey) or "N/A",
        'Code_book': clean_text(code_book) or "N/A"
    }


def extract_human_subject(data: dict) -> dict:
    """Extract human subject information from JSON."""
    metadata_blocks = data.get('datasetVersion', {}).get('metadataBlocks', {})
    social_science_fields = metadata_blocks.get('socialscience', {}).get('fields', [])
    citation_fields = metadata_blocks.get('citation', {}).get('fields', [])

    # Extract description to find participant count
    descriptions = extract_field_value(citation_fields, 'dsDescription')
    description = ""
    participant_count = ""
    if descriptions and len(descriptions) > 0:
        description = descriptions[0].get('dsDescriptionValue', {}).get('value', '')
        # Look for participant count in description
        import re
        match = re.search(r'(\d+)\s*participants', description, re.IGNORECASE)
        if match:
            participant_count = match.group(1)

    # Extract collection mode for recruitment
    collection_mode = extract_field_value(social_science_fields, 'collectionMode')
    recruitment_mode = collection_mode[0] if collection_mode else ""

    # Extract data collection situation
    data_collection_situation = extract_field_value(social_science_fields, 'dataCollectionSituation') or ""

    # Extract production place for regional distribution
    production_place = extract_field_value(citation_fields, 'productionPlace')
    regional_distribution = production_place[0] if production_place else ""

    return {
        'hs_id': None,  # Will be set by get_next_id
        'Age': "N/A",
        'Gender': "N/A",
        'Ethnicity': "N/A",
        'How_many_participants_are_included': clean_text(participant_count) or "N/A",
        'Regional_Distribution': clean_text(regional_distribution) or "N/A",
        'Recruitment_mode': clean_text(recruitment_mode if recruitment_mode else data_collection_situation) or "N/A",
        'IRB_Number_and_resolution': "N/A",
        'Protected_Data': "Yes" if "privacy" in description.lower() or "anonymized" in description.lower() else "N/A"
    }


def extract_experiment_setting(data: dict) -> dict:
    """Extract experiment setting information from JSON."""
    metadata_blocks = data.get('datasetVersion', {}).get('metadataBlocks', {})
    social_science_fields = metadata_blocks.get('socialscience', {}).get('fields', [])
    citation_fields = metadata_blocks.get('citation', {}).get('fields', [])

    # Extract production place for geographical location
    production_place = extract_field_value(citation_fields, 'productionPlace')
    geographical_location = production_place[0] if production_place else ""

    # Extract collection mode for format
    collection_mode = extract_field_value(social_science_fields, 'collectionMode')
    format_val = collection_mode[0] if collection_mode else ""

    # Extract data collection situation for environment description
    data_collection_situation = extract_field_value(social_science_fields, 'dataCollectionSituation') or ""

    # Extract description for conditions and tasks
    descriptions = extract_field_value(citation_fields, 'dsDescription')
    conditions = ""
    tasks = ""
    if descriptions and len(descriptions) > 0:
        desc = descriptions[0].get('dsDescriptionValue', {}).get('value', '')
        # Look for setting-related info
        if "pedestrian area" in desc.lower():
            conditions = "Public pedestrian area on university campus"
        if "interview" in desc.lower():
            tasks = "Semi-structured interviews about imagined robot encounters"

    return {
        'es_id': None,  # Will be set by get_next_id
        'Format': clean_text(format_val) or "N/A",
        'Geographical_location': clean_text(geographical_location) or "N/A",
        'Environment_description': clean_text(data_collection_situation) or "N/A",
        'Conditions': clean_text(conditions) or "N/A",
        'Tasks': clean_text(tasks) or "N/A"
    }


def extract_sessions(data: dict) -> dict:
    """Extract session information from JSON."""
    metadata_blocks = data.get('datasetVersion', {}).get('metadataBlocks', {})
    social_science_fields = metadata_blocks.get('socialscience', {}).get('fields', [])
    citation_fields = metadata_blocks.get('citation', {}).get('fields', [])

    # Extract time method for duration
    time_method = extract_field_value(social_science_fields, 'timeMethod') or ""

    # Extract frequency of data collection
    frequency = extract_field_value(social_science_fields, 'frequencyOfDataCollection') or ""

    # Extract description for session details
    descriptions = extract_field_value(citation_fields, 'dsDescription')
    duration_of_trials = ""
    if descriptions and len(descriptions) > 0:
        desc = descriptions[0].get('dsDescriptionValue', {}).get('value', '')
        # Look for duration info
        import re
        match = re.search(r'(\d+)\s*(?:to|and|-)\s*(\d+)\s*minutes', desc, re.IGNORECASE)
        if match:
            duration_of_trials = f"{match.group(1)}-{match.group(2)} minutes"
        else:
            match = re.search(r'(\d+)\s*minutes', desc, re.IGNORECASE)
            if match:
                duration_of_trials = f"{match.group(1)} minutes"

    # If no duration found in description, use time_method
    if not duration_of_trials and time_method:
        duration_of_trials = time_method

    return {
        's_id': None,  # Will be set by get_next_id
        'Sessions': clean_text(frequency) or "N/A",
        'Number_of_sessions': "N/A",
        'Trials_per_session': "N/A",
        'Duration_of_trials': clean_text(duration_of_trials) or "N/A",
        'Subjects_per_session': "N/A"
    }


def check_robot_presence(data: dict) -> dict:
    """
    Check if the JSON indicates presence of a robot.
    Returns robot data if present, None otherwise.
    """
    metadata_blocks = data.get('datasetVersion', {}).get('metadataBlocks', {})
    citation_fields = metadata_blocks.get('citation', {}).get('fields', [])

    title = extract_field_value(citation_fields, 'title') or ""
    descriptions = extract_field_value(citation_fields, 'dsDescription')
    description = ""
    if descriptions and len(descriptions) > 0:
        description = descriptions[0].get('dsDescriptionValue', {}).get('value', '')

    # Check for indicators that NO robot was used
    if "Non-Robot" in title or "non-robot" in title.lower():
        return None

    if "Pre-Deployment" in title and "deployed" not in description.lower():
        return None

    # Look for actual robot names or deployment mentions
    robot_indicators = ['deployed robot', 'robot deployment', 'using robot', 'robot named',
                        'the robot', 'our robot', 'robot was used']

    robot_present = False
    for indicator in robot_indicators:
        if indicator in description.lower():
            robot_present = True
            break

    if not robot_present:
        return None

    # Robot is present - extract properties or set to N/A
    return {
        'r_id': None,  # Will be set by get_next_id
        'Robot_type': "N/A",
        'Model': "N/A",
        'Robot_Model_URL': "N/A",
        'Hardware_instrumentation': "N/A",
        'Software_instrumentation': "N/A",
        'Indicate_if_adaptations_were_made': "N/A",
        'Implementation': "N/A",
        'Size': "N/A",
        'Motion_replay': "N/A"
    }


def extract_dataset_info(data: dict) -> dict:
    """Extract dataset information including URL."""
    # Get the persistent URL
    url = data.get('persistentUrl', '')

    return {
        'd_id': None,  # Will be set by get_next_id
        'name': 'Dataset',
        'url': clean_text(url) or "N/A"
    }


def check_human_data_presence(data: dict) -> bool:
    """Check if the dataset contains human data."""
    metadata_blocks = data.get('datasetVersion', {}).get('metadataBlocks', {})
    social_science_fields = metadata_blocks.get('socialscience', {}).get('fields', [])
    citation_fields = metadata_blocks.get('citation', {}).get('fields', [])

    # Check for human subjects indicators
    universe = extract_field_value(social_science_fields, 'universe')
    if universe:
        return True

    # Check description for human participant mentions
    descriptions = extract_field_value(citation_fields, 'dsDescription')
    if descriptions and len(descriptions) > 0:
        desc = descriptions[0].get('dsDescriptionValue', {}).get('value', '').lower()
        human_indicators = ['participant', 'interview', 'survey', 'human subject', 'respondent']
        for indicator in human_indicators:
            if indicator in desc:
                return True

    return False


def check_robot_data_presence(data: dict) -> bool:
    """Check if the dataset contains robot data."""
    metadata_blocks = data.get('datasetVersion', {}).get('metadataBlocks', {})
    citation_fields = metadata_blocks.get('citation', {}).get('fields', [])

    title = extract_field_value(citation_fields, 'title') or ""

    # Explicit non-robot indicator
    if "Non-Robot" in title or "non-robot" in title.lower():
        return False

    descriptions = extract_field_value(citation_fields, 'dsDescription')
    if descriptions and len(descriptions) > 0:
        desc = descriptions[0].get('dsDescriptionValue', {}).get('value', '').lower()
        robot_data_indicators = ['robot data', 'robot log', 'sensor data', 'robot sensor',
                                  'robot recording', 'robot trajectory']
        for indicator in robot_data_indicators:
            if indicator in desc:
                return True

    # Check files for robot data
    files = data.get('datasetVersion', {}).get('files', [])
    for f in files:
        filename = f.get('label', '').lower()
        desc = f.get('description', '').lower()
        if 'robot' in filename or 'sensor' in filename or 'robot' in desc:
            return True

    return False


def extract_human_data_sessions(data: dict) -> list:
    """
    Extract human data session information from JSON.
    Returns list of session data with paths if explicitly present.
    """
    sessions = []
    files = data.get('datasetVersion', {}).get('files', [])

    # Look for files that contain human/participant data
    session_index = 1
    for f in files:
        filename = f.get('label', '')
        desc = f.get('description', '').lower()
        data_file = f.get('dataFile', {})
        # Use pidURL (persistent URL) as the real accessible path
        pid_url = data_file.get('pidURL', '')

        # Check if this file contains human subject data
        human_data_indicators = ['interview', 'survey', 'response', 'participant',
                                  'questionnaire', 'dataset', 'data']
        is_human_data = any(ind in desc or ind in filename.lower() for ind in human_data_indicators)

        # Exclude protocol/methodology files
        exclude_indicators = ['protocol', 'poster', 'publication', 'readme']
        is_excluded = any(ind in desc or ind in filename.lower() for ind in exclude_indicators)

        if is_human_data and not is_excluded:
            # Use pidURL as the real data path, fallback to filename
            data_path = pid_url if pid_url else filename
            sessions.append({
                'session_index': session_index,
                'data_file_path': clean_text(data_path) or "N/A"
            })
            session_index += 1

    return sessions


def extract_robot_data_sessions(data: dict) -> list:
    """
    Extract robot data session information from JSON.
    Returns list of session data with paths if explicitly present.
    """
    sessions = []
    files = data.get('datasetVersion', {}).get('files', [])

    # Look for files that contain robot data
    session_index = 1
    for f in files:
        filename = f.get('label', '')
        desc = f.get('description', '').lower()
        data_file = f.get('dataFile', {})
        # Use pidURL (persistent URL) as the real accessible path
        pid_url = data_file.get('pidURL', '')

        # Check if this file contains robot data
        robot_data_indicators = ['robot', 'sensor', 'trajectory', 'log', 'motion']
        is_robot_data = any(ind in desc or ind in filename.lower() for ind in robot_data_indicators)

        if is_robot_data:
            # Use pidURL as the real data path, fallback to filename
            data_path = pid_url if pid_url else filename
            sessions.append({
                'session_index': session_index,
                'data_file_path': clean_text(data_path) or "N/A"
            })
            session_index += 1

    return sessions


def create_graph(driver, json_data: dict):
    """Create the Neo4j graph structure."""

    # Extract all data
    rp_data = extract_research_project_data(json_data)
    rm_data = extract_research_method(json_data)
    ei_data = extract_experiment_instrument(json_data)
    hs_data = extract_human_subject(json_data)
    es_data = extract_experiment_setting(json_data)
    sessions_data = extract_sessions(json_data)
    robot_data = check_robot_presence(json_data)
    dataset_data = extract_dataset_info(json_data)

    with driver.session() as session:
        # Get next sequential IDs for each label
        rp_data['rp_id'] = get_next_id(session, 'ResearchProject', 'rp_id')
        rm_data['rm_id'] = get_next_id(session, 'ResearchMethod', 'rm_id')
        ei_data['ei_id'] = get_next_id(session, 'ExperimentInstrument', 'ei_id')
        hs_data['hs_id'] = get_next_id(session, 'HumanSubject', 'hs_id')
        es_data['es_id'] = get_next_id(session, 'ExperimentSetting', 'es_id')
        sessions_data['s_id'] = get_next_id(session, 'Sessions', 's_id')
        dataset_data['d_id'] = get_next_id(session, 'Dataset', 'd_id')
        if robot_data:
            robot_data['r_id'] = get_next_id(session, 'Robot', 'r_id')

        # Create ResearchProject node
        session.run("""
            CREATE (rp:ResearchProject {
                rp_id: $rp_id,
                research_project_title: $research_project_title,
                contact_person_and_email: $contact_person_and_email,
                data_description: $data_description,
                data_gathering_begin_date: $data_gathering_begin_date,
                data_gathering_end_date: $data_gathering_end_date,
                data_gathering_site: $data_gathering_site,
                human_subjects: $human_subjects,
                instruments: $instruments,
                keywords: $keywords,
                research_problem_question: $research_problem_question,
                study_area: $study_area,
                team_members: $team_members,
                will_this_data_be_published: $will_this_data_be_published
            })
            """, **rp_data)
        print(f"Created ResearchProject node (rp_id={rp_data['rp_id']}): {rp_data['research_project_title']}")

        # Create ResearchMethod node and relationship
        session.run("""
            MATCH (rp:ResearchProject {rp_id: $rp_id})
            CREATE (rm:ResearchMethod {
                rm_id: $rm_id,
                name: $name,
                method_details: $method_details,
                type_s: $type_s
            })
            CREATE (rp)-[:HAS_METHOD]->(rm)
            """, rp_id=rp_data['rp_id'], **rm_data)
        print(f"Created ResearchMethod node (rm_id={rm_data['rm_id']}): {rm_data['method_details']}")

        # Create ExperimentInstrument node and relationship (child of ResearchMethod)
        session.run("""
            MATCH (rm:ResearchMethod {rm_id: $rm_id})
            CREATE (ei:ExperimentInstrument {
                ei_id: $ei_id,
                Survey: $Survey,
                Code_book: $Code_book
            })
            CREATE (rm)-[:Has_questionnaires]->(ei)
            """, rm_id=rm_data['rm_id'], **ei_data)
        print(f"Created ExperimentInstrument node (ei_id={ei_data['ei_id']})")

        # Create HumanSubject node and relationship (child of ResearchMethod)
        session.run("""
            MATCH (rm:ResearchMethod {rm_id: $rm_id})
            CREATE (hs:HumanSubject {
                hs_id: $hs_id,
                Age: $Age,
                Gender: $Gender,
                Ethnicity: $Ethnicity,
                How_many_participants_are_included: $How_many_participants_are_included,
                Regional_Distribution: $Regional_Distribution,
                Recruitment_mode: $Recruitment_mode,
                IRB_Number_and_resolution: $IRB_Number_and_resolution,
                Protected_Data: $Protected_Data
            })
            CREATE (rm)-[:Session_HumanSubject]->(hs)
            """, rm_id=rm_data['rm_id'], **hs_data)
        print(f"Created HumanSubject node (hs_id={hs_data['hs_id']})")

        # Create ExperimentSetting node and relationship (child of ResearchMethod)
        session.run("""
            MATCH (rm:ResearchMethod {rm_id: $rm_id})
            CREATE (es:ExperimentSetting {
                es_id: $es_id,
                Format: $Format,
                Geographical_location: $Geographical_location,
                Environment_description: $Environment_description,
                Conditions: $Conditions,
                Tasks: $Tasks
            })
            CREATE (rm)-[:Has_Settings]->(es)
            """, rm_id=rm_data['rm_id'], **es_data)
        print(f"Created ExperimentSetting node (es_id={es_data['es_id']})")

        # Create Sessions node and relationship (child of ResearchMethod)
        session.run("""
            MATCH (rm:ResearchMethod {rm_id: $rm_id})
            CREATE (s:Sessions {
                s_id: $s_id,
                Sessions: $Sessions,
                Number_of_sessions: $Number_of_sessions,
                Trials_per_session: $Trials_per_session,
                Duration_of_trials: $Duration_of_trials,
                Subjects_per_session: $Subjects_per_session
            })
            CREATE (rm)-[:Has_Sessions]->(s)
            """, rm_id=rm_data['rm_id'], **sessions_data)
        print(f"Created Sessions node (s_id={sessions_data['s_id']})")

        # Create Robot node if applicable (child of ResearchProject)
        if robot_data:
            session.run("""
                MATCH (rp:ResearchProject {rp_id: $rp_id})
                CREATE (r:Robot {
                    r_id: $r_id,
                    Robot_type: $Robot_type,
                    Model: $Model,
                    Robot_Model_URL: $Robot_Model_URL,
                    Hardware_instrumentation: $Hardware_instrumentation,
                    Software_instrumentation: $Software_instrumentation,
                    Indicate_if_adaptations_were_made: $Indicate_if_adaptations_were_made,
                    Implementation: $Implementation,
                    Size: $Size,
                    Motion_replay: $Motion_replay
                })
                CREATE (rp)-[:USES_ROBOT]->(r)
                """, rp_id=rp_data['rp_id'], **robot_data)
            print(f"Created Robot node (r_id={robot_data['r_id']})")
        else:
            print("No Robot node created (not indicated in JSON)")

        # Create Dataset node and relationship (child of ResearchProject)
        session.run("""
            MATCH (rp:ResearchProject {rp_id: $rp_id})
            CREATE (d:Dataset {
                d_id: $d_id,
                name: $name,
                url: $url
            })
            CREATE (rp)-[:HAS_DATASET]->(d)
            """, rp_id=rp_data['rp_id'], **dataset_data)
        print(f"Created Dataset node (d_id={dataset_data['d_id']}): {dataset_data['url']}")

        # Check for HumanData and RobotData presence
        has_human_data = check_human_data_presence(json_data)
        has_robot_data = check_robot_data_presence(json_data)
        human_sessions = extract_human_data_sessions(json_data)
        robot_sessions = extract_robot_data_sessions(json_data)

        # Create HumanData node if human data is present
        hd_id = None
        if has_human_data:
            hd_id = get_next_id(session, 'HumanData', 'hd_id')
            session.run("""
                MATCH (d:Dataset {d_id: $d_id})
                CREATE (hd:HumanData {hd_id: $hd_id})
                CREATE (d)-[:Has_HumanData]->(hd)
                """, d_id=dataset_data['d_id'], hd_id=hd_id)
            print(f"Created HumanData node (hd_id={hd_id})")

            # Create HumanData_session nodes if session data is present
            for sess in human_sessions:
                hds_id = get_next_id(session, 'HumanData_session', 'hds_id')
                prop_name = f"session{sess['session_index']}_data_file_path"
                session.run(f"""
                    MATCH (hd:HumanData {{hd_id: $hd_id}})
                    CREATE (hds:HumanData_session {{
                        hds_id: $hds_id,
                        {prop_name}: $data_path
                    }})
                    CREATE (hd)-[:Has_Session_Data]->(hds)
                    """, hd_id=hd_id, hds_id=hds_id, data_path=sess['data_file_path'])
                print(f"Created HumanData_session node (hds_id={hds_id}): session{sess['session_index']}")
        else:
            print("No HumanData node created (not indicated in JSON)")

        # Create RobotData node if robot data is present
        rd_id = None
        if has_robot_data:
            rd_id = get_next_id(session, 'RobotData', 'rd_id')
            session.run("""
                MATCH (d:Dataset {d_id: $d_id})
                CREATE (rd:RobotData {rd_id: $rd_id})
                CREATE (d)-[:Has_RobotData]->(rd)
                """, d_id=dataset_data['d_id'], rd_id=rd_id)
            print(f"Created RobotData node (rd_id={rd_id})")

            # Create RobotData_session nodes if session data is present
            for sess in robot_sessions:
                rds_id = get_next_id(session, 'RobotData_session', 'rds_id')
                prop_name = f"session{sess['session_index']}_data_file_path"
                session.run(f"""
                    MATCH (rd:RobotData {{rd_id: $rd_id}})
                    CREATE (rds:RobotData_session {{
                        rds_id: $rds_id,
                        {prop_name}: $data_path
                    }})
                    CREATE (rd)-[:Has_Session_Data]->(rds)
                    """, rd_id=rd_id, rds_id=rds_id, data_path=sess['data_file_path'])
                print(f"Created RobotData_session node (rds_id={rds_id}): session{sess['session_index']}")
        else:
            print("No RobotData node created (not indicated in JSON)")

        # Create Aligned_Session relationships between matching session indices
        if human_sessions and robot_sessions:
            # Find matching session indices
            human_indices = {s['session_index'] for s in human_sessions}
            robot_indices = {s['session_index'] for s in robot_sessions}
            common_indices = human_indices.intersection(robot_indices)

            for idx in common_indices:
                session.run("""
                    MATCH (hds:HumanData_session)
                    WHERE hds.hds_id IN [(hd:HumanData {hd_id: $hd_id})-[:Has_Session_Data]->(s) | s.hds_id]
                    MATCH (rds:RobotData_session)
                    WHERE rds.rds_id IN [(rd:RobotData {rd_id: $rd_id})-[:Has_Session_Data]->(s) | s.rds_id]
                    CREATE (hds)-[:Aligned_Session]->(rds)
                    CREATE (rds)-[:Aligned_Session]->(hds)
                    """, hd_id=hd_id, rd_id=rd_id)
                print(f"Created Aligned_Session relationship for session{idx}")


def main():
    # Path to the JSON file
    json_file_path = "/Users/xingruzhou/Documents/Project/TACC/origin_Data/paper1.json"

    # Load JSON data
    print(f"Loading JSON from: {json_file_path}")
    json_data = load_json_file(json_file_path)

    # Connect to Neo4j
    driver = GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))

    try:
        driver.verify_connectivity()
        print("Connected to Neo4j successfully!")

        # Create the graph
        create_graph(driver, json_data)
        print("\nGraph creation completed successfully!")

    except Exception as e:
        print(f"Error: {e}")
        raise
    finally:
        driver.close()


if __name__ == "__main__":
    main()

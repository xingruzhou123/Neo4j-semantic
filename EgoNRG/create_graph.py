"""
Script to build a knowledge graph from EgoNRG metadata.json in target.json format.

Relationship and property names align with the graph schema (e.g. graph.svg):
  Has_ResearchMethod, Experiment_Robots, Generates, Has_Sessions, Has_Settings,
  Has_ExperimentInstrument, Session_HumanSubject, Dataset_Human, Dataset_Robot,
  Contains (for dataset hierarchy).

Dataset hierarchy: (Dataset)-[Dataset_Indoor]->(HumanDataset Indoor),
[Dataset_Outdoor]->(HumanDataset Outdoor); each points to HumanDataset People
and No_People; each of those points to HumanDataset Covered and Uncovered.
All hierarchy nodes use url = EgoNRG dataset page (dataverse.tdl.org).

Primary output: writes a JSON file (default EgoNRG/output.json) with the same
structure as EgoNRG/target.json: an array of nodes, each with
  { "m": { "identity", "labels", "properties", "elementId" } }.
Includes hierarchy nodes (DataType, Environment, PeoplePresence, Clothing)
and video nodes with directory_path.

Usage:
  python create_metadata_graph.py [metadata.json] [-o output.json] [--neo4j]
With --neo4j, also creates the graph in Neo4j (requires neo4j package).
"""

import json
import re
import uuid
from pathlib import Path

try:
    from neo4j import GraphDatabase
except ImportError:
    GraphDatabase = None

# Default link for all dataset hierarchy nodes (EgoNRG dataset page)
DATASET_PAGE_URL = "https://dataverse.tdl.org/dataset.xhtml?persistentId=doi:10.18738/T8/DC4J0Q"

# Neo4j connection settings
URI = "bolt://localhost:7688"
USERNAME = "neo4j"
PASSWORD = "12345678"


def clean_text(text: str) -> str:
    """Remove HTML tags and clean up text."""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


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
    if not fields:
        return None
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


def format_filesize(size_bytes: int) -> str:
    """Format filesize in human-readable form."""
    if size_bytes is None or size_bytes < 0:
        return "N/A"
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def parse_directory_path(directory_label: str) -> dict:
    """
    Parse EgoNRG directory structure: data/{type}/{env}/{people}/{clothing}
    Returns dict with data_type, environment, people_presence, clothing.
    """
    parts = {}
    if not directory_label:
        return parts
    segments = [p for p in directory_label.split('/') if p]
    if len(segments) >= 2:
        parts['data_type'] = segments[1]  # images | masks
    if len(segments) >= 3:
        parts['environment'] = segments[2]  # Indoor | Outdoor
    if len(segments) >= 4:
        parts['people_presence'] = segments[3]  # People | No_People
    if len(segments) >= 5:
        parts['clothing'] = segments[4]  # Covered | Uncovered
    return parts


def extract_research_project_data(data: dict) -> dict:
    """Extract data for the ResearchProject node from JSON."""
    metadata_blocks = data.get('datasetVersion', {}).get('metadataBlocks', {})
    citation_fields = metadata_blocks.get('citation', {}).get('fields', [])
    social_science_fields = metadata_blocks.get('socialscience', {}).get('fields', [])

    contacts = extract_field_value(citation_fields, 'datasetContact')
    contact_info = ""
    if contacts and len(contacts) > 0:
        contact = contacts[0]
        name = contact.get('datasetContactName', {}).get('value', '')
        email = contact.get('datasetContactEmail', {}).get('value', '')
        contact_info = f"{name} ({email})" if name and email else name or email

    descriptions = extract_field_value(citation_fields, 'dsDescription')
    description = ""
    if descriptions and len(descriptions) > 0:
        description = descriptions[0].get('dsDescriptionValue', {}).get('value', '')

    date_collection = extract_field_value(citation_fields, 'dateOfCollection')
    begin_date = end_date = ""
    if date_collection and len(date_collection) > 0:
        begin_date = date_collection[0].get('dateOfCollectionStart', {}).get('value', '')
        end_date = date_collection[0].get('dateOfCollectionEnd', {}).get('value', '')

    production_place = extract_field_value(citation_fields, 'productionPlace')
    site = production_place[0] if production_place else ""

    keywords_data = extract_field_value(citation_fields, 'keyword')
    keywords = []
    if keywords_data:
        for kw in keywords_data:
            kw_value = kw.get('keywordValue', {}).get('value', '') if isinstance(kw, dict) else str(kw)
            if kw_value:
                keywords.append(kw_value)

    title = extract_field_value(citation_fields, 'title') or ""
    subjects = extract_field_value(citation_fields, 'subject')
    study_area = subjects[0] if subjects else ""

    authors_data = extract_field_value(citation_fields, 'author')
    team_members = []
    if authors_data:
        for author in authors_data:
            if isinstance(author, dict):
                name = author.get('authorName', {}).get('value', '')
                affiliation = author.get('authorAffiliation', {}).get('value', '')
                expanded = author.get('authorAffiliation', {}).get('expandedvalue', {})
                if isinstance(expanded, dict) and 'termName' in expanded:
                    affiliation = expanded.get('termName', affiliation)
                if name:
                    team_members.append(f"{name} ({affiliation})" if affiliation else name)

    instruments = extract_field_value(social_science_fields, 'researchInstrument') or ""
    universe = extract_field_value(social_science_fields, 'universe')
    human_subjects = universe[0] if universe else ""
    publication_date = data.get('publicationDate', '')
    will_be_published = "Yes" if publication_date else "No"
    research_problem = ""

    return {
        # 'rp_id': None,
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
        'study_area': clean_list_to_string(study_area) if isinstance(study_area, list) else (clean_text(study_area) or "N/A"),
        'team_members': clean_list_to_string(team_members) or "N/A",
        'will_this_data_be_published': clean_text(will_be_published) or "N/A"
    }


def extract_research_method(data: dict) -> dict:
    """Extract research method information from JSON."""
    metadata_blocks = data.get('datasetVersion', {}).get('metadataBlocks', {})
    citation_fields = metadata_blocks.get('citation', {}).get('fields', [])

    descriptions = extract_field_value(citation_fields, 'dsDescription')
    method_name = "ResearchMethod"
    method_details = ""
    type_s = ""

    if descriptions and len(descriptions) > 0:
        desc = descriptions[0].get('dsDescriptionValue', {}).get('value', '')
        desc_lower = desc.lower()
        if "grounded theory" in desc_lower:
            method_details = "Constructivist Grounded Theory"
        if "qualitative" in desc_lower:
            type_s = "Qualitative"
        elif "quantitative" in desc_lower:
            type_s = "Quantitative"
        elif "mixed" in desc_lower:
            type_s = "Mixed Methods"
        elif "egocentric" in desc_lower or "computer vision" in desc_lower:
            method_details = "Egocentric computer vision / Gesture recognition dataset"
            type_s = "Computer Vision"

    return {
        'rm_id': None,
        'name': method_name,
        'method_details': method_details or "N/A",
        'type_s': type_s or "N/A"
    }


def extract_experiment_instrument(data: dict) -> dict:
    """Extract experiment instrument information from JSON."""
    metadata_blocks = data.get('datasetVersion', {}).get('metadataBlocks', {})
    social_science_fields = metadata_blocks.get('socialscience', {}).get('fields', [])
    files = data.get('datasetVersion', {}).get('files', [])

    research_instrument = extract_field_value(social_science_fields, 'researchInstrument') or ""
    survey = code_book = ""
    for f in files:
        desc = f.get('description', '').lower()
        filename = f.get('label', '').lower()
        if 'questionnaire' in desc or 'questionnaire' in filename or 'protocol' in filename:
            survey = f.get('label', '')
        if 'codebook' in desc or 'code_book' in filename or 'codebook' in filename:
            code_book = f.get('label', '')
    if not survey and research_instrument:
        survey = research_instrument

    return {
        'ei_id': None,
        'Survey': clean_text(survey) or "N/A",
        'Code_book': clean_text(code_book) or "N/A"
    }


def _parse_universe_for_subjects(universe_str: str) -> tuple:
    """Parse universe string (e.g. 'Total: 32 Participants\\nAge: 19 - 56...') into Quantities, Gender, Age."""
    quantities = "N/A"
    gender = "N/A"
    age = "N/A"
    if not universe_str or universe_str == "N/A":
        return quantities, gender, age
    s = universe_str.replace("\n", " ")
    m = re.search(r"Total:\s*(\d+\s*Participants?)", s, re.IGNORECASE)
    if m:
        quantities = m.group(1).strip()
        if not quantities.endswith("participants") and not quantities.endswith("Participants"):
            quantities = f"{quantities} participants"
    m = re.search(r"Age:\s*([^\n]+?)(?=\s+Sex:|\s+Races:|\s*$)", s, re.IGNORECASE)
    if m:
        age = m.group(1).strip()
    m = re.search(r"Sex:\s*([^\n]+?)(?=\s+Races:|\s*$)", s, re.IGNORECASE)
    if m:
        gender = m.group(1).strip()
    return quantities, gender, age


def extract_human_subject(data: dict) -> dict:
    """Extract human subject information from JSON."""
    metadata_blocks = data.get('datasetVersion', {}).get('metadataBlocks', {})
    social_science_fields = metadata_blocks.get('socialscience', {}).get('fields', [])
    citation_fields = metadata_blocks.get('citation', {}).get('fields', [])

    universe = extract_field_value(social_science_fields, 'universe')
    universe_str = universe[0] if universe else ""

    descriptions = extract_field_value(citation_fields, 'dsDescription')
    description = participant_count = ""
    if descriptions and len(descriptions) > 0:
        description = descriptions[0].get('dsDescriptionValue', {}).get('value', '')
        match = re.search(r'(\d+)\s*participants', description, re.IGNORECASE)
        if match:
            participant_count = match.group(1)

    quantities, gender, age = _parse_universe_for_subjects(universe_str)
    if participant_count and quantities == "N/A":
        quantities = f"{participant_count} participants"

    collection_mode = extract_field_value(social_science_fields, 'collectionMode')
    recruitment_mode = collection_mode[0] if collection_mode else ""
    data_collection_situation = extract_field_value(social_science_fields, 'dataCollectionSituation') or ""
    production_place = extract_field_value(citation_fields, 'productionPlace')
    regional_distribution = production_place[0] if production_place else ""

    return {
        'hs_id': None,
        'Age': age or "N/A",
        'Gender': gender or "N/A",
        'Ethnicity': "N/A",
        'How_many_participants_are_included': participant_count or "N/A",
        'Quantities': quantities or "N/A",
        'Regional_Distribution': clean_text(regional_distribution) or "N/A",
        'Recruitment_mode': clean_text(recruitment_mode if recruitment_mode else data_collection_situation) or "N/A",
        'IRB_Number_and_resolution': "N/A",
        'Protected_Data': "Yes" if description and ("privacy" in description.lower() or "anonymized" in description.lower() or "irb" in description.lower()) else "N/A"
    }


def extract_experiment_setting(data: dict) -> dict:
    """Extract experiment setting information from JSON."""
    metadata_blocks = data.get('datasetVersion', {}).get('metadataBlocks', {})
    social_science_fields = metadata_blocks.get('socialscience', {}).get('fields', [])
    citation_fields = metadata_blocks.get('citation', {}).get('fields', [])

    production_place = extract_field_value(citation_fields, 'productionPlace')
    geographical_location = production_place[0] if production_place else ""
    collection_mode = extract_field_value(social_science_fields, 'collectionMode')
    format_val = collection_mode[0] if collection_mode else ""
    data_collection_situation = extract_field_value(social_science_fields, 'dataCollectionSituation') or ""
    conditions = tasks = ""

    descriptions = extract_field_value(citation_fields, 'dsDescription')
    if descriptions and len(descriptions) > 0:
        desc = descriptions[0].get('dsDescriptionValue', {}).get('value', '').lower()
        if "indoor" in desc or "outdoor" in desc:
            conditions = "Indoor and outdoor environments"
        if "gesture" in desc:
            tasks = "Hand-arm gesture segmentation and classification"

    return {
        'es_id': None,
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

    time_method = extract_field_value(social_science_fields, 'timeMethod') or ""
    frequency = extract_field_value(social_science_fields, 'frequencyOfDataCollection') or ""
    duration_of_trials = ""
    descriptions = extract_field_value(citation_fields, 'dsDescription')
    if descriptions and len(descriptions) > 0:
        desc = descriptions[0].get('dsDescriptionValue', {}).get('value', '')
        match = re.search(r'(\d+)\s*(?:to|and|-)\s*(\d+)\s*minutes', desc, re.IGNORECASE)
        if match:
            duration_of_trials = f"{match.group(1)}-{match.group(2)} minutes"
        else:
            match = re.search(r'(\d+)\s*minutes', desc, re.IGNORECASE)
            if match:
                duration_of_trials = f"{match.group(1)} minutes"
    if not duration_of_trials and time_method:
        duration_of_trials = time_method

    return {
        's_id': None,
        'Sessions': clean_text(frequency) or "N/A",
        'Number_of_sessions': "N/A",
        'Trials_per_session': "N/A",
        'Duration_of_trials': clean_text(duration_of_trials) or "N/A",
        'Subjects_per_session': "N/A"
    }


def extract_dataset_info(data: dict) -> dict:
    """Extract dataset information including URL."""
    url = data.get('persistentUrl', '')
    return {
        'd_id': None,
        'name': 'Dataset',
        'url': clean_text(url) or "N/A"
    }


def check_robot_presence(data: dict):
    """Check if the JSON indicates presence of a robot. Returns robot data if present, None otherwise."""
    metadata_blocks = data.get('datasetVersion', {}).get('metadataBlocks', {})
    citation_fields = metadata_blocks.get('citation', {}).get('fields', [])

    title = extract_field_value(citation_fields, 'title') or ""
    descriptions = extract_field_value(citation_fields, 'dsDescription')
    description = ""
    if descriptions and len(descriptions) > 0:
        description = descriptions[0].get('dsDescriptionValue', {}).get('value', '')

    if "Non-Robot" in title or "non-robot" in title.lower():
        return None
    if "Pre-Deployment" in title and "deployed" not in description.lower():
        return None

    robot_indicators = ['deployed robot', 'robot deployment', 'using robot', 'robot named',
                       'the robot', 'our robot', 'robot was used', 'hololens', 'hri']
    robot_present = any(ind in description.lower() for ind in robot_indicators)
    if not robot_present:
        return None

    return {
        'r_id': None,
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


def check_human_data_presence(data: dict) -> bool:
    """Check if the dataset contains human data."""
    metadata_blocks = data.get('datasetVersion', {}).get('metadataBlocks', {})
    social_science_fields = metadata_blocks.get('socialscience', {}).get('fields', [])
    citation_fields = metadata_blocks.get('citation', {}).get('fields', [])

    if extract_field_value(social_science_fields, 'universe'):
        return True
    descriptions = extract_field_value(citation_fields, 'dsDescription')
    if descriptions and len(descriptions) > 0:
        desc = descriptions[0].get('dsDescriptionValue', {}).get('value', '').lower()
        for ind in ['participant', 'interview', 'survey', 'human subject', 'respondent']:
            if ind in desc:
                return True
    return False


def check_robot_data_presence(data: dict) -> bool:
    """Check if the dataset contains robot data."""
    metadata_blocks = data.get('datasetVersion', {}).get('metadataBlocks', {})
    citation_fields = metadata_blocks.get('citation', {}).get('fields', [])
    title = extract_field_value(citation_fields, 'title') or ""
    if "Non-Robot" in title or "non-robot" in title.lower():
        return False

    descriptions = extract_field_value(citation_fields, 'dsDescription')
    if descriptions and len(descriptions) > 0:
        desc = descriptions[0].get('dsDescriptionValue', {}).get('value', '').lower()
        for ind in ['robot data', 'robot log', 'sensor data', 'robot sensor', 'robot recording', 'robot trajectory']:
            if ind in desc:
                return True

    for f in data.get('datasetVersion', {}).get('files', []):
        fn, fd = f.get('label', '').lower(), f.get('description', '').lower()
        if 'robot' in fn or 'sensor' in fn or 'robot' in fd:
            return True
    return False


def extract_data_files(data: dict) -> list:
    """
    Extract DataFile entries from the dataset.
    Each file gets: file_data_id, filename, full_path, directory_path, content_type,
    friendly_type, filesize, filesize_human, md5, storage_identifier, plus parsed
    directory dimensions (data_type, environment, people_presence, clothing).
    """
    files = data.get('datasetVersion', {}).get('files', [])
    result = []
    for f in files:
        label = f.get('label', '')
        directory_label = f.get('directoryLabel', '')
        data_file = f.get('dataFile', {})
        file_id = data_file.get('id')
        filename = data_file.get('filename', label)
        full_path = f"{directory_label}/{label}".strip('/') if directory_label else label
        content_type = data_file.get('contentType', '')
        friendly_type = data_file.get('friendlyType', '')
        filesize = data_file.get('filesize')
        md5 = data_file.get('md5', '') or (data_file.get('checksum', {}).get('value', '') if data_file.get('checksum') else '')
        storage_identifier = data_file.get('storageIdentifier', '')
        filesize_human = format_filesize(filesize) if filesize is not None else "N/A"
        parsed = parse_directory_path(directory_label)
        result.append({
            'file_data_id': file_id,
            'filename': clean_text(filename) or "N/A",
            'full_path': full_path or "N/A",
            'directory_path': directory_label or "N/A",
            'content_type': content_type or "N/A",
            'friendly_type': friendly_type or "N/A",
            'filesize': filesize if filesize is not None else 0,
            'filesize_human': filesize_human,
            'md5': md5 or "N/A",
            'storage_identifier': clean_text(storage_identifier) or "N/A",
            'data_type': parsed.get('data_type', "N/A"),
            'environment': parsed.get('environment', "N/A"),
            'people_presence': parsed.get('people_presence', "N/A"),
            'clothing': parsed.get('clothing', "N/A"),
        })
    return result

def create_graph(driver, json_data: dict):
    """Create the Neo4j graph structure from metadata JSON."""

    rp_data = extract_research_project_data(json_data)
    rm_data = extract_research_method(json_data)
    ei_data = extract_experiment_instrument(json_data)
    hs_data = extract_human_subject(json_data)
    es_data = extract_experiment_setting(json_data)
    sessions_data = extract_sessions(json_data)
    dataset_data = extract_dataset_info(json_data)
    data_files = extract_data_files(json_data)
    robot_data = check_robot_presence(json_data)
    has_human_data = check_human_data_presence(json_data)
    has_robot_data = check_robot_data_presence(json_data)

    with driver.session() as session:
        # rp_data['rp_id'] = get_next_id(session, 'ResearchProject', 'rp_id')
        rm_data['rm_id'] = get_next_id(session, 'ResearchMethod', 'rm_id')
        ei_data['ei_id'] = get_next_id(session, 'ExperimentInstrument', 'ei_id')
        hs_data['hs_id'] = get_next_id(session, 'HumanSubjects', 'hs_id')
        es_data['es_id'] = get_next_id(session, 'ExperimentSetting', 'es_id')
        sessions_data['s_id'] = get_next_id(session, 'Session', 's_id')
        dataset_data['d_id'] = get_next_id(session, 'Dataset', 'd_id')
        if robot_data:
            robot_data['r_id'] = get_next_id(session, 'Robots', 'r_id')

        result = session.run("""
            CREATE (rp:ResearchProject {
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
            RETURN elementId(rp) AS id
        """, **rp_data)
        rp_internal_id = result.single()["id"]
        print(f"Created ResearchProject (ID={rp_internal_id}): {rp_data['research_project_title'][:60]}...")

        session.run("""
            MATCH (rp:ResearchProject) WHERE elementId(rp) = $rp_id
            CREATE (rm:ResearchMethod {
                rm_id: $rm_id,
                name: $name,
                method_details: $method_details,
                type_s: $type_s
            })
            CREATE (rp)-[:Has_ResearchMethod]->(rm)
        """, rp_id=rp_internal_id, **rm_data)

        # session.run("""
        #     MATCH (rm:ResearchMethod {rm_id: $rm_id})
        #     CREATE (ei:ExperimentInstrument {
        #         ei_id: $ei_id,
        #         Survey: $Survey,
        #         Code_book: $Code_book
        #     })
        #     CREATE (rm)-[:Has_ExperimentInstrument]->(ei)
        # """, rm_id=rm_data['rm_id'], **ei_data)

        session.run("""
            MATCH (rm:ResearchMethod {rm_id: $rm_id})
            CREATE (hs:HumanSubjects {
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

        # session.run("""
        #     MATCH (rm:ResearchMethod {rm_id: $rm_id})
        #     CREATE (s:Session {
        #         s_id: $s_id,
        #         Sessions: $Sessions,
        #         Number_of_sessions: $Number_of_sessions,
        #         Trials_per_session: $Trials_per_session,
        #         Duration_of_trials: $Duration_of_trials,
        #         Subjects_per_session: $Subjects_per_session
        #     })
        #     CREATE (rm)-[:Has_Sessions]->(s)
        # """, rm_id=rm_data['rm_id'], **sessions_data)

        # if robot_data:
        #     session.run("""
        #         MATCH (rp:ResearchProject {rp_id: $rp_id})
        #         CREATE (r:Robots {
        #             r_id: $r_id,
        #             Robot_type: $Robot_type,
        #             Model: $Model,
        #             Robot_Model_URL: $Robot_Model_URL,
        #             Hardware_instrumentation: $Hardware_instrumentation,
        #             Software_instrumentation: $Software_instrumentation,
        #             Indicate_if_adaptations_were_made: $Indicate_if_adaptations_were_made,
        #             Implementation: $Implementation,
        #             Size: $Size,
        #             Motion_replay: $Motion_replay
        #         })
        #         CREATE (rp)-[:Experiment_Robots]->(r)
        #     """, rp_id=rp_data['rp_id'], **robot_data)
        #     print(f"Created Robot node (r_id={robot_data['r_id']})")

        dataset_url = DATASET_PAGE_URL
        session.run("""
            MATCH (rp:ResearchProject) WHERE elementId(rp) = $rp_id
            CREATE (d:Dataset {
                d_id: $d_id,
                name: $name,
                url: $url
            })
            CREATE (rp)-[:Generates]->(d)
        """, rp_id=rp_internal_id, d_id=dataset_data['d_id'], name=dataset_data['name'], url=dataset_url)
        print(f"Created Dataset (d_id={dataset_data['d_id']}): {dataset_url}")

        # if has_robot_data:
        #     rd_id = get_next_id(session, 'RobotDataset', 'rd_id')
        #     session.run("""
        #         MATCH (d:Dataset {d_id: $d_id})
        #         CREATE (rd:RobotDataset {rd_id: $rd_id, name: 'RobotDataset', url: $url})
        #         CREATE (d)-[:Dataset_Robot]->(rd)
        #     """, d_id=dataset_data['d_id'], rd_id=rd_id, url=DATASET_PAGE_URL)
        #     print(f"Created RobotDataset node (rd_id={rd_id})")

        # Dataset hierarchy: (Dataset)-[Dataset_Indoor]->(HumanDataset Indoor)-[Contains]->(People/No_People)-[Contains]->(Covered/Uncovered)
        # All hierarchy nodes link back to the dataset page.
        session.run("""
            MATCH (d:Dataset {d_id: $d_id})
            CREATE (hd_indoor:HumanDataset {name: 'Indoor', url: $url})
            CREATE (hd_outdoor:HumanDataset {name: 'Outdoor', url: $url})
            CREATE (d)-[:Dataset_Indoor]->(hd_indoor)
            CREATE (d)-[:Dataset_Outdoor]->(hd_outdoor)
        """, d_id=dataset_data['d_id'], url=DATASET_PAGE_URL)

        # Indoor -> People, No_People; Outdoor -> People, No_People
        for env_name in ("Indoor", "Outdoor"):
            session.run("""
                MATCH (hd:HumanDataset {name: $env_name})
                CREATE (hd_people:HumanDataset {name: 'People', url: $url}),
                       (hd_nopeople:HumanDataset {name: 'No_People', url: $url})
                CREATE (hd)-[:Contains]->(hd_people)
                CREATE (hd)-[:Contains]->(hd_nopeople)
            """, env_name=env_name, url=DATASET_PAGE_URL)

        # People / No_People -> Covered, Uncovered (store path on leaf for matching: e.g. "Indoor/People/Covered")
        for env_name in ("Indoor", "Outdoor"):
            for people_name in ("People", "No_People"):
                # Match the parent: (Indoor)-[:Contains]->(People) - we need to match the specific People/No_People under this env
                session.run("""
                MATCH (hd_env:HumanDataset {name: $env_name})
                MATCH (hd_env)-[:Contains]->(hd_pp:HumanDataset {name: $people_name})
                CREATE (hd_covered:HumanDataset {name: 'Covered', path: $path_covered, url: $url}),
                       (hd_uncovered:HumanDataset {name: 'Uncovered', path: $path_uncovered, url: $url})
                CREATE (hd_pp)-[:Contains]->(hd_covered)
                CREATE (hd_pp)-[:Contains]->(hd_uncovered)
                """, env_name=env_name, people_name=people_name,
                     path_covered=f"{env_name}/{people_name}/Covered",
                     path_uncovered=f"{env_name}/{people_name}/Uncovered",
                     url=DATASET_PAGE_URL)

        video_types = set(  i["directory_path"].split("/")[-1] for i in data_files if i["data_type"] == "videos")
        for env_name in ("Indoor", "Outdoor"):
            for people_name in ("People", "No_People"):
                for covered in ("Covered", "Uncovered"):
                    for video_type in video_types:
                        session.run("""
                        MATCH (hd_env:HumanDataset {name: $env_name})
                        MATCH (hd_env)-[:Contains]->(hd_pp:HumanDataset {name: $people_name})
                        MATCH (hd_pp)-[:Contains]->(hd_clothing:HumanDataset {name: $covered})
                        CREATE (hd_type:HumanDataset {name: $name, path: $path, url: $url})
                        CREATE (hd_clothing)-[:Contains]->(hd_type)
                        """, env_name=env_name, people_name=people_name, covered=covered,
                            name=video_type, path=f"{env_name}/{people_name}/{covered}/{video_type}",
                            url=DATASET_PAGE_URL)

        # Create zip nodes and link to leaf HumanDataset by path
        df_ids = {i: get_next_id(session, i, 'file_id') for i in ("images", "masks", "videos")}
        for i, df in enumerate(data_files):
            directory_path = df.get("directory_path", "")
            parts = [p for p in directory_path.split("/") if p] if directory_path else []
            if len(parts) >= 5:
                important_attributes = [("filename", "name"), ("directory_path", "directory_path"), ("friendly_type", "data_type"), ("storage_identifier", "storage_identifier"), ("filesize_human", "filesize")]
                data_type = df.get("data_type")
                attributes = {attr[1]: df.get(attr[0]) for attr in important_attributes}
                file_id = df_ids[data_type]
                df_ids[data_type] += 1
                session.run(f"""
                    CREATE (f:{data_type} {{
                        file_id: $file_id,
                        {",\n".join(f"{key}: ${key}" for key in attributes)}
                    }})
                """, file_id=file_id, **attributes)
                # Path in directory_path is e.g. data/masks/Indoor/People/Uncovered -> leaf path = "Indoor/People/Uncovered"

                leaf_path = "/".join(parts[2:])  # environment/people_presence/clothing/subtask
                if len(parts) == 5: leaf_path += f"/{df.get("filename").split(".")[0]}"
                session.run(f"""
                    MATCH (leaf:HumanDataset {{path: $leaf_path}})
                    MATCH (f:{data_type} {{ file_id: $file_id }})
                    CREATE (leaf)-[:Contains]->(f)
                """, leaf_path=leaf_path, file_id=file_id)
            else:
                pass
                # session.run("""
                #     MATCH (d:Dataset {d_id: $d_id})
                #     MATCH (v:video { file_id: $file_id })
                #     CREATE (d)-[:Contains]->(v)
                # """, d_id=dataset_data['d_id'], file_id=file_id)

        # if has_human_data:
        #     hd_id = get_next_id(session, 'HumanDataset', 'hd_id')
        #     session.run("""
        #         MATCH (d:Dataset {d_id: $d_id})
        #         CREATE (hd:HumanDataset {hd_id: $hd_id, name: 'HumanDataset', url: $url})
        #         CREATE (d)-[:Dataset_Human]->(hd)
        #     """, d_id=dataset_data['d_id'], hd_id=hd_id, url=DATASET_PAGE_URL)
        #     print(f"Created HumanDataset node (hd_id={hd_id})")

        print(f"Created dataset hierarchy (Dataset_Indoor/Dataset_Outdoor -> People/No_People -> Covered/Uncovered) and {len(data_files)} video nodes")


def main():
    project_root = Path(__file__).resolve().parent.parent
    metadata_path = project_root / "EgoNRG" / "egonrg.json"

    json_file_path = Path(metadata_path)
    if not json_file_path.exists():
        print(f"Error: File not found: {json_file_path}")
        return 1

    print(f"Loading JSON from: {json_file_path}")
    json_data = load_json_file(str(json_file_path))

    if GraphDatabase is None:
        print("Error: neo4j package required for --neo4j. Install with: pip install neo4j")
        return 1
    driver = GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))
    try:
        driver.verify_connectivity()
        print("Connected to Neo4j successfully!")
        create_graph(driver, json_data)
        print("Neo4j graph creation completed.")
    except Exception as e:
        print(f"Neo4j error: {e}")
        raise
    finally:
        driver.close()

    return 0


if __name__ == "__main__":
    exit(main())

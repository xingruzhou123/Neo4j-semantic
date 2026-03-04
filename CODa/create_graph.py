"""
Script to build a knowledge graph from CODa Re-ID coda_reid.json metadata.

Relationship and property names align with the graph schema (e.g. graph.svg).

CODa Re-ID is a robot-captured object re-identification dataset (no human
subjects).  Nodes included vs omitted relative to the full schema:

  INCLUDED:
    ResearchProject, ResearchMethod, ExperimentSetting, Dataset, Robot, RobotData

  OMITTED (no relevant data in JSON):
    ExperimentInstrument  - no questionnaires / codebooks; purely a CV dataset
    HumanSubject          - dataset is about static objects, not human participants
    Sessions              - no session structure present in metadata
    HumanData / HumanData_session - no human-subject data
    RobotData_session     - files organised by object class, not by session

Dataset file hierarchy built under RobotData:
  (RobotData)-[:Contains]->(AnnotationType {"2D_Annotations", "3D_BBox_Global"})
  (3D_BBox_Global)-[:Contains]->(ObjectClass)  -- one node per class JSON file

Usage:
  python create_graph.py [--neo4j]
Requires the neo4j package and a running Neo4j instance for --neo4j mode.
"""

import json
import re
from pathlib import Path

try:
    from neo4j import GraphDatabase
except ImportError:
    GraphDatabase = None

DATASET_PAGE_URL = "https://doi.org/10.18738/T8/E9WFTW"

URI = "bolt://localhost:7687"
USERNAME = "neo4j"
PASSWORD = "12345678"


# ---------------------------------------------------------------------------
# Shared utilities (identical to EgoNRG version)
# ---------------------------------------------------------------------------

def clean_text(text: str) -> str:
    """Remove HTML tags and normalise whitespace."""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def clean_list_to_string(items: list) -> str:
    """Convert a list to a clean comma-separated string."""
    if not items:
        return ""
    return ", ".join(clean_text(str(item)) for item in items)


def load_json_file(file_path: str) -> dict:
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def extract_field_value(fields: list, type_name: str):
    """Extract a field value from a metadataBlocks fields list."""
    if not fields:
        return None
    for field in fields:
        if field.get('typeName') == type_name:
            return field.get('value')
    return None


def get_next_id(session, label: str, id_field: str) -> int:
    """Return the next sequential ID for a given label."""
    result = session.run(f"""
        MATCH (n:{label})
        RETURN COALESCE(MAX(n.{id_field}), 0) AS max_id
    """)
    record = result.single()
    return record["max_id"] + 1


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def extract_research_project_data(data: dict) -> dict:
    """Extract ResearchProject node properties from CODa Re-ID JSON."""
    citation_fields = (
        data.get('datasetVersion', {})
            .get('metadataBlocks', {})
            .get('citation', {})
            .get('fields', [])
    )

    # Title
    title = extract_field_value(citation_fields, 'title') or ""

    # Contact
    contacts = extract_field_value(citation_fields, 'datasetContact') or []
    contact_info = ""
    if contacts:
        c = contacts[0]
        name = c.get('datasetContactName', {}).get('value', '')
        email = c.get('datasetContactEmail', {}).get('value', '')
        contact_info = f"{name} ({email})" if name and email else name or email

    # Description
    descriptions = extract_field_value(citation_fields, 'dsDescription') or []
    description = ""
    if descriptions:
        description = descriptions[0].get('dsDescriptionValue', {}).get('value', '')

    # Dates - CODa Re-ID has no dateOfCollection; use productionDate as begin date
    production_date = extract_field_value(citation_fields, 'productionDate') or ""
    publication_date = data.get('publicationDate', '')

    # Site
    production_place = extract_field_value(citation_fields, 'productionPlace') or []
    site = production_place[0] if production_place else ""

    # Keywords
    keywords_data = extract_field_value(citation_fields, 'keyword') or []
    keywords = [
        kw.get('keywordValue', {}).get('value', '')
        for kw in keywords_data
        if isinstance(kw, dict) and kw.get('keywordValue', {}).get('value')
    ]

    # Study area
    subjects = extract_field_value(citation_fields, 'subject') or []
    study_area = subjects[0] if subjects else ""

    # Team members (authors)
    authors_data = extract_field_value(citation_fields, 'author') or []
    team_members = []
    for author in authors_data:
        if not isinstance(author, dict):
            continue
        name = author.get('authorName', {}).get('value', '')
        affiliation_raw = author.get('authorAffiliation', {}).get('value', '')
        expanded = author.get('authorAffiliation', {}).get('expandedvalue', {})
        affiliation = expanded.get('termName', affiliation_raw) if isinstance(expanded, dict) else affiliation_raw
        if name:
            team_members.append(f"{name} ({affiliation})" if affiliation else name)

    # Research problem - extracted from description highlights
    research_problem = (
        "Object re-identification, object-centric SLAM, long-term localization, "
        "and persistent scene understanding in outdoor campus environments"
    )

    will_be_published = "Yes" if publication_date else "No"

    return {
        'research_project_title': clean_text(title) or "N/A",
        'contact_person_and_email': clean_text(contact_info) or "N/A",
        'data_description': clean_text(description) or "N/A",
        'data_gathering_begin_date': clean_text(production_date) or "N/A",
        'data_gathering_end_date': "N/A",   # no end date in metadata
        'data_gathering_site': clean_text(site) or "N/A",
        'human_subjects': "N/A",            # not a human-subject study
        'instruments': "N/A",               # no socialscience block
        'keywords': clean_list_to_string(keywords) or "N/A",
        'research_problem_question': research_problem,
        'study_area': clean_text(study_area) or "N/A",
        'team_members': clean_list_to_string(team_members) or "N/A",
        'will_this_data_be_published': will_be_published,
    }


def extract_research_method(data: dict) -> dict:
    """Extract ResearchMethod properties.

    CODa Re-ID is a Computer Vision dataset built with a semi-automated
    annotation pipeline (LiDAR-inertial SLAM + SAM + manual verification).
    """
    return {
        'rm_id': None,
        'name': 'ResearchMethod',
        'method_details': (
            "Semi-automated annotation pipeline: LiDAR-inertial odometry "
            "alignment with manual loop closures, 3D instance annotation "
            "clustering, projection to image frames, SAM-based automatic mask "
            "generation, targeted manual verification and correction."
        ),
        'type_s': 'Computer Vision',
    }


def extract_experiment_setting(data: dict) -> dict:
    """Extract ExperimentSetting properties from description text."""
    citation_fields = (
        data.get('datasetVersion', {})
            .get('metadataBlocks', {})
            .get('citation', {})
            .get('fields', [])
    )
    production_place = extract_field_value(citation_fields, 'productionPlace') or []
    geo = production_place[0] if production_place else ""

    descriptions = extract_field_value(citation_fields, 'dsDescription') or []
    desc_html = descriptions[0].get('dsDescriptionValue', {}).get('value', '') if descriptions else ""
    desc = clean_text(desc_html).lower()

    conditions = "N/A"
    if any(w in desc for w in ["sunny", "overcast", "rainy", "low-light", "night"]):
        conditions = "Multiple times of day and weather: sunny, overcast, rainy, low-light/night"

    tasks = "N/A"
    if "re-identification" in desc or "re-id" in desc:
        tasks = (
            "Object re-identification, object-centric SLAM, long-term "
            "localization, persistent scene understanding"
        )

    return {
        'es_id': None,
        'Format': "Autonomous robot traversals",
        'Geographical_location': clean_text(geo) or "N/A",
        'Environment_description': (
            "Outdoor university campus with varying lighting, weather, "
            "and viewpoint conditions across multiple robot traversal sequences"
        ),
        'Conditions': conditions,
        'Tasks': tasks,
    }


def extract_robot_data(data: dict) -> dict:
    """Extract Robot node properties.

    The dataset was collected by an autonomous mobile robot at UT Austin's
    Autonomous Mobile Robotics Laboratory.  Software tools are listed in the
    JSON `software` field.
    """
    citation_fields = (
        data.get('datasetVersion', {})
            .get('metadataBlocks', {})
            .get('citation', {})
            .get('fields', [])
    )
    software_entries = extract_field_value(citation_fields, 'software') or []
    software_names = []
    for entry in software_entries:
        if isinstance(entry, dict):
            name = entry.get('softwareName', {}).get('value', '')
            if name:
                software_names.append(name)
    software_str = ", ".join(software_names) if software_names else "N/A"

    return {
        'r_id': None,
        'Robot_type': "Autonomous Mobile Robot",
        'Model': "N/A",
        'Robot_Model_URL': "N/A",
        'Hardware_instrumentation': "LiDAR, RGB camera",
        'Software_instrumentation': software_str,
        'Indicate_if_adaptations_were_made': "N/A",
        'Implementation': "N/A",
        'Size': "N/A",
        'Motion_replay': "N/A",
    }


def extract_dataset_info(data: dict) -> dict:
    url = data.get('persistentUrl', DATASET_PAGE_URL)
    title = ""
    citation_fields = (
        data.get('datasetVersion', {})
            .get('metadataBlocks', {})
            .get('citation', {})
            .get('fields', [])
    )
    title = extract_field_value(citation_fields, 'title') or "Dataset"
    return {
        'd_id': None,
        'name': clean_text(title) or "Dataset",
        'url': clean_text(url) or "N/A",
    }


def extract_annotation_files(data: dict) -> dict:
    """
    Categorise dataset files into annotation types.

    Returns:
        {
            '2D_Annotations': [list of file dicts],
            '3D_BBox_Global': [list of file dicts],
            'documentation': [list of file dicts],
        }
    """
    files = data.get('datasetVersion', {}).get('files', [])
    categories = {'2D_Annotations': [], '3D_BBox_Global': [], 'documentation': []}

    for f in files:
        directory = f.get('directoryLabel', '')
        label = f.get('label', '')
        data_file = f.get('dataFile', {})
        entry = {
            'label': label,
            'directory': directory,
            'content_type': data_file.get('contentType', ''),
            'filesize': data_file.get('filesize', 0),
            'md5': data_file.get('md5', ''),
            'description': f.get('description', ''),
        }
        if directory.startswith('data/3d_bbox'):
            categories['3D_BBox_Global'].append(entry)
        elif directory.startswith('data/annotations') or 'annotation' in label.lower():
            categories['2D_Annotations'].append(entry)
        else:
            categories['documentation'].append(entry)

    return categories


# ---------------------------------------------------------------------------
# Graph creation
# ---------------------------------------------------------------------------

def create_graph(driver, json_data: dict):
    """Create the Neo4j graph structure from CODa Re-ID metadata JSON."""

    rp_data = extract_research_project_data(json_data)
    rm_data = extract_research_method(json_data)
    es_data = extract_experiment_setting(json_data)
    robot_data = extract_robot_data(json_data)
    dataset_data = extract_dataset_info(json_data)
    annotation_files = extract_annotation_files(json_data)

    with driver.session() as session:
        rm_data['rm_id'] = get_next_id(session, 'ResearchMethod', 'rm_id')
        es_data['es_id'] = get_next_id(session, 'ExperimentSetting', 'es_id')
        robot_data['r_id'] = get_next_id(session, 'Robot', 'r_id')
        dataset_data['d_id'] = get_next_id(session, 'Dataset', 'd_id')

        # ── ResearchProject ──────────────────────────────────────────────────
        result = session.run("""
            CREATE (rp:ResearchProject {
                research_project_title:    $research_project_title,
                contact_person_and_email:  $contact_person_and_email,
                data_description:          $data_description,
                data_gathering_begin_date: $data_gathering_begin_date,
                data_gathering_end_date:   $data_gathering_end_date,
                data_gathering_site:       $data_gathering_site,
                human_subjects:            $human_subjects,
                instruments:               $instruments,
                keywords:                  $keywords,
                research_problem_question: $research_problem_question,
                study_area:                $study_area,
                team_members:              $team_members,
                will_this_data_be_published: $will_this_data_be_published
            })
            RETURN elementId(rp) AS id
        """, **rp_data)
        rp_internal_id = result.single()["id"]
        print(f"Created ResearchProject: {rp_data['research_project_title'][:70]}")

        # ── ResearchMethod ───────────────────────────────────────────────────
        # Omitted: ExperimentInstrument (no questionnaires/codebooks)
        session.run("""
            MATCH (rp:ResearchProject) WHERE elementId(rp) = $rp_id
            CREATE (rm:ResearchMethod {
                rm_id:          $rm_id,
                name:           $name,
                method_details: $method_details,
                type_s:         $type_s
            })
            CREATE (rp)-[:HAS_METHOD]->(rm)
        """, rp_id=rp_internal_id, **rm_data)
        print(f"Created ResearchMethod (rm_id={rm_data['rm_id']}): {rm_data['type_s']}")

        # ── ExperimentSetting ────────────────────────────────────────────────
        # Omitted: HumanSubject (no human participants in this dataset)
        # Omitted: Sessions (no session-level metadata available)
        session.run("""
            MATCH (rm:ResearchMethod {rm_id: $rm_id})
            CREATE (es:ExperimentSetting {
                es_id:                  $es_id,
                Format:                 $Format,
                Geographical_location:  $Geographical_location,
                Environment_description:$Environment_description,
                Conditions:             $Conditions,
                Tasks:                  $Tasks
            })
            CREATE (rm)-[:Has_Settings]->(es)
        """, rm_id=rm_data['rm_id'], **es_data)
        print(f"Created ExperimentSetting (es_id={es_data['es_id']})")

        # ── Dataset ──────────────────────────────────────────────────────────
        session.run("""
            MATCH (rp:ResearchProject) WHERE elementId(rp) = $rp_id
            CREATE (d:Dataset {
                d_id: $d_id,
                name: $name,
                url:  $url
            })
            CREATE (rp)-[:HAS_DATASET]->(d)
        """, rp_id=rp_internal_id, **dataset_data)
        print(f"Created Dataset (d_id={dataset_data['d_id']}): {dataset_data['url']}")

        # ── Robot ────────────────────────────────────────────────────────────
        session.run("""
            MATCH (rp:ResearchProject) WHERE elementId(rp) = $rp_id
            CREATE (r:Robot {
                r_id:                            $r_id,
                Robot_type:                      $Robot_type,
                Model:                           $Model,
                Robot_Model_URL:                 $Robot_Model_URL,
                Hardware_instrumentation:        $Hardware_instrumentation,
                Software_instrumentation:        $Software_instrumentation,
                Indicate_if_adaptations_were_made: $Indicate_if_adaptations_were_made,
                Implementation:                  $Implementation,
                Size:                            $Size,
                Motion_replay:                   $Motion_replay
            })
            CREATE (rp)-[:USES_ROBOT]->(r)
        """, rp_id=rp_internal_id, **robot_data)
        print(f"Created Robot (r_id={robot_data['r_id']}): {robot_data['Robot_type']}")

        # ── RobotData + annotation hierarchy ─────────────────────────────────
        # Omitted: HumanData / HumanData_session (no human subject data)
        # Omitted: RobotData_session (files organised by object class, not session)
        #
        # Hierarchy:
        #   (Dataset)-[:Has_RobotData]->(RobotData)
        #   (RobotData)-[:Contains]->(2D_Annotations)
        #       (2D_Annotations)-[:Contains]->(file node per archive)
        #   (RobotData)-[:Contains]->(3D_BBox_Global)
        #       (3D_BBox_Global)-[:Contains]->(ObjectClass node per JSON file)

        rd_id = get_next_id(session, 'RobotData', 'rd_id')
        session.run("""
            MATCH (d:Dataset {d_id: $d_id})
            CREATE (rd:RobotData {rd_id: $rd_id, name: 'RobotData', url: $url})
            CREATE (d)-[:Has_RobotData]->(rd)
        """, d_id=dataset_data['d_id'], rd_id=rd_id, url=DATASET_PAGE_URL)
        print(f"Created RobotData (rd_id={rd_id})")

        # 2D Annotations branch
        session.run("""
            MATCH (rd:RobotData {rd_id: $rd_id})
            CREATE (ann2d:AnnotationData {
                name: '2D_Annotations',
                description: 'Per-frame 2D bounding box and segmentation contour annotations',
                url: $url
            })
            CREATE (rd)-[:Contains]->(ann2d)
        """, rd_id=rd_id, url=DATASET_PAGE_URL)

        for f in annotation_files['2D_Annotations']:
            session.run("""
                MATCH (ann2d:AnnotationData {name: '2D_Annotations'})
                CREATE (af:AnnotationFile {
                    name:         $name,
                    directory:    $directory,
                    content_type: $content_type,
                    filesize:     $filesize,
                    md5:          $md5,
                    description:  $description,
                    url:          $url
                })
                CREATE (ann2d)-[:Contains]->(af)
            """, name=f['label'], directory=f['directory'],
                content_type=f['content_type'], filesize=f['filesize'],
                md5=f['md5'], description=f['description'], url=DATASET_PAGE_URL)

        # 3D BBox Global branch
        session.run("""
            MATCH (rd:RobotData {rd_id: $rd_id})
            CREATE (bbox3d:AnnotationData {
                name: '3D_BBox_Global',
                description: 'Global-frame 3D bounding box annotations per object class',
                url: $url
            })
            CREATE (rd)-[:Contains]->(bbox3d)
        """, rd_id=rd_id, url=DATASET_PAGE_URL)

        for f in annotation_files['3D_BBox_Global']:
            # Derive a clean class name from the filename (e.g. "Bollard.json" → "Bollard")
            class_name = f['label'].replace('.json', '').replace('_', ' ')
            session.run("""
                MATCH (bbox3d:AnnotationData {name: '3D_BBox_Global'})
                CREATE (oc:ObjectClass {
                    name:         $name,
                    class_name:   $class_name,
                    directory:    $directory,
                    content_type: $content_type,
                    filesize:     $filesize,
                    md5:          $md5,
                    description:  $description,
                    url:          $url
                })
                CREATE (bbox3d)-[:Contains]->(oc)
            """, name=f['label'], class_name=class_name, directory=f['directory'],
                content_type=f['content_type'], filesize=f['filesize'],
                md5=f['md5'], description=f['description'], url=DATASET_PAGE_URL)

        n_2d = len(annotation_files['2D_Annotations'])
        n_3d = len(annotation_files['3D_BBox_Global'])
        print(
            f"Created RobotData hierarchy: "
            f"{n_2d} 2D annotation file(s), "
            f"{n_3d} 3D bbox object class file(s)"
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    project_root = Path(__file__).resolve().parent.parent
    metadata_path = project_root / "CODa" / "coda_reid.json"

    if not metadata_path.exists():
        print(f"Error: File not found: {metadata_path}")
        return 1

    print(f"Loading JSON from: {metadata_path}")
    json_data = load_json_file(str(metadata_path))

    if GraphDatabase is None:
        print("Error: neo4j package required. Install with: pip install neo4j")
        return 1

    driver = GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD),
                                  notifications_min_severity="OFF")
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

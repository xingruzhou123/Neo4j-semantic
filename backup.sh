#!/bin/bash
# Manage Neo4j database backups stored in ./data/backups/
#
# Usage:
#   ./backup.sh                        - create a new backup
#   ./backup.sh restore <timestamp>    - restore a backup (e.g. 20260328_175938)
#   ./backup.sh list                   - list available backups
#   ./backup.sh --container <name>     - use a custom container (default: neo4j)

CONTAINER="neo4j"
COMMAND="backup"
TIMESTAMP=""

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --container|-c)
            CONTAINER="$2"; shift 2 ;;
        restore)
            COMMAND="restore"; TIMESTAMP="$2"; shift 2 ;;
        list)
            COMMAND="list"; shift ;;
        *)
            echo "Unknown argument: $1"; exit 1 ;;
    esac
done

# Get the Neo4j image used by the container (so versions match)
NEO4J_IMAGE=$(docker inspect --format='{{.Config.Image}}' "$CONTAINER" 2>/dev/null)
if [[ -z "$NEO4J_IMAGE" ]]; then
    echo "Error: container '$CONTAINER' not found."
    exit 1
fi

case $COMMAND in
    backup)
        TS=$(date +%Y%m%d_%H%M%S)
        echo "Stopping $CONTAINER..."
        docker stop "$CONTAINER"
        echo "Dumping database..."
        docker run --rm \
            --volumes-from "$CONTAINER" \
            "$NEO4J_IMAGE" \
            bash -c "mkdir -p /data/backups/$TS && neo4j-admin database dump neo4j --to-path=/data/backups/$TS/"
        echo "Restarting $CONTAINER..."
        docker start "$CONTAINER"
        echo "Done. Backup saved to ./data/backups/$TS/"
        ;;

    restore)
        if [[ -z "$TIMESTAMP" ]]; then
            echo "Error: provide a timestamp to restore. Run './backup.sh list' to see available backups."
            exit 1
        fi
        echo "Stopping $CONTAINER..."
        docker stop "$CONTAINER"
        echo "Restoring from $TIMESTAMP..."
        docker run --rm \
            --volumes-from "$CONTAINER" \
            "$NEO4J_IMAGE" \
            bash -c "neo4j-admin database load neo4j --from-path=/data/backups/$TIMESTAMP/ --overwrite-destination"
        echo "Restarting $CONTAINER..."
        docker start "$CONTAINER"
        echo "Done. Restored from ./data/backups/$TIMESTAMP/"
        ;;

    list)
        echo "Available backups:"
        ls -1 ./data/backups/ 2>/dev/null || echo "  (none found in ./data/backups/)"
        ;;
esac
